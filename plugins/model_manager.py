# plugins/model_manager.py
"""
Plugin to dynamically add/remove GPT model references.
"""

from slack_bolt import App
from core.slack_app import app
from services.openai_service import AVAILABLE_MODELS

@app.message("add model")
def add_model(message, say):
    """
    Usage: "@BotName add model gpt-4"
    """
    text = message.get('text', '')
    parts = text.split()
    if len(parts) < 4:
        say("Usage: '@BotName add model <model_name>'")
        return
    model_name = parts[-1]
    if model_name in AVAILABLE_MODELS:
        say(f"Model '{model_name}' is already available.")
        return
    AVAILABLE_MODELS.add(model_name)
    say(f"Model '{model_name}' added to available models.")

@app.message("remove model")
def remove_model(message, say):
    """
    Usage: "@BotName remove model gpt-3.5-turbo"
    """
    text = message.get('text', '')
    parts = text.split()
    if len(parts) < 4:
        say("Usage: '@BotName remove model <model_name>'")
        return
    model_name = parts[-1]
    if model_name not in AVAILABLE_MODELS:
        say(f"Model '{model_name}' not found in available models.")
        return
    AVAILABLE_MODELS.remove(model_name)
    say(f"Model '{model_name}' removed from available models.")
