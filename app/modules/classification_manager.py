# project_root/modules/classification_manager.py

import json
import logging
from core.module_manager import BaseModule
from core.configs import bot_config
from services.chatgpt_service import ChatGPTService

logger = logging.getLogger(__name__)

class ClassificationManager(BaseModule):
    """
    Single global GPT session for classification. 
    1) On initialize, inject classification_system_prompt from config + the big bot_context once.
    2) handle_classification => decide request_type
    3) If CODER => do a second GPT call to extract relevant lines from bot_context => put in extra_data["bot_knowledge"].
    """

    module_name = "classification_manager"
    module_type = "CLASSIFIER"

    def initialize(self):
        logger.info("[INIT] ClassificationManager: single global GPT session.")
        self.gpt_service = ChatGPTService()
        # single global conversation for request_type classification
        self.classifier_conversation = []

        # Retrieve system prompt + context from config
        classification_prompt = bot_config["initial_prompts"].get("classification_system_prompt", "")
        full_bot_context = bot_config["initial_prompts"].get("bot_context", "")
        if not classification_prompt:
            logger.warning("[CLASSIFIER] classification_system_prompt missing, using minimal fallback.")
            classification_prompt = "You are a classification system. Return JSON: {request_type, role_info, extra_data}."
        if not full_bot_context:
            logger.warning("[CLASSIFIER] bot_context missing, fallback to 'No context'.")
            full_bot_context = "No extended context available..."

        # Combine them in one system message
        combined_system_msg = (
            f"{classification_prompt.strip()}\n\n"
            f"{full_bot_context.strip()}"
        )

        self.classifier_conversation.append({"role": "system", "content": combined_system_msg})
        logger.debug("[CLASSIFIER] Injected classification prompt & bot context at init.")

    def handle_classification(self, user_text, user_id, channel, thread_ts):
        logger.debug("[CLASSIFIER] handle_classification => user_text='%s'", user_text)

        # Step 1) Append user text
        self.classifier_conversation.append({"role": "user", "content": user_text})

        # Step 2) Classification GPT call
        raw_gpt_response = self.gpt_service.classify_chat(self.classifier_conversation)
        logger.debug("[CLASSIFIER] GPT raw output for classification: %s", raw_gpt_response)

        try:
            result = json.loads(raw_gpt_response)
            logger.debug("[CLASSIFIER] parsed JSON => %s", result)

            # Graceful fallback if missing
            request_type = result.get("request_type", "ASKTHEWORLD")
            role_info = result.get("role_info", "default")
            extra_data = result.get("extra_data", {})

            if request_type == "CODER":
                # We do a second GPT call to extract relevant lines from the big bot_context
                relevant_excerpt = self._extract_relevant_context(user_text)
                # merge with existing extra_data
                existing_know = extra_data.get("bot_knowledge", "")
                merged = f"{existing_know}\n\n[Relevant Excerpt Below]\n\n{relevant_excerpt}"
                extra_data["bot_knowledge"] = merged
                result["extra_data"] = extra_data
                logger.debug("[CLASSIFIER] Inserted relevant excerpt for CODER request.")

            # store final classification in conversation
            final_dict = {
                "request_type": request_type,
                "role_info": role_info,
                "extra_data": extra_data
            }
            final_json = json.dumps(final_dict)
            self.classifier_conversation.append({
                "role": "assistant",
                "content": final_json
            })

            logger.info("[CLASSIFIER] Final classification => %s", final_json)
            return final_dict

        except Exception as e:
            logger.error("[CLASSIFIER] parse error: %s", e, exc_info=True)
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

    def _extract_relevant_context(self, user_text):
        """
        A second GPT call to produce minimal lines from bot_context relevant to user_text.
        """
        logger.debug("[CLASSIFIER] _extract_relevant_context => user_text='%s'", user_text)

        extraction_prompt = (
            "Given the big context below, only return lines that are relevant to the user's code/config request. "
            "Keep it minimal. If user is referencing config, highlight config lines. If referencing modules, highlight them.\n"
            "No extra disclaimers, just the relevant lines. If nothing is relevant, return an empty string."
        )

        # We'll reuse 'classify_chat' for a quick single call
        # The system prompt is extraction_prompt, user content includes self.full_bot_context + user_text
        # We can grab the big context from the first system message in self.classifier_conversation
        system_content = self.classifier_conversation[0].get("content", "")
        extraction_conversation = [
            {"role": "system", "content": extraction_prompt},
            {"role": "user", "content": f"BOT CONTEXT:\n{system_content}\n\nUSER REQUEST:\n{user_text}"}
        ]

        raw_extraction = self.gpt_service.classify_chat(extraction_conversation)
        logger.debug("[CLASSIFIER] extraction raw => %s", raw_extraction)
        return raw_extraction
