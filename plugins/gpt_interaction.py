# plugins/gpt_interaction.py
"""
Plugin for handling ChatGPT-like interactions via the OpenAI API.
Includes a queue for each "instance" to ensure sequential requests.
"""

import re
from slack_bolt import App
from services.openai_service import ChatGPTSessionManager
from plugins.rate_limiting import rate_limit_check

from core.slack_app import app

# If referencing via mention: "@BotName /[modelType] /[instanceID] [prompt]"
COMMAND_REGEX = re.compile(r"^\s*[/]?(?P<model>[\w-]+)?\s*[/]?(?P<instance>[\w-]+)?\s*(?P<prompt>.*)$", re.DOTALL)

@app.message("")
def handle_gpt_command(message, say, context):
    """
    Catch all messages where the bot is mentioned.
    We'll parse if it's a GPT command.
    Slack Bolt automatically filters out messages that do not mention the bot if installed with "app_mention" event,
    but we use a generic approach for demonstration.
    """
    # Check if the message starts with a mention of the bot
    bot_user_id = context['bot_user_id']  # Slack Bolt provides the bot's user ID
    text = message.get('text', '')
    if not text or f"<@{bot_user_id}>" not in text:
        return  # Not mentioning the bot
    
    # Remove the mention part
    stripped_text = text.replace(f"<@{bot_user_id}>", "").strip()
    
    # Rate limiting check
    user_id = message['user']
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
    
    # Process GPT request (queued by instance_id)
    reply = ChatGPTSessionManager.process_request(model, instance_id, prompt)
    
    # Send the result back
    say(reply)
