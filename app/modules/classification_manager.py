# project_root/modules/classification_manager.py

import json
import logging
from core.module_manager import BaseModule
from core.configs import bot_config
from services.chatgpt_service import ChatGPTService

logger = logging.getLogger(__name__)

class ClassificationManager(BaseModule):
    """
    Single global GPT classification session. 
    If request_type=CODER => we do a second GPT call to 
    extract only the "relevant" pieces of the bot_context.
    """

    module_name = "classification_manager"
    module_type = "CLASSIFIER"

    def initialize(self):
        logger.info("[INIT] ClassificationManager: single global GPT session.")
        self.gpt_service = ChatGPTService()
        # Entire classification conversation (for request_type detection)
        self.classifier_conversation = []

        # The big bot context from configs
        self.full_bot_context = bot_config.get("initial_prompts", {}).get("bot_context", "")
        if not self.full_bot_context:
            logger.warning("[CLASSIFIER] No 'bot_context' found in config. Using minimal fallback.")
            self.full_bot_context = "No extended context available..."

        # Insert the system prompt with the big context once at startup
        system_prompt = (
            "You are the classification system for the entire Slackbot. "
            "Decide: ASKTHEWORLD | ASKTHEBOT | CODER. Output strictly valid JSON. \n\n"
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

        # 2) Classification GPT call
        logger.debug("[CLASSIFIER] classification conversation (pre-call): %s", self.classifier_conversation)
        raw_gpt_response = self.gpt_service.classify_chat(self.classifier_conversation)
        logger.debug("[CLASSIFIER] GPT raw output for classification: %s", raw_gpt_response)

        try:
            result = json.loads(raw_gpt_response)
            logger.debug("[CLASSIFIER] Parsed classification JSON: %s", result)

            for key in ["request_type", "role_info", "extra_data"]:
                if key not in result:
                    raise ValueError(f"Missing '{key}' in GPT JSON: {raw_gpt_response}")

            # store classification
            self.classifier_conversation.append({
                "role": "assistant",
                "content": json.dumps(result)
            })

            # 3) If request_type=CODER => do a second GPT call to extract only relevant snippet from self.full_bot_context
            if result["request_type"] == "CODER":
                # We'll do a minimal approach:
                relevant_context = self._extract_relevant_context(user_text)
                # Merge with whatever GPT put in extra_data['bot_knowledge']
                existing_knowledge = result["extra_data"].get("bot_knowledge", "")
                # Final knowledge
                merged = f"{existing_knowledge}\n\n[Relevant Bot Context Excerpt Below]\n\n{relevant_context}"
                # set it
                result["extra_data"]["bot_knowledge"] = merged
                logger.debug("[CLASSIFIER] Inserted relevant context snippet for coder request.")

            logger.info("[CLASSIFIER] Final classification => %s", result)
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

    def _extract_relevant_context(self, user_text):
        """
        A second GPT call that tries to produce a minimal snippet of self.full_bot_context
        relevant to user_text. Example approach:
        1) system prompt: "Given the big context below, only return the lines relevant to user_text."
        2) user prompt: "context: ... user_text: ..."

        In production, you might do a semantic search or chunk-based approach. This is a naive GPT approach.
        """
        logger.debug("[CLASSIFIER] _extract_relevant_context => user_text='%s'", user_text)

        # Build a conversation for the "context extraction" GPT call
        extraction_prompt = (
            "You have the following big context about the bot. The user has a code/config request. "
            "Return ONLY the lines or sections from the context that are directly relevant to the user's request. "
            "If the user is talking about config, mention the config portion. If about modules, mention that module. "
            "Keep it minimal—no extra details."
        )

        extraction_conversation = [
            {"role": "system", "content": extraction_prompt},
            {"role": "user", "content": f"BOT CONTEXT:\n{self.full_bot_context}\n\nUSER REQUEST:\n{user_text}"}
        ]

        raw_response = self.gpt_service.classify_chat(extraction_conversation)
        logger.debug("[CLASSIFIER] GPT raw output for relevant context extraction: %s", raw_response)

        # We assume GPT returns a snippet. We do no further JSON parse, just take raw text as the snippet.
        return raw_response
