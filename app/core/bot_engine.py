# project_root/core/bot_engine.py

import logging
from .configs import bot_config
from .module_manager import ModuleManager

logger = logging.getLogger(__name__)

class BotEngine:
    """
    Slack event orchestrator:
      - Classification => ASKTHEWORLD | ASKTHEBOT | CODER
      - CODER => advanced code or config logic in coder_manager
      - ASKTHEBOT => architecture Qs => askthebot_manager
      - else => normal Q&A => asktheworld_manager
    """

    def __init__(self):
        logger.info("[INIT] BotEngine: loading modules & personality manager.")
        self.module_manager = ModuleManager()
        self.module_manager.load_modules()
        self.personality_manager = self.module_manager.get_module("personality_manager")

    def handle_incoming_slack_event(self, event_data):
        user_text = event_data.get("text", "")
        channel = event_data.get("channel")
        thread_ts = event_data.get("thread_ts") or event_data.get("ts")
        user_id = event_data.get("user")

        logger.debug("[BOT_ENGINE] Slack event => text='%s', user='%s', channel='%s', thread_ts='%s'",
                     user_text, user_id, channel, thread_ts)

        classifier = self.module_manager.get_module_by_type("CLASSIFIER")
        if not classifier:
            logger.error("[BOT_ENGINE] classification_manager not found.")
            return

        classification_result = classifier.handle_classification(user_text, user_id, channel, thread_ts)
        request_type = classification_result.get("request_type", "ASKTHEWORLD")
        role_info = classification_result.get("role_info", "default")
        extra_data = classification_result.get("extra_data", {})

        logger.info("[BOT_ENGINE] classification => request_type=%s, role=%s, extra_data=%s",
                    request_type, role_info, extra_data)

        # Possibly handle new role creation
        self._maybe_register_new_role(role_info, extra_data, user_text, channel, thread_ts)

        if request_type == "ASKTHEBOT":
            self._handle_askthebot(user_text, user_id, channel, thread_ts)
        elif request_type == "CODER":
            self._handle_coder_flow(user_text, channel, thread_ts, extra_data)
        else:
            self._handle_asktheworld_flow(user_text, role_info, extra_data, channel, thread_ts)

    def _maybe_register_new_role(self, role_info, extra_data, user_text, channel, thread_ts):
        """
        If GPT invented a new role, store it in bot_config. 
        Then optionally run coder snippet to 'persist' that code. 
        """
        roles_def = bot_config["roles_definitions"]
        if role_info not in roles_def:
            new_prompt = extra_data.get("new_role_prompt")
            new_temp = extra_data.get("role_temperature")
            if new_prompt:
                logger.info("[BOT_ENGINE] GPT invented new role '%s'. Storing in memory & possibly persisting via snippet.",
                            role_info)
                roles_def[role_info] = {
                    "system_prompt": new_prompt,
                    "temperature": new_temp if new_temp is not None else 0.7,
                    "description": f"Dynamically created role: {role_info}"
                }
                self._run_new_role_snippet(role_info, new_prompt, new_temp, user_text, channel, thread_ts)

    def _run_new_role_snippet(self, role_name, role_prompt, role_temp, user_text, channel, thread_ts):
        logger.debug("[BOT_ENGINE] Running snippet to persist new role '%s' with prompt:\n%s", role_name, role_prompt)
        coder_mgr = self.module_manager.get_module("coder_manager")
        if not coder_mgr:
            logger.warning("[BOT_ENGINE] coder_manager not found, cannot persist new role in code.")
            return

        coder_input = (
            f"The user created new role '{role_name}' with system_prompt:\n{role_prompt}\n"
            f"Temperature={role_temp}. Please produce code snippet to store this role in code (bot_config)."
        )
        snippet_code = coder_mgr.generate_snippet(coder_input)
        logger.debug(f"[BOT_ENGINE] Generated snippet:\n{snippet_code}")
        snippet_callable = coder_mgr.create_snippet_callable(snippet_code)
        if snippet_callable:
            from core.snippets import SnippetsRunner
            sr = SnippetsRunner()
            sr.run_snippet_now(snippet_callable)
            logger.info("[BOT_ENGINE] New role snippet executed successfully.")
            from services.slack_service import SlackService
            SlackService().post_message(
                channel=channel,
                text=f"New role '{role_name}' snippet executed for code persistence.",
                thread_ts=thread_ts
            )
        else:
            logger.error("[BOT_ENGINE] Failed to create snippet callable for new role '%s'.", role_name)

    def _handle_askthebot(self, user_text, user_id, channel, thread_ts):
        logger.debug("[BOT_ENGINE] Handling ASKTHEBOT for user_text='%s'", user_text)
        askbot_module = self.module_manager.get_module("askthebot_manager")
        if not askbot_module:
            logger.error("[BOT_ENGINE] askthebot_manager not found.")
            return

        response_text = askbot_module.handle_bot_question(user_text, user_id, channel, thread_ts)

        from services.slack_service import SlackService
        SlackService().post_message(channel=channel, text=response_text, thread_ts=thread_ts)

    def _handle_coder_flow(self, user_text, channel, thread_ts, extra_data):
        logger.debug("[BOT_ENGINE] CODER flow => user_text='%s', extra_data=%s", user_text, extra_data)
        coder_mgr = self.module_manager.get_module("coder_manager")
        if not coder_mgr:
            logger.error("[BOT_ENGINE] coder_manager not found.")
            return

        from services.slack_service import SlackService
        slack_service = SlackService()

        bot_knowledge = extra_data.get("bot_knowledge", "")
        coder_input = user_text
        if bot_knowledge:
            coder_input += f"\n\n[Bot Knowledge]: {bot_knowledge}"

        snippet_code = coder_mgr.generate_snippet(coder_input)
        logger.debug(f"[BOT_ENGINE] Generated snippet:\n{snippet_code}")
        snippet_callable = coder_mgr.create_snippet_callable(snippet_code)
        if snippet_callable:
            from core.snippets import SnippetsRunner
            sr = SnippetsRunner()
            sr.run_snippet_now(snippet_callable)
            logger.info("[BOT_ENGINE] Code snippet executed successfully for request: %s", user_text)
            slack_service.post_message(channel=channel, text="Code snippet executed successfully.", thread_ts=thread_ts)
        else:
            logger.error("[BOT_ENGINE] Failed to generate snippet code from user_text='%s'", user_text)
            slack_service.post_message(channel=channel, text="Failed to generate snippet code.", thread_ts=thread_ts)

    def _handle_asktheworld_flow(self, user_text, role_info, extra_data, channel, thread_ts):
        logger.debug("[BOT_ENGINE] ASKTHEWORLD flow => user_text='%s', role_info='%s'", user_text, role_info)
        asktheworld_module = self.module_manager.get_module_by_type("ASKTHEWORLD")
        if not asktheworld_module:
            logger.error("[BOT_ENGINE] asktheworld_manager not found.")
            return

        role_temp = extra_data.get("role_temperature")
        system_prompt, default_temp = self.personality_manager.get_system_prompt_and_temp(role_info)
        temperature = role_temp if role_temp is not None else default_temp

        asktheworld_module.handle_inquiry(
            user_text=user_text,
            system_prompt=system_prompt,
            temperature=temperature,
            user_id=None,
            channel=channel,
            thread_ts=thread_ts
        )
