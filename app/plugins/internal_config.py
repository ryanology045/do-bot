# plugins/internal_config.py
"""
Plugin to answer questions about internal configuration values,
like available GPT models or other internal states.
"""

import re
import logging
from slack_bolt import App
from services.openai_service import AVAILABLE_MODELS

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

CONFIG_QUERY_REGEX = re.compile(
    r"(?i)\b(what|which)\s+(?:are|is)\s+(?:the\s+)?(gpt models|models you support|available models)\??",
    re.IGNORECASE
)

def register(app: App):
    @app.message(CONFIG_QUERY_REGEX)
    def handle_config_query(message, say):
        """
        Respond to queries like:
        '@BotName what are the gpt models you support?'
        """
        user_id = message.get("user", "")
        # Convert the set of models to a string list
        models_list = "\n".join(sorted(AVAILABLE_MODELS))
        response_text = (
            f"Here are the GPT models I currently support:\n```\n{models_list}\n```"
        )
        say(f"<@{user_id}> {response_text}")
