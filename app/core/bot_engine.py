# project_root/core/bot_engine.py

import logging
import uuid
import time
import threading
from datetime import datetime, timedelta

from .configs import bot_config
from .module_manager import ModuleManager
from modules.coder_manager import CoderManager
from core.snippets import SnippetsRunner
from services.slack_service import SlackService

logger = logging.getLogger(__name__)

snippet_storage = {}  # snippet_id -> { "code", "summary", "channel", "thread_ts", "expires_at", "user_request", "initial_role_info" }

class BotEngine:
    """
    Slack event orchestrator:
      - Classification => ASKTHEWORLD | ASKTHEBOT | CODER
      - CODER => advanced code or config logic in coder_manager
      - ASKTHEBOT => architecture Qs => askthebot_manager
      - else => normal Q&A => asktheworld_manager

    Now includes:
      - A second GPT "sanity check" summarizing generated snippet code
      - An ephemeral confirmation flow with snippet expiration
    """

    def __init__(self):
        logger.info("[INIT] BotEngine: loading modules & personality manager.")
        self.module_manager = ModuleManager()
        self.module_manager.load_modules()
        self.personality_manager = self.module_manager.get_module("personality_manager")

        # OPTIONAL: start a background thread to clean up expired snippets:
        threading.Thread(target=self._cleanup_expired_snippets, daemon=True).start()

    def handle_incoming_slack_event(self, event_data):
        user_text = event_data.get("text", "")
        channel = event_data.get("channel")
        thread_ts = event_data.get("thread_ts") or event_data.get("ts")
        user_id = event_data.get("user")

        logger.debug(
            "[BOT_ENGINE] Slack event => text='%s', user='%s', channel='%s', thread_ts='%s'",
            user_text, user_id, channel, thread_ts
        )

        classifier = self.module_manager.get_module_by_type("CLASSIFIER")
        if not classifier:
            logger.error("[BOT_ENGINE] classification_manager not found.")
            return

        classification_result = classifier.handle_classification(
            user_text, user_id, channel, thread_ts
        )
        request_type = classification_result.get("request_type", "ASKTHEWORLD")
        role_info = classification_result.get("role_info", "default")
        extra_data = classification_result.get("extra_data", {})

        logger.info(
            "[BOT_ENGINE] classification => request_type=%s, role=%s, extra_data=%s",
            request_type, role_info, extra_data
        )

        # Store user_id in extra_data so we have a consistent approach
        if "user_id" not in extra_data:
            extra_data["user_id"] = user_id

        if request_type == "ASKTHEBOT":
            self._handle_askthebot(user_text, user_id, channel, thread_ts)
        elif request_type == "CODER":
            self._handle_coder_flow(user_text, channel, thread_ts, extra_data)
        else:
            self._handle_asktheworld_flow(user_text, role_info, extra_data, channel, thread_ts)

    def _handle_askthebot(self, user_text, user_id, channel, thread_ts):
        logger.debug("[BOT_ENGINE] Handling ASKTHEBOT for user_text='%s'", user_text)
        askbot_module = self.module_manager.get_module("askthebot_manager")
        if not askbot_module:
            logger.error("[BOT_ENGINE] askthebot_manager not found.")
            return

        response_text = askbot_module.handle_bot_question(user_text, user_id, channel, thread_ts)
        SlackService().post_message(channel=channel, text=response_text, thread_ts=thread_ts)

    def _handle_coder_flow(self, user_text, channel, thread_ts, extra_data):
        """
        If classification says request_type=CODER, we arrive here.
        We'll:
          1) Generate snippet with coder_manager
          2) Do a 2nd GPT pass (the "sanity check") to interpret the snippet
          3) Show user the initial classifier interpretation, the snippet, the 2nd pass summary, recommended considerations
          4) Provide ephemeral Slack buttons: Confirm, Extend, Cancel
          5) If Confirm => run snippet
          6) If Cancel => discard
          7) If Extend => push back expiration
        """
        logger.debug("[BOT_ENGINE] CODER flow => user_text='%s', extra_data=%s", user_text, extra_data)

        # Check if user specifically requested a different channel/thread
        override_channel = extra_data.get("override_channel")  # e.g. "#random"
        override_thread = extra_data.get("override_thread")

        final_channel = override_channel if override_channel else channel
        final_thread = override_thread if override_thread else thread_ts

        coder_mgr = self.module_manager.get_module("coder_manager")
        if not coder_mgr:
            logger.error("[BOT_ENGINE] coder_manager not found.")
            return

        slack_service = SlackService()

        bot_knowledge = extra_data.get("bot_knowledge", "")
        coder_input = user_text
        if bot_knowledge:
            coder_input += f"\n\n[Bot Knowledge]: {bot_knowledge}"

        # Generate snippet code
        snippet_code = coder_mgr.generate_snippet(coder_input)
        logger.debug(f"[BOT_ENGINE] Generated snippet:\n{snippet_code}")

        # Second GPT pass: "sanity check"
        summary_prompt = (
            "You are a snippet reviewer. Summarize in plain language what the following Python code does. "
            "Focus on potential destructive actions or changes. Return a short bullet-list or paragraph. "
            "No disclaimers, just the summary.\n\n"
            f"```python\n{snippet_code}\n```"
        )
        snippet_summary = coder_mgr.review_snippet(summary_prompt)

        initial_role_info = extra_data.get("role_info", "N/A")

        # Parameterize default snippet expiration:
        expiration_minutes = bot_config.get("snippet_expiration_minutes", 5)
        now = datetime.utcnow()
        expires_at = now + timedelta(minutes=expiration_minutes)

        snippet_id = str(uuid.uuid4())
        snippet_storage[snippet_id] = {
            "code": snippet_code,
            "summary": snippet_summary,
            "channel": final_channel,
            "thread_ts": final_thread,
            "expires_at": expires_at,
            "user_request": user_text,
            "initial_role_info": initial_role_info
        }

        # Distinguish ephemeral vs public confirm (optional):
        confirm_style = extra_data.get("confirm_style", "ephemeral")  # "ephemeral" or "public"

        ephemeral_text = (
            f"*Classifier's initial interpretation (role_info)*: {initial_role_info}\n"
            f"*Original user request*: {user_text}\n\n"
            "*--- Generated Snippet Code (shortened if long) ---*\n"
            f"```python\n{snippet_code[:1000]}...\n```\n\n"
            "*--- Second GPT pass summary ---*\n"
            f"{snippet_summary}\n\n"
            "*Recommended considerations*: If it matches your intent, confirm. Otherwise, extend or cancel. "
            f"(Expires in {expiration_minutes} minute(s).)"
        )

        if confirm_style == "public":
            # If user wants a public confirm message:
            slack_service.post_message(
                channel=final_channel,
                text=ephemeral_text
            )
            # You could provide an interactive approach for public usage, but ephemeral is typical
        else:
            # ephemeral usage is typical
            slack_service.post_interactive_confirm(
                snippet_id=snippet_id,
                ephemeral_text=ephemeral_text,
                channel=final_channel,
                user=extra_data["user_id"]
            )

    def handle_interactive_confirm_action(self, snippet_id, action_value, user_id):
        """
        This method is called when user clicks one of the ephemeral buttons:
        - confirm_SNIPPETID
        - extend_SNIPPETID
        - cancel_SNIPPETID
        """
        if snippet_id not in snippet_storage:
            # Already expired or used
            SlackService().post_ephemeral(
                channel="",
                user=user_id,
                text="Snippet not found (maybe expired)."
            )
            return

        entry = snippet_storage[snippet_id]
        code_str = entry["code"]
        snippet_channel = entry["channel"]
        snippet_thread = entry["thread_ts"]
        user_req = entry["user_request"]
        now = datetime.utcnow()

        if now > entry["expires_at"]:
            SlackService().post_ephemeral(
                channel=snippet_channel,
                user=user_id,
                text="Snippet expired. No changes made."
            )
            snippet_storage.pop(snippet_id, None)
            return

        if action_value == "confirm":
            # Confirm => run the snippet
            snippet_storage.pop(snippet_id, None)
            snippet_callable = self.module_manager.get_module("coder_manager").create_snippet_callable(code_str)
            if snippet_callable:
                sr = SnippetsRunner()
                sr.run_snippet_now(snippet_callable, snippet_channel, snippet_thread)
                logger.info("[BOT_ENGINE] Code snippet executed successfully for request: %s", user_req)
                SlackService().post_ephemeral(
                    channel=snippet_channel, user=user_id,
                    text="Snippet executed successfully!"
                )
            else:
                logger.error("[BOT_ENGINE] Failed to create snippet callable from request='%s'", user_req)
                SlackService().post_ephemeral(
                    channel=snippet_channel, user=user_id,
                    text="Failed to create snippet callable."
                )

        elif action_value == "extend":
            new_expires = entry["expires_at"] + timedelta(minutes=5)
            entry["expires_at"] = new_expires
            SlackService().post_ephemeral(
                channel=snippet_channel, user=user_id,
                text=f"Snippet expiration extended to {new_expires} UTC."
            )

        elif action_value == "cancel":
            snippet_storage.pop(snippet_id, None)
            SlackService().post_ephemeral(
                channel=snippet_channel, user=user_id,
                text="Snippet canceled. No changes made."
            )

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

    def _cleanup_expired_snippets(self):
        """
        Periodically checks snippet_storage for expired entries and removes them.
        This runs in a background thread, so it doesn't block the main Slack event loop.
        """
        while True:
            now = datetime.utcnow()
            # Make a copy of items to avoid runtime dict change error
            for sid, entry in list(snippet_storage.items()):
                if now > entry["expires_at"]:
                    snippet_storage.pop(sid, None)
            time.sleep(30)  # check every 30 seconds
