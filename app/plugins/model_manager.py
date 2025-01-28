# plugins/model_manager.py
"""
Plugin to dynamically add/remove GPT model references.
Only admins can add or remove models.
"""

import re
import logging
import os
from slack_bolt import App
from services.openai_service import AVAILABLE_MODELS

def register(app: App):
    """
    Register the Model Manager plugin with the given Slack Bolt app.
    
    This plugin only handles commands like:
      - "@BotName add model <model_name>"
      - "@BotName remove model <model_name>"
    If the text doesn't match, we simply 'return' without responding
    and do not produce an error or fallback message.
    """
    logger = logging.getLogger(__name__)
    logger.setLevel(logging.INFO)
    
    # Retrieve admin user IDs from environment variable (comma-separated)
    admin_users_str = os.environ.get("ADMIN_USER_IDS", "")
    ADMIN_USER_IDS = set(uid.strip() for uid in admin_users_str.split(",") if uid.strip())
    
    if not ADMIN_USER_IDS:
        logger.warning("No ADMIN_USER_IDS defined. Only the bot itself can perform admin actions.")
    
    # Regex to parse commands: "add model <model_name>" or "remove model <model_name>"
    COMMAND_REGEX = re.compile(r"^(add|remove)\s+model\s+(?P<model>[\w-]+)$", re.IGNORECASE)
    
    @app.event("app_mention")
    def handle_model_commands(event, say, logger):
        """
        Handle 'app_mention' events from Slack. 
        Only processes commands to add or remove GPT models.
        
        Expected commands:
            - "@BotName add model gpt-4"
            - "@BotName remove model gpt-3.5-turbo"
        
        If the text doesn't match this pattern, we do nothing (return),
        allowing other handlers to process the event if they wish.
        """
        user_id = event.get("user")
        text = event.get("text", "")
        
        if not user_id or not text:
            logger.warning("Received app_mention event without user_id or text.")
            return  # Do nothing, no errors
        
        # Remove all bot mentions from the text
        mention_pattern = re.compile(r"<@[\w]+>")
        stripped_text = mention_pattern.sub("", text).strip()
        
        if not stripped_text:
            # Not actually a command, do nothing
            return
        
        # Check if the text matches "add model ..." or "remove model ..."
        match = COMMAND_REGEX.match(stripped_text)
        if not match:
            # If it doesn't match, do nothing (no error message),
            # so other handlers can process the mention.
            return
        
        action = match.group(1).lower()   # 'add' or 'remove'
        model_name = match.group("model").lower()
        
        # Check if the user is an admin
        if user_id not in ADMIN_USER_IDS:
            say(f"<@{user_id}>, you do not have permission to perform this action.")
            logger.info(f"Unauthorized user {user_id} attempted to {action} model '{model_name}'.")
            return
        
        if action == "add":
            if model_name in AVAILABLE_MODELS:
                say(f"Model '{model_name}' is already available.")
                logger.info(f"Admin {user_id} attempted to add existing model '{model_name}'.")
            else:
                AVAILABLE_MODELS.add(model_name)
                say(f"Model '{model_name}' has been added to the available models.")
                logger.info(f"Admin {user_id} added model '{model_name}'.")
        
        elif action == "remove":
            if model_name not in AVAILABLE_MODELS:
                say(f"Model '{model_name}' is not available.")
                logger.info(f"Admin {user_id} attempted to remove non-existent model '{model_name}'.")
            else:
                AVAILABLE_MODELS.remove(model_name)
                say(f"Model '{model_name}' has been removed from the available models.")
                logger.info(f"Admin {user_id} removed model '{model_name}'.")
