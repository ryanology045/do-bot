# project_root/modules/classification_manager.py

import json
import logging
from core.module_manager import BaseModule
from services.chatgpt_service import ChatGPTService

logger = logging.getLogger(__name__)

class ClassificationManager(BaseModule):
    """
    This module classifies inbound Slack messages into:
      - CONFIG_UPDATE
      - PRINT_CONFIG
      - ASKTHEWORLD

    It also can detect references to new roles (e.g., 'Batman') and
    propose a 'new_role_prompt' and 'role_temperature' in extra_data.

    The conversation with GPT is persistent across messages, so
    GPT can remember prior user contexts or role references over time.
    """
    module_name = "classification_manager"
    module_type = "CLASSIFIER"

    def initialize(self):
        """
        Called once when the module is loaded by ModuleManager.
        """
        logger.info("[INIT] ClassificationManager initialized.")
        self.gpt_service = ChatGPTService()
        # Store all classification messages in one global conversation
        self.classifier_conversation_history = []

    def handle_classification(self, user_text, user_id, channel, thread_ts):
        """
        1. Appends the user's message to our persistent classifier conversation.
        2. Calls GPT with a system prompt explaining the classification scheme:
           - 'CONFIG_UPDATE' if they're updating something.
           - 'PRINT_CONFIG' if they want to see config values.
           - 'ASKTHEWORLD' otherwise (general Q&A).
        3. GPT should return JSON like:
           {
             "request_type": "ASKTHEWORLD" | "CONFIG_UPDATE" | "PRINT_CONFIG",
             "role_info": "Batman" | "friendly" | "default" | ...
             "extra_data": {
               "new_role_prompt": "...",
               "role_temperature": 0.5,
               ...
             }
           }
        4. Logs debug info and returns the parsed result.
        5. Falls back to {"request_type": "ASKTHEWORLD", "role_info": "default", ...}
           if GPT fails or the JSON is invalid.
        """
        logger.debug(
            "ClassificationManager.handle_classification called with user_text='%s', "
            "user_id='%s', channel='%s', thread_ts='%s'",
            user_text, user_id, channel, thread_ts
        )

        # 1) Append the user's latest text to conversation
        self.classifier_conversation_history.append({"role": "user", "content": user_text})

        # 2) Build a system prompt explaining how GPT must return request_type, role_info, extra_data
        system_prompt = (
            "You are a classification system with persistent memory of prior user messages. "
            "For each new user message, determine if the request is:\n"
            " - CONFIG_UPDATE (user wants to update or set config/roles),\n"
            " - PRINT_CONFIG (user wants to see config),\n"
            " - ASKTHEWORLD (any other request for Q&A).\n\n"
            "Additionally, if the user references a new role (e.g. 'Batman'), you can provide:\n"
            "  \"role_info\": \"Batman\",\n"
            "  and in extra_data, set \"new_role_prompt\" and \"role_temperature\" if you want.\n\n"
            "You MUST output strictly valid JSON with keys:\n"
            "  request_type, role_info, extra_data.\n"
            "If uncertain, default to:\n"
            "  {\"request_type\": \"ASKTHEWORLD\", \"role_info\": \"default\", \"extra_data\": {}}"
        )

        # Merge system prompt + conversation
        conversation = [{"role": "system", "content": system_prompt}] + self.classifier_conversation_history

        # 3) Call GPT for classification
        logger.debug("Calling GPT classify_chat with conversation: %s", conversation)
        raw_gpt_response = self.gpt_service.classify_chat(conversation)
        logger.debug("Classifier GPT raw output: %s", raw_gpt_response)

        # 4) Parse JSON result
        try:
            result = json.loads(raw_gpt_response)
            logger.debug("Parsed classification JSON: %s", result)

            # Minimal structure check
            for key in ["request_type", "role_info", "extra_data"]:
                if key not in result:
                    raise ValueError(f"Missing key '{key}' in GPT JSON.")

            # If parse is successful, store GPT's raw response in conversation
            self.classifier_conversation_history.append({
                "role": "assistant",
                "content": raw_gpt_response
            })

            return result

        except Exception as e:
            logger.error("Failed to parse classification JSON: %s", e, exc_info=True)
            # Fallback to ASKTHEWORLD
            fallback_result = {
                "request_type": "ASKTHEWORLD",
                "role_info": "default",
                "extra_data": {}
            }
            self.classifier_conversation_history.append({
                "role": "assistant",
                "content": "Error fallback => ASKTHEWORLD"
            })
            return fallback_result
