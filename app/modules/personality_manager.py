# project_root/modules/personality_manager.py

from core.module_manager import BaseModule
from core.configs import bot_config

class PersonalityManager(BaseModule):
    module_name = "personality_manager"
    module_type = "PERSONALITY"

    def initialize(self):
        print("[INIT] PersonalityManager initialized.")

    def get_system_prompt_and_temp(self, role):
        roles_def = bot_config.get("roles_definitions", {})
        if role not in roles_def:
            role = "default"
        data = roles_def[role]
        return data["system_prompt"], data["temperature"]
