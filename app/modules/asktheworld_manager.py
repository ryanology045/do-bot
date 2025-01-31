# project_root/modules/asktheworld_manager.py

from core.module_manager import BaseModule
from services.gpt_service import GPTService
from services.slack_service.slack_adapter import SlackPostClient

class AskTheWorldManager(BaseModule):
    module_name = "asktheworld_manager"
    module_type = "ASKTHEWORLD"

    def initialize(self):
        print("[INIT] AskTheWorldManager initialized.")
        self.gpt_service = GPTService()
        self.slack_post_client = SlackPostClient()
        self.thread_conversations = {}  # thread_ts -> list of conversation messages

    def handle_inquiry(self, user_text, system_prompt, temperature, user_id, channel, thread_ts):
        conversation = self.thread_conversations.get(thread_ts)
        if not conversation:
            conversation = [{"role": "system", "content": system_prompt}]

        # Add user's message
        conversation.append({"role": "user", "content": user_text})

        response_text = self.gpt_service.chat_with_history(
            conversation, model="gpt-3.5-turbo", temperature=temperature
        )

        conversation.append({"role": "assistant", "content": response_text})
        self.thread_conversations[thread_ts] = conversation

        # Post to Slack
        self.slack_post_client.post_message(channel=channel, text=response_text, thread_ts=thread_ts)
