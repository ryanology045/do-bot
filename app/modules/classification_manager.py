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
        logger.info("[INIT] ClassificationManager with single GPT session.")
        self.gpt_service = ChatGPTService()
        self.classifier_conversation = []

        classification_prompt = bot_config["initial_prompts"].get("classification_system_prompt","")
        big_context = bot_config["initial_prompts"].get("bot_context","")
        if not classification_prompt:
            classification_prompt = "You are a classification system. Return request_type in JSON."
        combined_prompt = classification_prompt.strip() + "\n\n" + big_context.strip()

        self.classifier_conversation.append({
            "role":"system",
            "content": combined_prompt
        })

    def handle_classification(self, user_text, user_id, channel, thread_ts):
        logger.debug("[CLASSIFIER] user_text='%s'", user_text)
        self.classifier_conversation.append({"role":"user","content":user_text})

        raw_response = self.gpt_service.classify_chat(self.classifier_conversation)
        logger.debug("[CLASSIFIER] raw => %s", raw_response)

        try:
            parsed = json.loads(raw_response)
            req_type = parsed.get("request_type","ASKTHEWORLD")
            role_info= parsed.get("role_info","default")
            extra_data=parsed.get("extra_data",{})

            # if CODER => optionally add relevant excerpt
            if req_type=="CODER":
                excerpt = self._extract_relevant_context(user_text)
                existing = extra_data.get("bot_knowledge","")
                extra_data["bot_knowledge"] = existing + "\n\n[Relevant Excerpt]\n\n" + excerpt

            final_result = {
                "request_type": req_type,
                "role_info": role_info,
                "extra_data": extra_data
            }

            self.classifier_conversation.append({
                "role":"assistant",
                "content": json.dumps(final_result)
            })
            logger.info("[CLASSIFIER] final => %s", final_result)
            return final_result

        except Exception as e:
            logger.error("[CLASSIFIER] parse error => %s", e, exc_info=True)
            fallback = {"request_type":"ASKTHEWORLD","role_info":"default","extra_data":{}}
            self.classifier_conversation.append({
                "role":"assistant",
                "content": "Error fallback => ASKTHEWORLD"
            })
            return fallback

    def review_snippet(self, snippet_prompt):
        """
        The second pass snippet review. 
        We rely on 'snippet_review_expanded' in config for added instructions.
        """
        logger.debug("[CLASSIFIER] review_snippet => length=%d", len(snippet_prompt))
        conv = [
            {
                "role":"system",
                "content":"You are Classification GPT. Summarize in plain language, no disclaimers."
            },
            {
                "role":"user",
                "content": snippet_prompt
            }
        ]
        raw_sum = self.gpt_service.classify_chat(conv)
        logger.debug("[CLASSIFIER] snippet summary => %s", raw_sum)
        return raw_sum

    def _extract_relevant_context(self, user_text):
        logger.debug("[CLASSIFIER] _extract_relevant_context => '%s'", user_text)
        extraction_prompt = (
            "Given the big context, only return lines relevant to the user's code or config request. Minimal. No disclaimers."
        )
        system_msg = self.classifier_conversation[0]["content"]

        conv = [
            {"role":"system","content":extraction_prompt},
            {"role":"user","content":f"BOT CONTEXT:\n{system_msg}\nUSER REQUEST:\n{user_text}"}
        ]
        raw = self.gpt_service.classify_chat(conv)
        logger.debug("[CLASSIFIER] relevant excerpt => %s", raw)
        return raw
