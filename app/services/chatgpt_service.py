# project_root/services/chatgpt_service.py

import os
import openai
import logging

logger = logging.getLogger(__name__)

class ChatGPTService:
    """
    Handles ChatGPT calls for both classification and Q&A with conversation history.
    """

    def __init__(self):
        self.api_key = os.environ.get("OPENAI_API_KEY")
        if not self.api_key:
            raise ValueError("OPENAI_API_KEY not set.")
        openai.api_key = self.api_key

    def classify_chat(self, conversation):
        """
        Used by classification_manager. Usually temperature=0.0 for deterministic JSON.
        'conversation' is a list of messages (role='system'|'user'|'assistant').
        """
        try:
            response = openai.ChatCompletion.create(
                model="gpt-3.5-turbo",
                messages=conversation,
                temperature=0.0,
                max_tokens=300
            )
            return response["choices"][0]["message"]["content"]
        except Exception as e:
            logger.error(f"ChatGPT classify_chat error: {e}")
            return """{"request_type":"ASKTHEWORLD","role_info":"default","extra_data":{}}"""

    def chat_with_history(self, conversation, model="gpt-3.5-turbo", temperature=0.7):
        """
        For the 'AskTheWorld' Q&A manager. 'conversation' is a list of
        dicts with roles: 'system', 'user', 'assistant'.
        """
        try:
            response = openai.ChatCompletion.create(
                model=model,
                messages=conversation,
                temperature=temperature,
                max_tokens=800
            )
            return response["choices"][0]["message"]["content"]
        except Exception as e:
            logger.error(f"ChatGPT chat_with_history error: {e}")
            return "I'm having trouble responding right now."
