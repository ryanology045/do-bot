# project_root/modules/classification_manager.py

import json
from core.module_manager import BaseModule
from services.gpt_service import GPTService

class ClassificationManager(BaseModule):
    module_name = "classification_manager"
    module_type = "CLASSIFIER"

    def initialize(self):
        print("[INIT] ClassificationManager initialized.")
        self.gpt_service = GPTService()
        self.classifier_conversation_history = []  # persistent across all classification calls

    def handle_classification(self, user_text, user_id, channel, thread_ts):
        """
        Expects GPT to return valid JSON with {request_type, role_info, extra_data}.
        """
        self.classifier_conversation_history.append({"role": "user", "content": user_text})

        system_prompt = (
            "You are a classification system with persistent memory. "
            "For the incoming user message, decide if it is a 'CONFIG_UPDATE', 'PRINT_CONFIG', or 'ASKTHEWORLD'. "
            "Also set 'role_info' (like 'friendly', 'professional', or 'default'), "
            "and fill 'extra_data' if user wants to set new_model, update role prompts, etc.\n"
            "Output strictly valid JSON with keys: request_type, role_info, extra_data.\n"
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
            print(f"[ERROR] Classification parse error: {e}")
            self.classifier_conversation_history.append({"role": "assistant", "content": "Fallback to ASKTHEWORLD."})
            return {
                "request_type": "ASKTHEWORLD",
                "role_info": "default",
                "extra_data": {}
            }
