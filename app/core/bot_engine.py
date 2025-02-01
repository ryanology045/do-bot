# project_root/core/bot_engine.py

from .configs import bot_config
from .module_manager import ModuleManager

class BotEngine:
    """
    Slack event orchestrator:
      - Classification => request_type = ASKTHEWORLD / ASKTHEBOT / CODER
      - CODER => coder flow
      - ASKTHEBOT => askthebot_manager
      - else => normal Q&A
    """

    def __init__(self):
        self.module_manager = ModuleManager()
        self.module_manager.load_modules()
        self.personality_manager = self.module_manager.get_module("personality_manager")

    def handle_incoming_slack_event(self, event_data):
        user_text = event_data.get("text", "")
        channel = event_data.get("channel")
        thread_ts = event_data.get("thread_ts") or event_data.get("ts")
        user_id = event_data.get("user")

        classifier = self.module_manager.get_module_by_type("CLASSIFIER")
        if not classifier:
            print("[ERROR] classification_manager not found.")
            return

        classification_result = classifier.handle_classification(
            user_text=user_text,
            user_id=user_id,
            channel=channel,
            thread_ts=thread_ts
        )
        request_type = classification_result.get("request_type", "ASKTHEWORLD")
        role_info = classification_result.get("role_info", "default")
        extra_data = classification_result.get("extra_data", {})

        # Possibly register new roles if GPT invented them
        self._maybe_register_new_role(role_info, extra_data, user_text, channel, thread_ts)

        if request_type == "ASKTHEBOT":
            self._handle_askthebot(user_text, user_id, channel, thread_ts)
        elif request_type == "CODER":
            self._handle_coder_flow(user_text, channel, thread_ts, extra_data)
        else:
            # default => normal Q&A
            self._handle_asktheworld_flow(user_text, role_info, extra_data, channel, thread_ts)

    def _maybe_register_new_role(self, role_info, extra_data, user_text, channel, thread_ts):
        """
        If GPT creates a brand-new role, store it in bot_config. 
        Then optionally persist it with coder manager if you want advanced logic.
        """
        roles_def = bot_config["roles_definitions"]
        if role_info not in roles_def:
            new_prompt = extra_data.get("new_role_prompt")
            new_temp = extra_data.get("role_temperature")
            if new_prompt:
                roles_def[role_info] = {
                    "system_prompt": new_prompt,
                    "temperature": new_temp if new_temp is not None else 0.7,
                    "description": f"Dynamically created role: {role_info}"
                }
                self._run_new_role_snippet(role_info, new_prompt, new_temp, user_text, channel, thread_ts)

    def _run_new_role_snippet(self, role_name, role_prompt, role_temp, user_text, channel, thread_ts):
        coder_manager = self.module_manager.get_module("coder_manager")
        if not coder_manager:
            print("[ERROR] coder_manager not found. Can't persist new role code.")
            return

        coder_input = (
            f"The user invented a new role '{role_name}' with prompt:\n{role_prompt}\n"
            f"temperature={role_temp}. Provide code snippet to store this role in code.\n"
        )
        code_str = coder_manager.generate_snippet(coder_input)
        snippet_callable = coder_manager.create_snippet_callable(code_str)
        if snippet_callable:
            from core.snippets import SnippetsRunner
            sr = SnippetsRunner()
            sr.run_snippet_now(snippet_callable)

            from services.slack_service import SlackService
            SlackService().post_message(
                channel=channel,
                text=f"Role '{role_name}' snippet executed for code persistence.",
                thread_ts=thread_ts
            )

    def _handle_askthebot(self, user_text, user_id, channel, thread_ts):
        askbot = self.module_manager.get_module("askthebot_manager")
        if not askbot:
            print("[ERROR] askthebot_manager not found.")
            return
        response_text = askbot.handle_bot_question(user_text, user_id, channel, thread_ts)

        from services.slack_service import SlackService
        SlackService().post_message(channel=channel, text=response_text, thread_ts=thread_ts)

    def _handle_coder_flow(self, user_text, channel, thread_ts, extra_data):
        coder_manager = self.module_manager.get_module("coder_manager")
        if not coder_manager:
            print("[ERROR] coder_manager not found.")
            return

        from services.slack_service import SlackService
        slack_service = SlackService()

        bot_knowledge = extra_data.get("bot_knowledge", "")
        coder_input = user_text
        if bot_knowledge:
            coder_input += f"\n\n[Bot Knowledge]: {bot_knowledge}"

        snippet_code = coder_manager.generate_snippet(coder_input)
        snippet_callable = coder_manager.create_snippet_callable(snippet_code)
        if snippet_callable:
            from core.snippets import SnippetsRunner
            sr = SnippetsRunner()
            sr.run_snippet_now(snippet_callable)
            slack_service.post_message(channel=channel, text="Code snippet executed successfully.", thread_ts=thread_ts)
        else:
            slack_service.post_message(channel=channel, text="Failed to generate snippet code.", thread_ts=thread_ts)

    def _handle_asktheworld_flow(self, user_text, role_info, extra_data, channel, thread_ts):
        asktheworld = self.module_manager.get_module_by_type("ASKTHEWORLD")
        if not asktheworld:
            print("[ERROR] asktheworld_manager not found.")
            return

        role_temp = extra_data.get("role_temperature")
        system_prompt, default_temp = self.personality_manager.get_system_prompt_and_temp(role_info)
        temperature = role_temp if role_temp is not None else default_temp

        asktheworld.handle_inquiry(
            user_text=user_text,
            system_prompt=system_prompt,
            temperature=temperature,
            user_id=None,
            channel=channel,
            thread_ts=thread_ts
        )
