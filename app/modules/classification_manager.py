import json
import logging
from core.module_manager import BaseModule
from core.configs import bot_config
from services.chatgpt_service import ChatGPTService

logger = logging.getLogger(__name__)

class ClassificationManager(BaseModule):
    """
    SINGLE global classification GPT session for the entire Slackbot.
    - On initialize(), we inject a big 'Full Bot Context' system prompt ONCE.
    - Every classification call, we append user text to this single conversation.
    - If GPT says request_type=CODER, we forcibly embed that same context in extra_data['bot_knowledge'].
    - Potentially large memory usage. 'Cold honesty': any user can push the conversation in unexpected directions. 
    """

    module_name = "classification_manager"
    module_type = "CLASSIFIER"

    def initialize(self):
        logger.info("[INIT] ClassificationManager initialized.")
        self.gpt_service = ChatGPTService()
        # A single global conversation
        self.classifier_conversation = []

        # Insert a big system prompt with full context at BOT STARTUP
        full_bot_context = bot_config.get("initial_prompts", {}).get("bot_context", "")
        if not full_bot_context:
            full_bot_context = (
                "No expanded context found in bot_config['initial_prompts']['bot_context'].\n"
                "Using minimal fallback."
            )
        system_prompt = (
            "You are the classification system for this entire Slackbot session. "
            "All code or config requests => CODER. If user is asking about the bot's internal design => ASKTHEBOT. "
            "Otherwise => ASKTHEWORLD. Strictly output JSON => {\"request_type\":\"...\",\"role_info\":\"...\",\"extra_data\":{}}.\n\n"
            f"{full_bot_context}"
        )
        self.classifier_conversation.append({"role": "system", "content": system_prompt})

    def handle_classification(self, user_text, user_id, channel, thread_ts):
        """
        1) Append user text to the single global conversation.
        2) Call GPT for classification. 
        3) If request_type=CODER => forcibly embed the full context in extra_data['bot_knowledge'].
        4) Return the classification JSON.
        """
        logger.debug(
            "ClassificationManager.handle_classification => user_text='%s', user_id='%s', channel='%s', thread_ts='%s'",
            user_text, user_id, channel, thread_ts
        )

        # Step 1: Append user text to the single global conversation
        self.classifier_conversation.append({"role": "user", "content": user_text})

        # Step 2: GPT classification
        logger.debug("Calling GPT classify_chat with conversation: %s", self.classifier_conversation)
        raw_gpt_response = self.gpt_service.classify_chat(self.classifier_conversation)
        logger.debug("Classifier GPT raw output: %s", raw_gpt_response)

        try:
            result = json.loads(raw_gpt_response)
            logger.debug("Parsed classification JSON: %s", result)

            for key in ["request_type", "role_info", "extra_data"]:
                if key not in result:
                    raise ValueError(f"Missing '{key}' in GPT JSON.")

            # If request_type=CODER => forcibly embed the same full_bot_context 
            # from the system prompt. We'll retrieve from the first message's content if needed:
            if result["request_type"] == "CODER":
                # The first message in the classifier_conversation is system content:
                if len(self.classifier_conversation) > 0:
                    system_content = self.classifier_conversation[0].get("content", "")
                    # We assume that is our "big context" (though it's not a perfect extraction)
                    if "bot_knowledge" not in result["extra_data"]:
                        result["extra_data"]["bot_knowledge"] = system_content
                    else:
                        existing = result["extra_data"]["bot_knowledge"]
                        merged = f"{existing}\n\n[Full Bot Context Below]\n\n{system_content}"
                        result["extra_data"]["bot_knowledge"] = merged

            # Step 3: Store GPT's final classification in the conversation
            self.classifier_conversation.append({
                "role": "assistant",
                "content": json.dumps(result)
            })

            return result

        except Exception as e:
            logger.error("Failed to parse classification JSON: %s", e, exc_info=True)
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
