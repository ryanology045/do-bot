# project_root/modules/askthebot_manager.py

import logging
from core.module_manager import BaseModule
from services.chatgpt_service import ChatGPTService

logger = logging.getLogger(__name__)

class AskTheBotManager(BaseModule):
    """
    Answers questions about the bot's internal architecture.
    """

    module_name = "askthebot_manager"
    module_type = "ASKTHEBOT"

    def initialize(self):
        logger.info("[INIT] AskTheBotManager initialized.")
        self.gpt_service = ChatGPTService()

    def handle_bot_question(self, user_text, user_id, channel, thread_ts):
        logger.debug("[ASKTHEBOT] handle_bot_question => user_text='%s', user_id='%s', channel='%s', thread_ts='%s'",
                     user_text, user_id, channel, thread_ts)

        system_prompt = (
            "You are an assistant that knows the Slackbot's internal modules, file structure, and usage. "
            "Provide helpful answers about the bot's design, referencing code or config if needed. "
            "Don't reveal sensitive credentials."
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
        logger.info("[ASKTHEBOT] Generated response for architecture Q: %s", response_text[:100] + "...")
        return response_text
