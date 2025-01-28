# plugins/universal_app_mention.py

import os
import json
import re
import logging
import openai
from slack_bolt import App

from plugins.rate_limiting import rate_limit_check
from services.openai_service import (
    AVAILABLE_MODELS,
    DEFAULT_MODEL
)
from services.github_service import rollback_to_tag, get_last_deployment_tag
from plugins.self_upgrade import (
    handle_request_upgrade,
    handle_confirm_upgrade,
    handle_new_code,
    handle_do_sanity_check,
    handle_finalize_upgrade,
    handle_abort_upgrade
)

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

ADMIN_USER_IDS = set(uid.strip() for uid in os.environ.get("ADMIN_USER_IDS", "").split(",") if uid.strip())

UPGRADE_CHANNEL_NAME = "bot-upgrades"

# Temporary in-memory confirmations
PENDING_CONFIRMATIONS = {}

SYSTEM_PROMPT = """\
You are a Slackbot that interprets the user's mention with NO hard-coded regex, 
and produces exactly one JSON snippet in the format:

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

1) "set model to X" => action="update_model", model_name="X"
2) "rollback last" => action="rollback", rollback_target="last"
3) self-upgrade => action="upgrade", upgrade_step=...
4) normal chat => action="chat" or "none"
5) if request is risky => "confirmation_needed": true
Place normal text in "message_for_user". 
No disclaimers about "cannot" do something—just produce the snippet.
"""

def register(app: App):
    @app.event("app_mention")
    def universal_app_mention(event, say):
        """
        Single GPT-based approach: 
        1) If user typed "yes," handle pending confirmations. 
        2) Otherwise, call GPT for a JSON snippet describing the user's request.
        3) Parse & perform that action. 
        4) Also print the raw JSON snippet in Slack.
        """
        user_id = event.get("user", "")
        text = event.get("text", "").strip()
        channel_id = event.get("channel", "")

        if not user_id or not text:
            return

        # Rate limit check
        if not rate_limit_check(user_id):
            say(f"<@{user_id}> You've hit the rate limit. Try again later.")
            return

        # If user typed "yes," see if there's a pending confirmation
        if text.lower() == "yes":
            if user_id in PENDING_CONFIRMATIONS:
                pending_action, pending_data = PENDING_CONFIRMATIONS.pop(user_id)
                _handle_confirmed_action(user_id, pending_action, pending_data, say)
                return

        # Otherwise, do a single GPT call 
        gpt_answer = _call_gpt_with_prompt(text)

        # Extract the JSON snippet
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

        json_part = None
        if start_idx != -1 and end_idx != -1 and end_idx > start_idx:
            json_part = gpt_answer[start_idx + len(start_tag):end_idx].strip()
            user_facing_text = (
                gpt_answer[:start_idx] + gpt_answer[end_idx + len(end_tag):]
            ).strip()
            # Attempt to parse
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
                logger.warning(f"Could not parse GPT JSON block: {e}")

        # Print the raw JSON snippet in Slack
        if json_part:
            say(f"<@{user_id}> **GPT JSON snippet**:\n```json\n{json_part}\n```")

        # Combine leftover text with "message_for_user"
        final_text = user_facing_text
        if message_for_user.strip():
            if final_text.strip():
                final_text += "\n" + message_for_user
            else:
                final_text = message_for_user

        # Show user-facing text
        if final_text.strip():
            say(f"<@{user_id}> {final_text}")

        # Perform action
        if action == "update_model":
            if user_id not in ADMIN_USER_IDS:
                say(f"<@{user_id}> Not authorized to update model.")
                return
            if confirmation_needed:
                PENDING_CONFIRMATIONS[user_id] = ("update_model", model_name)
                say(f"<@{user_id}> Type 'yes' to confirm updating model to '{model_name}'.")
            else:
                _handle_update_model(user_id, model_name, say)

        elif action == "rollback":
            if user_id not in ADMIN_USER_IDS:
                say(f"<@{user_id}> Not authorized for rollback.")
                return
            if not rollback_target:
                say(f"<@{user_id}> No rollback target found.")
                return
            if confirmation_needed:
                PENDING_CONFIRMATIONS[user_id] = ("rollback", rollback_target)
                say(f"<@{user_id}> Type 'yes' to confirm rollback to '{rollback_target}'.")
            else:
                _handle_rollback(user_id, rollback_target, say)

        elif action == "upgrade":
            # Check channel if you want to restrict
            channel_name = get_channel_name(app, channel_id)
            if UPGRADE_CHANNEL_NAME.lower() not in channel_name.lower():
                say(f"<@{user_id}> Upgrades must be in #{UPGRADE_CHANNEL_NAME} channel.")
                return
            # handle the step
            _handle_upgrade_step(user_id, upgrade_step, upgrade_data, say)

        else:
            # "none" or "chat" => do nothing special
            pass

def _call_gpt_with_prompt(user_text: str) -> str:
    """
    Single call to GPT with the system prompt => returns the entire answer (with JSON snippet).
    """
    try:
        response = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",  # or "gpt-4"
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_text}
            ],
            temperature=0.7
        )
        return response["choices"][0]["message"]["content"].strip()
    except Exception as e:
        logger.error(f"Error calling GPT: {e}")
        return f"GPT error: {e}"

def _handle_confirmed_action(user_id: str, pending_action: str, pending_data: str, say):
    if pending_action == "update_model":
        _handle_update_model(user_id, pending_data, say, confirmed=True)
    elif pending_action == "rollback":
        _handle_rollback(user_id, pending_data, say, confirmed=True)
    else:
        say(f"<@{user_id}> Unknown action '{pending_action}' for confirmation.")

def _handle_update_model(user_id: str, model_name: str, say, confirmed=False):
    if model_name not in AVAILABLE_MODELS:
        say(f"<@{user_id}> Model '{model_name}' isn't recognized.")
        return
    global DEFAULT_MODEL
    DEFAULT_MODEL = model_name
    c_note = " (confirmed)" if confirmed else ""
    say(f"<@{user_id}> Updated model to '{model_name}'{c_note}.")

def _handle_rollback(user_id: str, target: str, say, confirmed=False):
    try:
        rollback_to_tag(target)
        c_note = " (confirmed)" if confirmed else ""
        say(f"<@{user_id}> Rolled back to '{target}'{c_note}.")
    except Exception as e:
        say(f"Rollback error: {e}")

def _handle_upgrade_step(user_id: str, step: str, data: str, say):
    """
    Delegates to self_upgrade helper functions
    """
    from plugins import self_upgrade
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
        say(f"<@{user_id}> Unrecognized upgrade step '{step}'. Use request, confirm, new_code, do_sanity, finalize, abort.")

def get_channel_name(app: App, channel_id: str) -> str:
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
