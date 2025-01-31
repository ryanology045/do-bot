# project_root/core/bot_engine.py

from .configs import bot_config
from .module_manager import ModuleManager

class BotEngine:
    def __init__(self):
        self.module_manager = ModuleManager()
        self.module_manager.load_modules()
        self.personality_manager = self.module_manager.get_module("personality_manager")

    def handle_incoming_slack_event(self, event_data):
        user_text = event_data.get("text", "")
        channel = event_data.get("channel")
        thread_ts = event_data.get("thread_ts") or event_data.get("ts")
        user_id = event_data.get("user")

        # Classify
        classifier_module = self.module_manager.get_module_by_type("CLASSIFIER")
        if not classifier_module:
            print("[ERROR] classification_manager not found.")
            return
        classification_result = classifier_module.handle_classification(
            user_text=user_text, user_id=user_id, channel=channel, thread_ts=thread_ts
        )

        request_type = classification_result.get("request_type", "ASKTHEWORLD")
        role_info = classification_result.get("role_info", "default")
        extra_data = classification_result.get("extra_data", {})

        if request_type == "CONFIG_UPDATE":
            self._handle_config_update(extra_data, channel, thread_ts)
        elif request_type == "PRINT_CONFIG":
            self._handle_print_config(channel, thread_ts)
        else:
            # Q&A
            asktheworld_module = self.module_manager.get_module_by_type("ASKTHEWORLD")
            if not asktheworld_module:
                print("[ERROR] asktheworld_manager not found.")
                return

            role_temp = extra_data.get("role_temperature")
            system_prompt, default_temp = self.personality_manager.get_system_prompt_and_temp(role_info)
            temperature = role_temp if role_temp is not None else default_temp

            asktheworld_module.handle_inquiry(
                user_text=user_text,
                system_prompt=system_prompt,
                temperature=temperature,
                user_id=user_id,
                channel=channel,
                thread_ts=thread_ts
            )

    def _handle_config_update(self, extra_data, channel, thread_ts):
        from services.slack_service.slack_adapter import SlackPostClient
        spc = SlackPostClient()

        updated_something = False

        new_model = extra_data.get("new_model")
        if new_model:
            bot_config["default_qna_model"] = new_model
            updated_something = True

        role_to_update = extra_data.get("role_to_update")
        if role_to_update:
            roles_def = bot_config.get("roles_definitions", {})
            if role_to_update in roles_def:
                if "new_role_temp" in extra_data:
                    roles_def[role_to_update]["temperature"] = extra_data["new_role_temp"]
                    updated_something = True
                if "new_role_prompt" in extra_data:
                    roles_def[role_to_update]["system_prompt"] = extra_data["new_role_prompt"]
                    updated_something = True

        if updated_something:
            spc.post_message(channel=channel, text="Config update successful!", thread_ts=thread_ts)
        else:
            spc.post_message(channel=channel, text="No recognized config fields to update.", thread_ts=thread_ts)

    def _handle_print_config(self, channel, thread_ts):
        from services.slack_service.slack_adapter import SlackPostClient
        spc = SlackPostClient()
        spc.post_message(channel=channel, text=f"Current Bot Config:\n{bot_config}", thread_ts=thread_ts)
