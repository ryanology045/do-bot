# project_root/modules/askthebot_manager.py

import logging
from core.module_manager import BaseModule
from services.chatgpt_service import ChatGPTService

logger = logging.getLogger(__name__)

class AskTheBotManager(BaseModule):
    """
    Handles inquiries ABOUT the bot itself: architecture, roles, design, usage.
    This is invoked after classification if the user is specifically
    asking about the bot's internals or how it works.
    """
    module_name = "askthebot_manager"
    module_type = "ASKTHEBOT"

    def initialize(self):
        logger.info("[INIT] AskTheBotManager initialized.")
        self.gpt_service = ChatGPTService()

    def handle_bot_question(self, user_text, user_id, channel, thread_ts):
        """
        Provide answers about the bot's design, modules, usage, etc.
        """
        logger.debug("[ASKTHEBOT] Handling question about the bot: %s", user_text)

        # "Do not reveal confidential credentials." -> nuked for now
        
        system_prompt = (
            "You are an assistant that knows this Slackbot's architecture, modules, roles, gating, etc. "
            "Answer the user's questions about how the bot is built or how it works. "
        )
        conversation = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_text}
        ]

        response_text = self.gpt_service.chat_with_history(
            conversation=conversation,
            model="gpt-3.5-turbo",
            temperature=0.6
        )
        return response_text
