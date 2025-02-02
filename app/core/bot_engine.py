# project_root/core/bot_engine.py

import logging
from .configs import bot_config
from .module_manager import ModuleManager
from services.slack_service import SlackService

logger = logging.getLogger(__name__)

class BotEngine:
    """
    Minimal Slack event orchestrator. For snippet logic or typed commands, 
    we delegate to SnippetManager. For watchers, also SnippetManager.
    """

    def __init__(self):
        logger.info("[INIT] BotEngine: loading modules, no watchers here.")
        self.module_manager = ModuleManager()
        self.module_manager.load_modules()

        self.personality_manager = self.module_manager.get_module("personality_manager")
        self.classifier_manager = self.module_manager.get_module("classification_manager")
        self.snippet_manager = self.module_manager.get_module("snippet_manager")

    def handle_incoming_slack_event(self, event_data):
        user_text = event_data.get("text","")
        channel  = event_data.get("channel")
        thread_ts= event_data.get("thread_ts") or event_data.get("ts")
        user_id  = event_data.get("user")

        logger.debug("[BOT_ENGINE] Slack event => text='%s', user='%s', ch='%s', thread_ts='%s'",
                     user_text, user_id, channel, thread_ts)

        # 1) snippet_manager typed command
        snippet_result = self.snippet_manager.handle_typed_command(user_text, user_id, channel, thread_ts)
        if snippet_result and snippet_result.get("action") == "execute_snippet":
            snippet_id = snippet_result["snippet_id"]

            # we still have snippet_manager snippet_storage
            # or a snippet_manager method to fetch it
            from modules.snippet_manager import snippet_storage
            entry = snippet_storage.get(snippet_id)
            if not entry:
                return  # weird edge case

            code_str = entry["code"]
            snippet_channel = entry["channel"]
            snippet_thread = entry["thread_ts"]

            # call coder_manager => snippet_callable
            coder_mgr = self.module_manager.get_module("coder_manager")
            snippet_callable = coder_mgr.create_snippet_callable(code_str)

            if snippet_callable:
                from core.snippets import SnippetsRunner
                runner = SnippetsRunner()

                # block until snippet returns or crashes
                runner.run_snippet_now(snippet_callable, snippet_channel, snippet_thread)

                # once it returns, remove from snippet_storage
                snippet_storage.pop(snippet_id, None)

                SlackService().post_message(
                    channel=snippet_channel,
                    text="Snippet executed successfully!",
                    thread_ts=snippet_thread
                )
                logger.info("[BOT_ENGINE] Snippet executed => '%s'", entry["user_request"])
            else:
                SlackService().post_message(
                    channel=snippet_channel,
                    text="Failed to create snippet callable.",
                    thread_ts=snippet_thread
                )
                logger.error("[BOT_ENGINE] snippet callable creation failed => '%s'", entry["user_request"])
            return

        # 2) Otherwise classification
        classification = self.classifier_manager.handle_classification(user_text, user_id, channel, thread_ts)
        req_type = classification.get("request_type","ASKTHEWORLD")
        role_info= classification.get("role_info","default")
        extra_data=classification.get("extra_data",{})

        logger.info("[BOT_ENGINE] classification => %s, role=%s, extra_data=%s", req_type, role_info, extra_data)

        if req_type == "ASKTHEBOT":
            self._handle_askthebot(user_text, user_id, channel, thread_ts)
        elif req_type == "CODER":
            self._handle_coder_flow(user_text, channel, thread_ts, role_info, extra_data)
        else:
            self._handle_asktheworld_flow(user_text, role_info, extra_data, channel, thread_ts)

    def _handle_askthebot(self, user_text, user_id, channel, thread_ts):
        askbot = self.module_manager.get_module("askthebot_manager")
        if not askbot:
            logger.error("[BOT_ENGINE] askthebot_manager not found.")
            return
        response = askbot.handle_bot_question(user_text, user_id, channel, thread_ts)
        SlackService().post_message(channel=channel, text=response, thread_ts=thread_ts)

    def _handle_coder_flow(self, user_text, channel, thread_ts, role_info, extra_data):
        """
        1) Generate snippet code with coder_manager
        2) Second pass snippet review with classification_manager
        3) snippet_manager.propose_snippet(...) => store snippet & instruct user typed commands
        """
        from modules.coder_manager import CoderManager
        coder_mgr = self.module_manager.get_module("coder_manager")
        if not coder_mgr:
            logger.error("[BOT_ENGINE] coder_manager missing.")
            return

        # 1) Generate code
        code_str = coder_mgr.generate_snippet(user_text)

        # 2) second pass snippet review prompt from config
        snippet_review_expanded = bot_config["initial_prompts"].get("snippet_review_expanded","")
        review_prompt = snippet_review_expanded + f"\n\n```python\n{code_str}\n```"
        snippet_summary = self.classifier_manager.review_snippet(review_prompt)

        # 3) propose snippet via snippet_manager
        self.snippet_manager.propose_snippet(
            snippet_code=code_str,
            snippet_summary=snippet_summary,
            user_text=user_text,
            channel=channel,
            thread_ts=thread_ts,
            role_info=role_info
        )

    def _handle_asktheworld_flow(self, user_text, role_info, extra_data, channel, thread_ts):
        askworld = self.module_manager.get_module_by_type("ASKTHEWORLD")
        if not askworld:
            logger.error("[BOT_ENGINE] asktheworld_manager not found.")
            return

        role_temp = extra_data.get("role_temperature")
        system_prompt, default_temp = self.personality_manager.get_system_prompt_and_temp(role_info)
        temperature = role_temp if role_temp is not None else default_temp

        askworld.handle_inquiry(
            user_text=user_text,
            system_prompt=system_prompt,
            temperature=temperature,
            user_id=None,
            channel=channel,
            thread_ts=thread_ts
        )

    def has_pending_snippet(self, channel, thread_ts):
        """
        Return True if snippet_manager has a snippet in this channel/thread 
        with final_decision=None.
        """
        return self.snippet_manager.has_pending_snippet_in(channel, thread_ts)
