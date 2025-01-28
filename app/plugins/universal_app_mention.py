# plugins/universal_app_mention.py

import os
import json
import logging
import openai
from slack_bolt import App
import services.openai_service as openai_service

from plugins.rate_limiting import rate_limit_check
from services.openai_service import (
    AVAILABLE_MODELS,
    DEFAULT_MODEL,
#    logger as openai_logger
)
from services.github_service import rollback_to_tag, get_last_deployment_tag

# Self-upgrade helpers (multi-step) -- we won't do mention-based regex
from plugins.self_upgrade import (
    handle_request_upgrade,
    handle_confirm_upgrade,
    handle_new_code,
    handle_do_sanity_check,
    handle_finalize_upgrade,
    handle_abort_upgrade,
    PENDING_UPGRADES
)

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

ADMIN_USER_IDS = set(uid.strip() for uid in os.environ.get("ADMIN_USER_IDS", "").split(",") if uid.strip())

UPGRADE_CHANNEL_NAME = "bot-upgrades"  # If you want to require that channel for upgrades

# If you want to do "are you sure?" confirmations, store them here
PENDING_CONFIRMATIONS = {}

###################################################
# A system prompt telling GPT how to produce
# a single JSON snippet for each user mention.
###################################################
SYSTEM_PROMPT = """\
You are a Slackbot that interprets all user mentions with NO hard-coded regex.
You must produce exactly one JSON snippet at the end of your message in this format:

<<JSON:
{
  "action": "none" | "update_model" | "rollback" | "upgrade" | "chat",
  "model_name": "",
  "rollback_target": "",
  "upgrade_step": "",
  "upgrade_data": "",
  "message_for_user": "",
  "confirmation_needed": false
}
JSON>>

1) If user says "set model to X" or "add model X" => "action":"update_model", "model_name":"X".
2) If user wants to do a rollback => "action":"rollback", "rollback_target":"<tag or 'last'>".
3) If user wants to do a self-upgrade step => "action":"upgrade",
   "upgrade_step":"request|confirm|new_code|do_sanity|finalize|abort",
   "upgrade_data":"(description or code snippet if relevant)".
4) If user is just chatting => "action":"chat" or "none".
5) If request is "risky" or requires confirmation => "confirmation_needed":true.
6) Place normal text or answer in "message_for_user", but the Slackbot code will parse your JSON to do the actual action.

Only produce one JSON snippet, enclosed with <<JSON: ... JSON>>. No disclaimers that you "cannot" do something—just produce the JSON instructions for the Slackbot.
"""

def register(app: App):
    @app.event("app_mention")
    def universal_app_mention(event, say):
        """
        Single GPT call that returns a JSON snippet describing the user's intent:
          "update_model", "rollback", "upgrade", "chat" etc.
        The Slackbot code then performs that action (no separate regex).
        """
        user_id = event.get("user", "")
        text = event.get("text", "").strip()
        channel_id = event.get("channel", "")

        # Basic checks
        if not user_id or not text:
            return

        # Rate limit
        if not rate_limit_check(user_id):
            say(f"<@{user_id}> You've hit the rate limit. Try again later.")
            return

        # If user typed "yes" => confirm an existing action
        if text.lower() == "yes":
            if user_id in PENDING_CONFIRMATIONS:
                pending_action, pending_data = PENDING_CONFIRMATIONS.pop(user_id)
                handle_confirmation(user_id, pending_action, pending_data, say)
                return

        # Otherwise, do a single GPT call for classification + normal text
        gpt_answer = call_gpt(text)

        # Parse out the JSON snippet
        start_tag = "<<JSON:"
        end_tag = "JSON>>"
        user_facing_text = gpt_answer
        action = "none"
        model_name = ""
        rollback_target = ""
        upgrade_step = ""
        upgrade_data = ""
        message_for_user = ""
        confirmation_needed = False

        start_idx = gpt_answer.find(start_tag)
        end_idx = gpt_answer.find(end_tag)
        if start_idx != -1 and end_idx != -1 and end_idx > start_idx:
            json_part = gpt_answer[start_idx + len(start_tag):end_idx].strip()
            user_facing_text = (gpt_answer[:start_idx] + gpt_answer[end_idx + len(end_tag):]).strip()

            try:
                data = json.loads(json_part)
                action = data.get("action", "none")
                model_name = data.get("model_name", "")
                rollback_target = data.get("rollback_target", "")
                upgrade_step = data.get("upgrade_step", "")
                upgrade_data = data.get("upgrade_data", "")
                message_for_user = data.get("message_for_user", "")
                confirmation_needed = data.get("confirmation_needed", False)
            except Exception as e:
                logger.warning(f"Error parsing GPT JSON: {e}")

        # Combine any leftover text with the "message_for_user"
        final_text = user_facing_text
        if message_for_user:
            if final_text.strip():
                final_text += "\n" + message_for_user
            else:
                final_text = message_for_user

        # If there's user-facing text, show it
        if final_text.strip():
            say(f"<@{user_id}> {final_text}")

        # Now interpret "action"
        if action == "update_model":
            if user_id not in ADMIN_USER_IDS:
                say(f"<@{user_id}> Not authorized to update model.")
                return
            if confirmation_needed:
                PENDING_CONFIRMATIONS[user_id] = ("update_model", model_name)
                say(f"<@{user_id}> Type 'yes' to confirm updating the model to '{model_name}'.")
            else:
                handle_update_model(user_id, model_name, say)
        elif action == "rollback":
            if user_id not in ADMIN_USER_IDS:
                say(f"<@{user_id}> Not authorized to rollback.")
                return
            if not rollback_target:
                say("No rollback target specified.")
                return
            if confirmation_needed:
                PENDING_CONFIRMATIONS[user_id] = ("rollback", rollback_target)
                say(f"<@{user_id}> Type 'yes' to confirm rollback to '{rollback_target}'.")
            else:
                handle_rollback(user_id, rollback_target, say)
        elif action == "upgrade":
            # check if the user is in the right channel if you want
            channel_name = get_channel_name(app, channel_id)
            if UPGRADE_CHANNEL_NAME.lower() not in channel_name.lower():
                say(f"<@{user_id}> Upgrades must be requested in #{UPGRADE_CHANNEL_NAME}.")
                return
            # proceed
            handle_upgrade(user_id, upgrade_step, upgrade_data, say)
        else:
            # "chat" or "none" => do nothing special
            pass


def call_gpt(user_text: str) -> str:
    """
    Single call to GPT with the system prompt to produce the JSON snippet.
    """
    import openai
    try:
        response = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_text}
            ],
            temperature=0.7
        )
        return response.choices[0].message["content"].strip()
    except Exception as e:
        logger.error(f"Error calling GPT: {e}")
        return f"Error from GPT: {e}"

def handle_confirmation(user_id: str, pending_action: str, pending_data: str, say):
    """
    Called when user typed 'yes' to confirm a previously stored action.
    """
    if pending_action == "update_model":
        handle_update_model(user_id, pending_data, say, confirmed=True)
    elif pending_action == "rollback":
        handle_rollback(user_id, pending_data, say, confirmed=True)
    else:
        say(f"<@{user_id}> Unknown pending confirmation action '{pending_action}'.")

def handle_update_model(user_id: str, model_name: str, say, confirmed=False):
    if model_name not in openai_service.AVAILABLE_MODELS:
        say(f"<@{user_id}> Model '{model_name}' is not in AVAILABLE_MODELS.")
        return
    openai_service.DEFAULT_MODEL = model_name
    note = " (confirmed)" if confirmed else ""
    say(f"<@{user_id}> Updated model to '{model_name}'{note}.")

def handle_rollback(user_id: str, target: str, say, confirmed=False):
    try:
        rollback_to_tag(target)
        note = " (confirmed)" if confirmed else ""
        say(f"<@{user_id}> Rolled back to '{target}'{note}.")
    except Exception as e:
        say(f"Rollback failed: {e}")

def handle_upgrade(user_id: str, step: str, data: str, say):
    """
    Calls the self_upgrade logic for 'request', 'confirm', etc.
    """
    # map steps to the helper functions
    from plugins import self_upgrade

    # Example: step could be "request", "confirm", "new_code", "do_sanity", "finalize", "abort"
    step_lower = step.lower()
    if step_lower == "request":
        msg = self_upgrade.handle_request_upgrade(user_id, data)
        say(f"<@{user_id}> {msg}")
    elif step_lower == "confirm":
        msg = self_upgrade.handle_confirm_upgrade(user_id)
        say(f"<@{user_id}> {msg}")
    elif step_lower == "new_code":
        msg = self_upgrade.handle_new_code(user_id, data)
        say(f"<@{user_id}> {msg}")
    elif step_lower in ["do_sanity", "sanity", "do_sanity_check"]:
        msg = self_upgrade.handle_do_sanity_check(user_id)
        say(f"<@{user_id}> {msg}")
    elif step_lower == "finalize":
        msg = self_upgrade.handle_finalize_upgrade(user_id)
        say(f"<@{user_id}> {msg}")
    elif step_lower == "abort":
        msg = self_upgrade.handle_abort_upgrade(user_id)
        say(f"<@{user_id}> {msg}")
    else:
        say(f"<@{user_id}> Unrecognized upgrade step '{step}'. Try request, confirm, new_code, do_sanity, finalize, abort.")


def get_channel_name(app: App, channel_id: str) -> str:
    """
    Retrieves the Slack channel name for this channel_id (used for upgrade enforcement).
    """
    from slack_sdk import WebClient
    from slack_sdk.errors import SlackApiError
    token = os.environ.get("SLACK_BOT_TOKEN", "")
    client = WebClient(token=token)
    try:
        resp = client.conversations_info(channel=channel_id)
        return resp["channel"]["name"]
    except SlackApiError as e:
        logger.error(f"Error fetching channel info for {channel_id}: {e.response['error']}")
        return "unknown-channel"
