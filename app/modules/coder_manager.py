# project_root/modules/coder_manager.py

import logging
from core.module_manager import BaseModule
from services.chatgpt_service import ChatGPTService

logger = logging.getLogger(__name__)

class CoderManager(BaseModule):
    """
    Handles snippet generation (via CODER GPT) for complex dev tasks,
    passing results to core/snippets for execution if needed.
    """
    module_name = "coder_manager"
    module_type = "CODER"

    def initialize(self):
        logger.info("[INIT] CoderManager initialized.")
        self.gpt_service = ChatGPTService()

    def generate_snippet(self, user_requirements):
        """
        Interact with GPT in a 'CODER' capacity to produce code snippets or functions.
        Return a code string.
        """
        logger.debug("[CODER] Generating snippet for requirements: %s", user_requirements)

        system_prompt = (
            "You are a coding-oriented GPT. User wants a Python code snippet or function. "
            "Return minimal, valid code as a string. If uncertain, ask clarifications."
        )
        conversation = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_requirements}
        ]

        raw_snippet = self.gpt_service.chat_with_history(
            conversation=conversation,
            model="gpt-3.5-turbo",
            temperature=0.3
        )
        logger.debug("[CODER] Raw snippet code:\n%s", raw_snippet)
        return raw_snippet

    def create_snippet_callable(self, code_str):
        """
        Convert the code string into a callable. This is a naive approach using exec.
        Expects the snippet to define a function named 'generated_snippet'.
        """
        local_env = {}
        try:
            exec(code_str, local_env)
        except Exception as e:
            logger.error("[CODER] Failed to exec snippet code: %s", e)
            return None

        snippet_callable = local_env.get("generated_snippet")
        if not snippet_callable:
            logger.warning("[CODER] The snippet code does not define 'generated_snippet' function.")
        return snippet_callable
