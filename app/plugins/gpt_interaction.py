# plugins/gpt_interaction.py
"""
Plugin for handling ChatGPT-like interactions via the OpenAI API.
Includes a queue for each "instance" to ensure sequential requests.
"""

import re
import logging
from slack_bolt import App
from slack_bolt.adapter.flask import SlackRequestHandler
from services.openai_service import ChatGPTSessionManager
from plugins.rate_limiting import rate_limit_check

def register(app: App):
    """
    Register GPT interaction event listeners with the given Slack Bolt app.
    
    Args:
        app (App): The Slack Bolt App instance to register event listeners with.
    """
    # Configure logger for this plugin
    logger = logging.getLogger(__name__)
    logger.setLevel(logging.INFO)
    
    # Regex to parse commands: "/[modelType] /[instanceID] [prompt]"
    COMMAND_REGEX = re.compile(r"^\s*[/]?(?P<model>[\w-]+)?\s*[/]?(?P<instance>[\w-]+)?\s*(?P<prompt>.+)$", re.DOTALL)
    
    @app.event("app_mention")
    def handle_app_mention_events(event, say, logger):
        """
        Handle 'app_mention' events from Slack.
        
        Args:
            event (dict): The event payload from Slack.
            say (function): Function to send messages back to Slack.
            logger (Logger): Logger instance for logging.
        """
        user_id = event.get("user")
        text = event.get("text", "")
        
        if not user_id or not text:
            logger.warning("Missing user_id or text in app_mention event.")
            return
        
        # Remove all bot mentions from the text
        # Slack mentions are in the format <@U12345678>
        mention_pattern = re.compile(r"<@[\w]+>")
        stripped_text = mention_pattern.sub("", text).strip()
        
        if not stripped_text:
            say(f"<@{user_id}>, please provide a command after mentioning me.")
            return
        
        # Rate limiting check
        if not rate_limit_check(user_id):
            say(f"<@{user_id}>, you've hit the rate limit. Try again later or request an admin override.")
            return
        
        # Parse the command structure
        match = COMMAND_REGEX.match(stripped_text)
        if not match:
            say("Could not parse GPT command. Use `/[modelType] /[instanceID] [prompt]` (some parts optional).")
            return
        
        model = match.group("model") if match.group("model") else "gpt-3.5-turbo"   # Default model
        instance_id = match.group("instance") if match.group("instance") else "default"
        prompt = match.group("prompt").strip()
        
        if not prompt:
            say("Please provide a prompt for me to process.")
            return
        
        logger.info(f"Received GPT request from user {user_id} with model '{model}', instance '{instance_id}', prompt '{prompt}'")
        
        # Process GPT request (queued by instance_id)
        try:
            reply = ChatGPTSessionManager.generate_response(model, instance_id, prompt)
        except Exception as e:
            logger.error(f"Error processing GPT request: {e}")
            say("Sorry, something went wrong while processing your request.")
            return
        
        # Send the result back to Slack
        say(reply)
