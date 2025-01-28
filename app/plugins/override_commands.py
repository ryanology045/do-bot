# plugins/override_commands.py

import logging
from slack_bolt import App
from openai_service import BOT_ROLE, BOT_TEMPERATURE  # We'll reassign these, so be mindful of "global" usage
import openai_service

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# Track override state
_OVERRIDE_ACTIVE = False
_OLD_ROLE = None
_OLD_TEMP = None

# Example: If you have an admin list in env, or define it here
ADMIN_USER_IDS = {"U123ABC", "U456DEF"}  # Slack user IDs of admins

def register(app: App):
    @app.command("/override_role")
    def override_role_command(ack, say, command):
        """
        Force the bot to reset to safe default config, bypassing any user-defined role that may be blocking.
        """
        ack()  # Acknowledge the slash command immediately

        user_id = command.get("user_id", "")
        if user_id not in ADMIN_USER_IDS:
            say("Sorry, you're not authorized to override the bot's role.")
            return

        global _OVERRIDE_ACTIVE, _OLD_ROLE, _OLD_TEMP
        global openai_service

        if not _OVERRIDE_ACTIVE:
            # Store old values before overriding
            _OLD_ROLE = openai_service.BOT_ROLE
            _OLD_TEMP = openai_service.BOT_TEMPERATURE

        # Set the override defaults
        openai_service.BOT_ROLE = "You are a helpful assistant. Always respond to code/config queries."
        openai_service.BOT_TEMPERATURE = 0.7

        _OVERRIDE_ACTIVE = True
        say("**OVERRIDE ACTIVE**: BOT_ROLE and BOT_TEMPERATURE have been reset to safe defaults.\n"
            "Use `/cancel_override` to revert to the previous config.")

    @app.command("/cancel_override")
    def cancel_override_command(ack, say, command):
        """
        Revert the bot's configuration back to what it was before /override_role.
        """
        ack()
        user_id = command.get("user_id", "")
        if user_id not in ADMIN_USER_IDS:
            say("Sorry, you're not authorized to cancel the override.")
            return

        global _OVERRIDE_ACTIVE, _OLD_ROLE, _OLD_TEMP
        global openai_service

        if not _OVERRIDE_ACTIVE:
            say("No override is active.")
            return

        # Revert to old values
        openai_service.BOT_ROLE = _OLD_ROLE
        openai_service.BOT_TEMPERATURE = _OLD_TEMP

        _OVERRIDE_ACTIVE = False
        say("Override canceled. BOT_ROLE and BOT_TEMPERATURE reverted to previous values.")
