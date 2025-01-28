# plugins/universal_app_mention.py
import os
import re
import logging
from slack_bolt import App

from plugins.rate_limiting import rate_limit_check
from services.openai_service import generate_response, AVAILABLE_MODELS
from services.github_service import rollback_to_tag, get_last_deployment_tag

# We import the self-upgrade helper functions
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

# Regex for model add/remove
MODEL_CMD_REGEX = re.compile(r"^(add|remove)\s+model\s+(?P<model>[\w-]+)$", re.IGNORECASE)

# Regex for rollback
ROLLBACK_LAST_REGEX = re.compile(r"^rollback\s+last$", re.IGNORECASE)
ROLLBACK_TO_REGEX = re.compile(r"^rollback\s+to\s+(?P<tag>[\w-]+)$", re.IGNORECASE)

# Regex for self-upgrade
REQUEST_UPGRADE_REGEX = re.compile(r"^request\s+upgrade\s*:\s*(?P<desc>.+)$", re.IGNORECASE)
CONFIRM_UPGRADE_REGEX = re.compile(r"^confirm\s+upgrade$", re.IGNORECASE)
NEW_CODE_REGEX = re.compile(r"^new\s+code\s*:\s*(?P<code>.+)$", re.IGNORECASE)
DO_SANITY_CHECK_REGEX = re.compile(r"^do\s+sanity\s+check$", re.IGNORECASE)
FINALIZE_UPGRADE_REGEX = re.compile(r"^finalize\s+upgrade$", re.IGNORECASE)
ABORT_UPGRADE_REGEX = re.compile(r"^abort\s+upgrade$", re.IGNORECASE)

UPGRADE_CHANNEL_NAME = "upgrade_channel_name"  # If you want to enforce a special channel

def register(app: App):
    @app.event("app_mention")
    def universal_app_mention(event, say):
        user_id = event.get("user")
        text = event.get("text", "")
        channel_id = event.get("channel", "")

        if not user_id or not text:
            return

        # Remove the mention token
        mention_pattern = re.compile(r"<@[\w]+>")
        stripped_text = mention_pattern.sub("", text).strip()
        if not stripped_text:
            say(f"<@{user_id}> Please provide a command or prompt.")
            return

        # Rate limit check
        if not rate_limit_check(user_id):
            say(f"<@{user_id}> You've hit the rate limit. Try again later.")
            return

        # 1) Model add/remove
        match_model = MODEL_CMD_REGEX.match(stripped_text)
        if match_model:
            action = match_model.group(1).lower()
            model_name = match_model.group("model").lower()
            if user_id not in ADMIN_USER_IDS:
                say(f"<@{user_id}> You do not have permission to manage models.")
                return
            if action == "add":
                if model_name in AVAILABLE_MODELS:
                    say(f"Model '{model_name}' is already available.")
                else:
                    AVAILABLE_MODELS.add(model_name)
                    say(f"Model '{model_name}' has been added.")
            else:  # remove
                if model_name not in AVAILABLE_MODELS:
                    say(f"Model '{model_name}' is not in AVAILABLE_MODELS.")
                else:
                    AVAILABLE_MODELS.remove(model_name)
                    say(f"Model '{model_name}' has been removed.")
            return

        # 2) Rollback
        if ROLLBACK_LAST_REGEX.match(stripped_text):
            if user_id not in ADMIN_USER_IDS:
                say(f"<@{user_id}> Not authorized to do rollback.")
                return
            try:
                tag = get_last_deployment_tag()
                rollback_to_tag(tag)
                say(f"Rolled back to {tag}")
            except Exception as e:
                say(f"Failed to rollback: {e}")
            return

        rb_match = ROLLBACK_TO_REGEX.match(stripped_text)
        if rb_match:
            if user_id not in ADMIN_USER_IDS:
                say(f"<@{user_id}> Not authorized to do rollback.")
                return
            target_tag = rb_match.group("tag")
            try:
                rollback_to_tag(target_tag)
                say(f"Rolled back to {target_tag}")
            except Exception as e:
                say(f"Failed to rollback to {target_tag}: {e}")
            return

        # 3) Self-upgrade commands
        channel_name = get_channel_name(app, channel_id)
        if "upgrade_channel_name".lower() in channel_name.lower():
            # request upgrade
            if REQUEST_UPGRADE_REGEX.match(stripped_text):
                handle_request_upgrade(event, say, logger, user_id, stripped_text)
                return
            elif CONFIRM_UPGRADE_REGEX.match(stripped_text):
                handle_confirm_upgrade(event, say, logger, user_id)
                return
            elif NEW_CODE_REGEX.match(stripped_text):
                handle_new_code(event, say, logger, user_id)
                return
            elif DO_SANITY_CHECK_REGEX.match(stripped_text):
                handle_do_sanity_check(event, say, logger, user_id)
                return
            elif FINALIZE_UPGRADE_REGEX.match(stripped_text):
                handle_finalize_upgrade(event, say, logger, user_id)
                return
            elif ABORT_UPGRADE_REGEX.match(stripped_text):
                handle_abort_upgrade(event, say, logger, user_id)
                return
            # else no recognized self-upgrade command => fallback GPT
        else:
            # If they tried "request upgrade" outside upgrade channel, block it
            if REQUEST_UPGRADE_REGEX.match(stripped_text):
                say(f"<@{user_id}> Upgrades must be requested in #{UPGRADE_CHANNEL_NAME}")
                return

        # 4) GPT fallback
        # parse "/model /instance prompt"
        GPT_CMD_REGEX = re.compile(r"^\s*(?:/(?P<model>[\w-]+))?\s*(?:/(?P<inst>[\w-]+))?\s*(?P<prompt>.+)$", re.DOTALL)
        gpt_match = GPT_CMD_REGEX.match(stripped_text)
        if gpt_match:
            model = gpt_match.group("model") or "gpt-3.5-turbo"
            inst = gpt_match.group("inst") or "default"
            prompt = gpt_match.group("prompt").strip()
            try:
                reply = generate_response(model, inst, prompt)
                say(f"<@{user_id}> {reply}")
            except Exception as e:
                logger.error(f"GPT fallback error: {e}")
                say(f"<@{user_id}> Sorry, GPT is having an issue: {e}")
        else:
            say(f"<@{user_id}> I'm here, but didn't recognize a command or prompt. "
                "Try `/gpt-3.5-turbo /default your question`, or `request upgrade: desc`, etc.")

def get_channel_name(app: App, channel_id: str) -> str:
    """
    Slack API call to fetch the channel name for the given ID.
    This helps enforce #upgrade_channel_name.
    """
    from slack_sdk import WebClient
    from slack_sdk.errors import SlackApiError
    client = WebClient(token=os.environ.get("SLACK_BOT_TOKEN"))
    try:
        resp = client.conversations_info(channel=channel_id)
        return resp["channel"]["name"]
    except SlackApiError as e:
        logger.error(f"Error fetching channel info {channel_id}: {e.response['error']}")
        return "unknown-channel"
