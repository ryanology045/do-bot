# plugins/override_commands.py
import logging
from slack_bolt import App
import services.openai_service as openai_service
from plugins.slash_command_directory import register_slash_command

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

_OVERRIDE_ACTIVE = False
_OLD_ROLE = None
_OLD_TEMP = None

admin_ids_str = os.environ.get("ADMIN_USER_IDS", "")
# Split by commas, strip whitespace, and put into a set
ADMIN_USER_IDS = set(x.strip() for x in admin_ids_str.split(",") if x.strip())

def register(app: App):
    # 1) Register slash commands in Slack Bolt
    @app.command("/override_role")
    def override_role_command(ack, say, command):
        ack()
        user_id = command.get("user_id", "")
        if user_id not in ADMIN_USER_IDS:
            say("Sorry, you're not authorized to override the bot's role.")
            return

        global _OVERRIDE_ACTIVE, _OLD_ROLE, _OLD_TEMP
        if not _OVERRIDE_ACTIVE:
            _OLD_ROLE = openai_service.BOT_ROLE
            _OLD_TEMP = openai_service.BOT_TEMPERATURE

        openai_service.BOT_ROLE = "You are a helpful assistant. Always respond to code/config queries."
        openai_service.BOT_TEMPERATURE = 0.7
        _OVERRIDE_ACTIVE = True

        say("**OVERRIDE ACTIVE**: BOT_ROLE and BOT_TEMPERATURE reset to safe defaults.")

    @app.command("/cancel_override")
    def cancel_override_command(ack, say, command):
        ack()
        user_id = command.get("user_id", "")
        if user_id not in ADMIN_USER_IDS:
            say("Sorry, you're not authorized to cancel the override.")
            return

        global _OVERRIDE_ACTIVE, _OLD_ROLE, _OLD_TEMP
        if not _OVERRIDE_ACTIVE:
            say("No override is currently active.")
            return

        openai_service.BOT_ROLE = _OLD_ROLE
        openai_service.BOT_TEMPERATURE = _OLD_TEMP
        _OVERRIDE_ACTIVE = False

        say("Override canceled. Restored previous BOT_ROLE and BOT_TEMPERATURE.")

    # 2) Also register the slash commands in the aggregator
    register_slash_command("/override_role", "Resets the bot's role to safe defaults (Admin only).")
    register_slash_command("/cancel_override", "Cancels the override and reverts previous role config.")
