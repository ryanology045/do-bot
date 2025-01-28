# plugins/role_manager.py
"""
Plugin that allows a user to define or update the bot's "role"
for ChatGPT prompts (system message). 
"""

import re
import logging
from slack_bolt import App
import services.openai_service as openai_svc

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# Example regex for "set role to <some text>"
SET_ROLE_REGEX = re.compile(r"(?i)\bset\s+role\s+to\s+(.*)$", re.IGNORECASE)

def register(app: App):
    @app.message(SET_ROLE_REGEX)
    def handle_set_role(message, say):
        """
        Usage: 
        '@BotName set role to You are a Python expert specialized in concurrency...'
        """
        user_id = message.get("user", "")
        text = message.get("text", "")
        match = SET_ROLE_REGEX.search(text)
        if not match:
            return
        new_role = match.group(1).strip()
        # Update the global BOT_ROLE used by openai_service
        openai_svc.BOT_ROLE = new_role
        logger.info(f"User {user_id} set the bot's role to: {new_role}")
        say(f"<@{user_id}> Got it! My role is now:\n```{new_role}```")

    @app.message(re.compile(r"(?i)\bwhat\s+is\s+your\s+role\??"))
    def handle_get_role(message, say):
        """
        Usage:
        '@BotName what is your role?'
        """
        user_id = message.get("user", "")
        current_role = openai_svc.BOT_ROLE
        say(f"<@{user_id}>, my current role is:\n```{current_role}```")
