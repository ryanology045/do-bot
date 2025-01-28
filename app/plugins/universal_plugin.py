# plugins/universal_plugin.py

import os
import re
import logging
from slack_bolt import App
# If you use openai_service, import it:
from services.openai_service import AVAILABLE_MODELS, generate_response
# If you have a rate_limiting check:
from plugins.rate_limiting import rate_limit_check

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# Setup admin user IDs
admin_users_str = os.environ.get("ADMIN_USER_IDS", "")
ADMIN_USER_IDS = set(u.strip() for u in admin_users_str.split(",") if u.strip())

# Regex for add/remove model
MODEL_REGEX = re.compile(r"^(add|remove)\s+model\s+(?P<model>[\w-]+)$", re.IGNORECASE)

def register(app: App):
    @app.event("app_mention")
    def universal_app_mention(event, say):
        """
        A single event handler that merges:
          1) "add model / remove model" logic
          2) GPT-based or universal conversation logic
        """
        user_id = event.get("user")
        text = event.get("text", "")
        
        # Basic checks
        if not user_id or not text:
            logger.warning("app_mention with no user or text.")
            return

        # Remove Slack mention tokens <@U123ABC>
        mention_pattern = re.compile(r"<@[\w]+>")
        stripped_text = mention_pattern.sub("", text).strip()

        if not stripped_text:
            say(f"<@{user_id}> I'm listening, please provide a command or question.")
            return
        
        # 1) Check for add/remove model command
        match = MODEL_REGEX.match(stripped_text)
        if match:
            action = match.group(1).lower()  # 'add' or 'remove'
            model_name = match.group("model").lower()

            # Admin check
            if user_id not in ADMIN_USER_IDS:
                say(f"<@{user_id}> you do not have permission to perform this action.")
                logger.info(f"Non-admin {user_id} tried to {action} model '{model_name}'.")
                return

            if action == "add":
                if model_name in AVAILABLE_MODELS:
                    say(f"Model '{model_name}' is already available.")
                else:
                    AVAILABLE_MODELS.add(model_name)
                    say(f"Model '{model_name}' has been added.")
                logger.info(f"Admin {user_id} added model '{model_name}'.")
            elif action == "remove":
                if model_name not in AVAILABLE_MODELS:
                    say(f"Model '{model_name}' is not in AVAILABLE_MODELS.")
                else:
                    AVAILABLE_MODELS.remove(model_name)
                    say(f"Model '{model_name}' has been removed.")
                logger.info(f"Admin {user_id} removed model '{model_name}'.")
            
            # Return here so we don't do GPT logic below
            return
        
        # 2) If not an add/remove command, handle GPT or universal logic
        # Example GPT usage (similar to your old gpt_interaction.py logic)
        
        # Rate limiting example:
        if not rate_limit_check(user_id):
            say(f"<@{user_id}> You've hit the rate limit. Try again later.")
            return
        
        # Some sample parse: "/[modelType] /[instanceID] [prompt]"
        # If you still want that, or use a universal approach
        GPT_COMMAND_REGEX = re.compile(r"^\s*(?:/(?P<model>[\w-]+))?\s*(?:/(?P<inst>[\w-]+))?\s*(?P<prompt>.+)$", re.DOTALL)
        match_gpt = GPT_COMMAND_REGEX.match(stripped_text)
        if match_gpt:
            model = match_gpt.group("model") or "gpt-3.5-turbo"
            inst = match_gpt.group("inst") or "default"
            prompt = match_gpt.group("prompt").strip()
            
            # call generate_response
            try:
                reply = generate_response(model, inst, prompt)
                say(reply)
            except Exception as e:
                logger.error(f"GPT error: {e}")
                say("Sorry, something went wrong with GPT.")
        else:
            # fallback if the user didn't follow "/model /inst prompt" syntax
            # Or you can do a universal GPT approach
            say(f"<@{user_id}> I'm here! Please ask me something or use `/model /instance prompt`.")
