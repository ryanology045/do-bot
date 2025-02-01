# project_root/modules/coder_manager.py

import logging
from core.module_manager import BaseModule
from services.chatgpt_service import ChatGPTService

logger = logging.getLogger(__name__)

class CoderManager(BaseModule):
    """
    Handles snippet generation (via GPT) for complex tasks. Then hands off
    snippet code or function references to core/snippets.py for scheduling/execution.
    """
    module_name = "coder_manager"
    module_type = "CODER"

    def initialize(self):
        logger.info("[INIT] CoderManager initialized.")
        self.gpt_service = ChatGPTService()

    def generate_snippet(self, user_requirements):
        """
        Interact with GPT (CODER GPT) to produce a snippet (function code).
        Return a Python callable or raw code string that core/snippets.py can run.
        """
        logger.debug("[CODER] Generating snippet for user requirements: %s", user_requirements)

        # Build a specialized system prompt for CODER GPT:
        system_prompt = (
            "You are a coding assistant GPT. The user wants to generate a Python snippet or function.\n"
            "Return minimal, valid Python code as a string. If uncertain, ask clarifications.\n"
        )
        conversation = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_requirements}
        ]

        raw_response = self.gpt_service.chat_with_history(
            conversation=conversation,
            model="gpt-3.5-turbo",
            temperature=0.3
        )
        logger.debug("[CODER] Raw snippet from GPT:\n%s", raw_response)

        # In a real scenario, parse or validate the returned code. 
        # For demonstration, we just return the code as a string:
        return raw_response

    def create_snippet_callable(self, code_str):
        """
        Convert a code string into a callable function object (dangerous in real systems).
        For demonstration only. Real systems should sandbox or store code in a file.
        """
        local_env = {}
        try:
            exec(code_str, local_env)
        except Exception as e:
            logger.error("[CODER] Failed to exec snippet code: %s", e)
            return None

        # Suppose GPT defines a function 'generated_snippet'
        snippet_callable = local_env.get("generated_snippet")
        if not snippet_callable:
            logger.warning("[CODER] No function named 'generated_snippet' found in snippet.")
        return snippet_callable
