# project_root/modules/classification_manager.py

import json
import logging

from core.module_manager import BaseModule
from core.configs import bot_config
from services.chatgpt_service import ChatGPTService

logger = logging.getLogger(__name__)

class ClassificationManager(BaseModule):
    module_name = "classification_manager"
    module_type = "CLASSIFIER"

    def initialize(self):
        logger.info("[INIT] ClassificationManager: single GPT session for classification.")
        self.gpt_service = ChatGPTService()
        self.classifier_conversation = []

        classification_prompt = bot_config["initial_prompts"].get("classification_system_prompt","")
        big_context = bot_config["initial_prompts"].get("bot_context","")

        if not classification_prompt:
            classification_prompt = "You are a classification system. Return {request_type, role_info, extra_data}."
            logger.warning("[CLASSIFIER] Missing classification_system_prompt, fallback used.")
        if not big_context:
            big_context = "No extended context"
            logger.warning("[CLASSIFIER] Missing bot_context, fallback used.")

        combined_prompt = classification_prompt.strip() + "\n\n" + big_context.strip()
        self.classifier_conversation.append({"role": "system", "content": combined_prompt})

    def handle_classification(self, user_text, user_id, channel, thread_ts):
        logger.debug("[CLASSIFIER] user_text='%s'", user_text)
        self.classifier_conversation.append({"role": "user", "content": user_text})

        raw_classification = self.gpt_service.classify_chat(self.classifier_conversation)
        logger.debug("[CLASSIFIER] raw classification => %s", raw_classification)

        try:
            result = json.loads(raw_classification)
            logger.debug("[CLASSIFIER] parsed => %s", result)

            request_type = result.get("request_type","ASKTHEWORLD")
            role_info   = result.get("role_info","default")
            extra_data  = result.get("extra_data",{})

            if request_type == "CODER":
                excerpt = self._extract_relevant_context(user_text)
                exi = extra_data.get("bot_knowledge","")
                extra_data["bot_knowledge"] = exi + "\n\n[Relevant Excerpt]\n\n" + excerpt

            final = {
                "request_type": request_type,
                "role_info": role_info,
                "extra_data": extra_data
            }
            self.classifier_conversation.append({
                "role": "assistant",
                "content": json.dumps(final)
            })
            logger.info("[CLASSIFIER] final => %s", final)
            return final

        except Exception as e:
            logger.error("[CLASSIFIER] parse error => %s", e, exc_info=True)
            fallback = {
                "request_type": "ASKTHEWORLD",
                "role_info": "default",
                "extra_data": {}
            }
            self.classifier_conversation.append({
                "role": "assistant",
                "content": "Error fallback => ASKTHEWORLD"
            })
            return fallback

    def review_snippet(self, snippet_prompt):
        """
        Second pass snippet review also done by Classification GPT.
        """
        logger.debug("[CLASSIFIER] review_snippet => snippet_prompt length=%d", len(snippet_prompt))
        conv = [
            {
                "role": "system",
                "content": "You are the Classification GPT with full context. Summarize snippet in plain language, no disclaimers."
            },
            {
                "role": "user",
                "content": snippet_prompt
            }
        ]
        raw = self.gpt_service.classify_chat(conv)
        logger.debug("[CLASSIFIER] snippet review => %s", raw)
        return raw

    def _extract_relevant_context(self, user_text):
        logger.debug("[CLASSIFIER] _extract_relevant_context => '%s'", user_text)
        extraction_prompt = (
            "Given the big context, only return lines relevant to the user's code or config request. Minimal, no disclaimers."
        )
        sys_msg = self.classifier_conversation[0].get("content","")

        conv = [
            {"role":"system","content":extraction_prompt},
            {"role":"user","content":f"BOT CONTEXT:\n{sys_msg}\n\nUSER REQUEST:\n{user_text}"}
        ]
        raw_extract = self.gpt_service.classify_chat(conv)
        logger.debug("[CLASSIFIER] relevant excerpt => %s", raw_extract)
        return raw_extract
