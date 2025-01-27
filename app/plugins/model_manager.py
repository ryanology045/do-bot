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
    
    Args:
        app (App): The Slack Bolt App instance to register event listeners with.
    """
    logger = logging.getLogger(__name__)
    logger.setLevel(logging.INFO)
    
    # Retrieve admin user IDs from environment variable (comma-separated)
    ADMIN_USER_IDS = os.environ.get("ADMIN_USER_IDS", "")
    ADMIN_USER_IDS = set(uid.strip() for uid in ADMIN_USER_IDS.split(",") if uid.strip())
    
    if not ADMIN_USER_IDS:
        logger.warning("No ADMIN_USER_IDS defined. Only the bot itself can perform admin actions.")
    
    # Regex to parse commands: "add model <model_name>" or "remove model <model_name>"
    COMMAND_REGEX = re.compile(r"^(add|remove)\s+model\s+(?P<model>[\w-]+)$", re.IGNORECASE)
    
    @app.event("app_mention")
    def handle_app_mention_events(event, say, logger):
        """
        Handle 'app_mention' events from Slack.
        Parses commands to add or remove GPT models.
        
        Expected command format:
            - "@BotName add model gpt-4"
            - "@BotName remove model gpt-3.5-turbo"
        
        Args:
            event (dict): The event payload from Slack.
            say (function): Function to send messages back to Slack.
            logger (Logger): Logger instance for logging.
        """
        user_id = event.get("user")
        text = event.get("text", "")
        
        if not user_id or not text:
            logger.warning("Received app_mention event without user ID or text.")
            return
        
        # Remove all bot mentions from the text
        # Slack mentions are in the format <@U12345678>
        mention_pattern = re.compile(r"<@[\w]+>")
        stripped_text = mention_pattern.sub("", text).strip()
        
        if not stripped_text:
            say(f"<@{user_id}>, please provide a command after mentioning me.")
            return
        
        # Parse the command using regex
        match = COMMAND_REGEX.match(stripped_text)
        if not match:
            say("Could not parse command. Use `add model <model_name>` or `remove model <model_name>`.")
            return
        
        action = match.group(1).lower()
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
                return
            AVAILABLE_MODELS.add(model_name)
            say(f"Model '{model_name}' has been added to the available models.")
            logger.info(f"Admin {user_id} added model '{model_name}'.")
        
        elif action == "remove":
            if model_name not in AVAILABLE_MODELS:
                say(f"Model '{model_name}' is not available.")
                logger.info(f"Admin {user_id} attempted to remove non-existent model '{model_name}'.")
                return
            AVAILABLE_MODELS.remove(model_name)
            say(f"Model '{model_name}' has been removed from the available models.")
            logger.info(f"Admin {user_id} removed model '{model_name}'.")
