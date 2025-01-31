# project_root/modules/asktheworld_manager.py

from core.module_manager import BaseModule
from services.chatgpt_service import ChatGPTService
from services.slack_service import SlackService

class AskTheWorldManager(BaseModule):
    module_name = "asktheworld_manager"
    module_type = "ASKTHEWORLD"

    def initialize(self):
        print("[INIT] AskTheWorldManager initialized.")
        self.gpt_service = ChatGPTService()
        self.slack_post_client = SlackService().slack_post_client
        self.thread_conversations = {}  # Slack thread_ts -> conversation list

    def handle_inquiry(self, user_text, system_prompt, temperature, user_id, channel, thread_ts):
        conv = self.thread_conversations.get(thread_ts)
        if not conv:
            conv = [{"role": "system", "content": system_prompt}]

        conv.append({"role": "user", "content": user_text})

        response_text = self.gpt_service.chat_with_history(
            conversation=conv,
            model="gpt-3.5-turbo",  # or from bot_config["default_qna_model"]
            temperature=temperature
        )

        conv.append({"role": "assistant", "content": response_text})
        self.thread_conversations[thread_ts] = conv

        # Post answer to Slack
        self.slack_post_client.post_message(channel=channel, text=response_text, thread_ts=thread_ts)
