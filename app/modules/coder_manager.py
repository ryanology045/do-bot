# project_root/modules/coder_manager.py

import logging
from core.module_manager import BaseModule
from core.configs import bot_config
from services.chatgpt_service import ChatGPTService

logger = logging.getLogger(__name__)

class CoderManager(BaseModule):
    module_name = "coder_manager"
    module_type = "CODER"

    def initialize(self):
        logger.info("[INIT] CoderManager: uses coder_system_prompt + coder_safety_prompt.")
        self.gpt_service = ChatGPTService()

    def generate_snippet(self, user_requirements):
        logger.debug("[CODER_MANAGER] generate_snippet => %s", user_requirements)

        coder_prompt = bot_config["initial_prompts"].get("coder_system_prompt","")
        safety_prompt= bot_config["initial_prompts"].get("coder_safety_prompt","")

        if not coder_prompt:
            coder_prompt = "You are a Python code generator. Provide def generated_snippet(...)."
        # Append the safety prompt for event-driven snippet logic
        conversation = [
            {"role":"system","content": coder_prompt + "\n\n" + safety_prompt},
            {"role":"user","content": user_requirements}
        ]

        code_str = self.gpt_service.chat_with_history(
            conversation=conversation,
            model="gpt-3.5-turbo",
            temperature=0.3
        )
        logger.debug("[CODER_MANAGER] Raw snippet:\n%s", code_str)
        return code_str

    def create_snippet_callable(self, code_str):
        logger.debug("[CODER_MANAGER] create_snippet_callable => code_str length=%d", len(code_str))
        local_env = {}
        try:
            exec(code_str, local_env)
        except Exception as e:
            logger.error("[CODER_MANAGER] Exec snippet code error: %s", e)
            return None

        snippet_callable = local_env.get("generated_snippet")
        if not snippet_callable:
            logger.warning("[CODER_MANAGER] 'generated_snippet' not found in snippet code.")
        else:
            logger.info("[CODER_MANAGER] snippet_callable created successfully.")
        return snippet_callable
