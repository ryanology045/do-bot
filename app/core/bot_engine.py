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

        # 1) Classify
        classifier_module = self.module_manager.get_module_by_type("CLASSIFIER")
        if not classifier_module:
            print("[ERROR] classification_manager not found.")
            return

        classification_result = classifier_module.handle_classification(
            user_text=user_text,
            user_id=user_id,
            channel=channel,
            thread_ts=thread_ts
        )
        # Example structure:
        # {
        #   "request_type": "ASKTHEWORLD",
        #   "role_info": "Batman",
        #   "extra_data": {
        #       "role_temperature": 0.5,
        #       "new_role_prompt": "You are Batman. A dark, witty vigilante..."
        #   }
        # }

        request_type = classification_result.get("request_type", "ASKTHEWORLD")
        role_info = classification_result.get("role_info", "default")
        extra_data = classification_result.get("extra_data", {})

        # 2) Possibly add a brand-new role to the config if GPT invented one
        self._maybe_register_new_role(role_info, extra_data)

        # 3) Route logic
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

    def _maybe_register_new_role(self, role_info, extra_data):
        """
        If 'role_info' is not in bot_config['roles_definitions'] but we have
        'new_role_prompt' in extra_data, we create a brand-new role entry.
        """
        roles_def = bot_config.get("roles_definitions", {})
        if role_info not in roles_def:
            new_prompt = extra_data.get("new_role_prompt")
            new_temp = extra_data.get("role_temperature")  # or "new_role_temp"
            if new_prompt:
                # Dynamically add a new role
                roles_def[role_info] = {
                    "system_prompt": new_prompt,
                    "temperature": new_temp if new_temp is not None else 0.7,
                    "description": f"Dynamically created role: {role_info}"
                }

    def _handle_config_update(self, extra_data, channel, thread_ts):
        from services.slack_service import SlackService
        spc = SlackService().slack_post_client

        updated_something = False

        new_model = extra_data.get("new_model")
        if new_model:
            bot_config["default_qna_model"] = new_model
            updated_something = True

        role_to_update = extra_data.get("role_to_update")
        if role_to_update:
            roles_def = bot_config["roles_definitions"]
            if role_to_update in roles_def:
                if "new_role_temp" in extra_data:
                    roles_def[role_to_update]["temperature"] = extra_data["new_role_temp"]
                    updated_something = True
                if "new_role_prompt" in extra_data:
                    roles_def[role_to_update]["system_prompt"] = extra_data["new_role_prompt"]
                    updated_something = True

        message = "Config update successful!" if updated_something else "No recognized config fields to update."
        spc.post_message(channel=channel, text=message, thread_ts=thread_ts)

    def _handle_print_config(self, channel, thread_ts):
        from services.slack_service import SlackService
        spc = SlackService().slack_post_client
        spc.post_message(channel=channel, text=f"Current Bot Config:\n{bot_config}", thread_ts=thread_ts)
