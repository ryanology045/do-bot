# project_root/modules/coder_manager.py

import logging
from core.module_manager import BaseModule
from services.chatgpt_service import ChatGPTService

logger = logging.getLogger(__name__)

class CoderManager(BaseModule):
    """
    For advanced code snippet generation or config changes => CODER GPT.
    """

    module_name = "coder_manager"
    module_type = "CODER"

    def initialize(self):
        logger.info("[INIT] CoderManager initialized.")
        self.gpt_service = ChatGPTService()

    def generate_snippet(self, user_requirements):
        """
        Interact with GPT in coder capacity, returning a code string.
        """
        logger.debug("[CODER_MANAGER] generate_snippet => user_requirements='%s'", user_requirements)
        system_prompt = (
            "You are a coding-oriented GPT. The user wants a Python code snippet or function. "
            "Return minimal, valid code. If you need to clarify, you can indicate so. "
            "Any advanced changes to the bot must reference the existing file structure or config usage."
        )
        conversation = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_requirements}
        ]

        code_str = self.gpt_service.chat_with_history(
            conversation=conversation,
            model="gpt-3.5-turbo",
            temperature=0.3
        )
        logger.debug("[CODER_MANAGER] Raw snippet code from GPT:\n%s", code_str)
        return code_str

    def create_snippet_callable(self, code_str):
        """
        Convert code_str into a Python callable.
        Expects function named 'generated_snippet'.
        """
        logger.debug("[CODER_MANAGER] create_snippet_callable => code_str length=%d", len(code_str))
        local_env = {}
        try:
            exec(code_str, local_env)
        except Exception as e:
            logger.error("[CODER_MANAGER] Failed to exec snippet code: %s", e)
            return None

        snippet_callable = local_env.get("generated_snippet")
        if not snippet_callable:
            logger.warning("[CODER_MANAGER] The snippet code does not define 'generated_snippet'.")
        else:
            logger.info("[CODER_MANAGER] snippet_callable created successfully.")
        return snippet_callable
