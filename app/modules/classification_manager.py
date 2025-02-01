# project_root/modules/classification_manager.py

import json
import logging
from core.module_manager import BaseModule
from core.configs import bot_config
from services.chatgpt_service import ChatGPTService

logger = logging.getLogger(__name__)

class ClassificationManager(BaseModule):
    """
    Single global GPT classification session for the entire Slackbot.
    - On init, we inject a large system prompt from bot_config['initial_prompts']['bot_context'].
    - All user messages from any Slack thread go into the same conversation.
    - If request_type=CODER => forcibly embed that context in extra_data['bot_knowledge'].
    """

    module_name = "classification_manager"
    module_type = "CLASSIFIER"

    def initialize(self):
        logger.info("[INIT] ClassificationManager: Initializing single global GPT session.")
        self.gpt_service = ChatGPTService()
        self.classifier_conversation = []

        # Retrieve the big context from configs
        full_bot_context = bot_config.get("initial_prompts", {}).get("bot_context", "")
        if not full_bot_context:
            logger.warning("[CLASSIFIER] No 'bot_context' found in bot_config['initial_prompts']. Using minimal fallback.")
            full_bot_context = "No extended bot context available..."

        system_prompt = (
            "You are the classification system for the entire Slackbot. Decide request_type among:\n"
            " - ASKTHEWORLD => normal Q&A\n"
            " - ASKTHEBOT => user wants architecture details\n"
            " - CODER => any code/config modifications.\n"
            "Output strictly valid JSON => {\"request_type\":\"...\",\"role_info\":\"...\",\"extra_data\":{}}\n\n"
            f"{full_bot_context}"
        )
        # Insert the big system prompt once at startup
        self.classifier_conversation.append({"role": "system", "content": system_prompt})
        logger.debug("[CLASSIFIER] System prompt injected on init: %s", system_prompt)

    def handle_classification(self, user_text, user_id, channel, thread_ts):
        logger.debug(
            "ClassificationManager.handle_classification => user_text='%s', user_id='%s', channel='%s', thread_ts='%s'",
            user_text, user_id, channel, thread_ts
        )

        # Append user text to the single global conversation
        self.classifier_conversation.append({"role": "user", "content": user_text})
        logger.debug("[CLASSIFIER] Updated conversation before GPT call: %s", self.classifier_conversation)

        # Call GPT for classification
        raw_gpt_response = self.gpt_service.classify_chat(self.classifier_conversation)
        logger.debug("[CLASSIFIER] GPT raw output: %s", raw_gpt_response)

        try:
            result = json.loads(raw_gpt_response)
            logger.debug("[CLASSIFIER] Parsed classification JSON: %s", result)

            # Ensure minimal structure
            for key in ["request_type", "role_info", "extra_data"]:
                if key not in result:
                    raise ValueError(f"Missing '{key}' in GPT JSON: {raw_gpt_response}")

            # If request_type=CODER => embed the full context into extra_data['bot_knowledge']
            if result["request_type"] == "CODER":
                # The first message in conversation is the system prompt with big context
                system_content = self.classifier_conversation[0].get("content", "")
                existing_knowledge = result["extra_data"].get("bot_knowledge", "")
                merged = f"{existing_knowledge}\n\n[Full Bot Context Below]\n\n{system_content}"
                result["extra_data"]["bot_knowledge"] = merged if existing_knowledge else system_content
                logger.debug("[CLASSIFIER] Forced 'bot_knowledge' merged with system prompt for CODER request.")

            # Store GPT's classification in conversation
            self.classifier_conversation.append({
                "role": "assistant",
                "content": json.dumps(result)
            })

            logger.info("[CLASSIFIER] Final classification => %s", result)
            return result

        except Exception as e:
            logger.error("[CLASSIFIER] Failed to parse classification JSON: %s", e, exc_info=True)
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
