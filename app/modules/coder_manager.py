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
        logger.info("[INIT] CoderManager initialized.")
        self.gpt_service = ChatGPTService()

    def generate_snippet(self, user_requirements):
        logger.debug("[CODER_MANAGER] generate_snippet => user_requirements='%s'", user_requirements)

        coder_prompt = bot_config["initial_prompts"].get("coder_system_prompt", "")
        if not coder_prompt:
            logger.warning("[CODER_MANAGER] coder_system_prompt missing. Using fallback.")
            coder_prompt = "You are a Python code generator. Return def generated_snippet(channel, thread_ts): code."

        conversation = [
            {"role": "system", "content": coder_prompt},
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
        logger.debug("[CODER_MANAGER] create_snippet_callable => code_str length=%d", len(code_str))
        local_env = {}
        try:
            exec(code_str, local_env)
        except Exception as e:
            logger.error("[CODER_MANAGER] Failed to exec snippet code: %s", e)
            return None

        snippet_callable = local_env.get("generated_snippet")
        if not snippet_callable:
            logger.warning("[CODER_MANAGER] snippet code does not define 'generated_snippet'.")
        else:
            logger.info("[CODER_MANAGER] snippet_callable created successfully.")
        return snippet_callable

    def review_snippet(self, snippet_text):
        """
        Reuses GPT to provide a short summary or 'sanity check' of the snippet code.
        """
        # Could be a small chat or classification call
        logger.debug("[CODER_MANAGER] review_snippet => snippet_text length=%d", len(snippet_text))

        # For simplicity, we do a single message call
        response = self.gpt_service.classify_chat([
            {"role": "system", "content": "You are a snippet reviewer. Summarize what the code does."},
            {"role": "user", "content": snippet_text}
        ])
        # 'classify_chat' or 'chat_with_history' depends on your chatgpt_service
        logger.debug("[CODER_MANAGER] Snippet review output: %s", response)
        return response
