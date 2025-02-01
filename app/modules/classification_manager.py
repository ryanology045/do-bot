# project_root/modules/classification_manager.py

import json
import logging
from core.module_manager import BaseModule
from core.configs import bot_config
from services.chatgpt_service import ChatGPTService

logger = logging.getLogger(__name__)

class ClassificationManager(BaseModule):
    """
    Single global GPT classification session. If GPT returns partial JSON,
    we fallback to default role_info='default' or extra_data={}, etc.
    """

    module_name = "classification_manager"
    module_type = "CLASSIFIER"

    def initialize(self):
        logger.info("[INIT] ClassificationManager: single global GPT session.")
        self.gpt_service = ChatGPTService()
        self.classifier_conversation = []

        # The big bot context from configs
        self.full_bot_context = bot_config.get("initial_prompts", {}).get("bot_context", "")
        if not self.full_bot_context:
            logger.warning("[CLASSIFIER] No 'bot_context' found in config. Using minimal fallback.")
            self.full_bot_context = "No extended context available..."

        system_prompt = (
            "You are the classification system for the entire Slackbot. "
            "Decide among: ASKTHEWORLD, ASKTHEBOT, CODER. Output strictly valid JSON. \n\n"
            f"{self.full_bot_context}"
        )
        self.classifier_conversation.append({"role": "system", "content": system_prompt})
        logger.debug("[CLASSIFIER] Injected big context system prompt on init.")

    def handle_classification(self, user_text, user_id, channel, thread_ts):
        logger.debug(
            "[CLASSIFIER] handle_classification => user_text='%s', user_id='%s', channel='%s', thread_ts='%s'",
            user_text, user_id, channel, thread_ts
        )

        # 1) Append user text
        self.classifier_conversation.append({"role": "user", "content": user_text})
        logger.debug("[CLASSIFIER] classification conversation (pre-call): %s", self.classifier_conversation)

        # 2) GPT classification
        raw_gpt_response = self.gpt_service.classify_chat(self.classifier_conversation)
        logger.debug("[CLASSIFIER] GPT raw output for classification: %s", raw_gpt_response)

        try:
            result = json.loads(raw_gpt_response)
            logger.debug("[CLASSIFIER] Parsed classification JSON: %s", result)

            # Gracefully fallback if keys are missing
            request_type = result.get("request_type", "ASKTHEWORLD")
            role_info = result.get("role_info", "default")
            extra_data = result.get("extra_data", {})

            # If GPT didn't supply them at all, we set them ourselves
            if "request_type" not in result:
                logger.warning("[CLASSIFIER] GPT omitted 'request_type'. Defaulting to 'ASKTHEWORLD'")
            if "role_info" not in result:
                logger.warning("[CLASSIFIER] GPT omitted 'role_info'. Defaulting to 'default'")
            if "extra_data" not in result:
                logger.warning("[CLASSIFIER] GPT omitted 'extra_data'. Using empty {}")

            # Overwrite result dict with safe values
            result["request_type"] = request_type
            result["role_info"] = role_info
            result["extra_data"] = extra_data

            # If request_type=CODER => forcibly embed full_bot_context in extra_data['bot_knowledge']
            if request_type == "CODER":
                existing_knowledge = extra_data.get("bot_knowledge", "")
                merged = f"{existing_knowledge}\n\n[Full Bot Context Below]\n\n{self.full_bot_context}"
                result["extra_data"]["bot_knowledge"] = merged
                logger.debug("[CLASSIFIER] Inserted full context snippet for CODER request.")

            # 3) Store final classification in conversation
            final_json = json.dumps(result)
            self.classifier_conversation.append({
                "role": "assistant",
                "content": final_json
            })
            logger.info("[CLASSIFIER] Final classification => %s", final_json)
            return result

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
