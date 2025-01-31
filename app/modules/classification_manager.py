# project_root/modules/classification_manager.py

import json
from core.module_manager import BaseModule
from services.chatgpt_service import ChatGPTService

class ClassificationManager(BaseModule):
    module_name = "classification_manager"
    module_type = "CLASSIFIER"

    def initialize(self):
        print("[INIT] ClassificationManager initialized.")
        self.gpt_service = ChatGPTService()
        self.classifier_conversation_history = []

    def handle_classification(self, user_text, user_id, channel, thread_ts):
        self.classifier_conversation_history.append({"role": "user", "content": user_text})

        system_prompt = (
            "You are a classification system with a persistent memory of prior user messages. "
            "For each new user message, decide if it's CONFIG_UPDATE, PRINT_CONFIG, or ASKTHEWORLD. "
            "If the user references a new role (e.g. 'Batman'), you can define it with 'new_role_prompt'. "
            "Output strictly valid JSON with keys: request_type, role_info, extra_data. Example:\n"
            "{\n"
            "  \"request_type\": \"ASKTHEWORLD\",\n"
            "  \"role_info\": \"Batman\",\n"
            "  \"extra_data\": {\n"
            "    \"new_role_prompt\": \"You are Batman...\",\n"
            "    \"role_temperature\": 0.5\n"
            "  }\n"
            "}\n"
        )

        conversation = [{"role": "system", "content": system_prompt}] + self.classifier_conversation_history
        raw_response = self.gpt_service.classify_chat(conversation)

        try:
            parsed = json.loads(raw_response)
            for key in ["request_type", "role_info", "extra_data"]:
                if key not in parsed:
                    raise ValueError(f"Missing {key} in GPT JSON.")
            self.classifier_conversation_history.append({"role": "assistant", "content": raw_response})
            return parsed
        except Exception as e:
            print(f"[ERROR] Classification JSON parse error: {e}")
            self.classifier_conversation_history.append({"role": "assistant", "content": "Fallback to ASKTHEWORLD."})
            return {
                "request_type": "ASKTHEWORLD",
                "role_info": "default",
                "extra_data": {}
            }
