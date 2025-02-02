# project_root/core/bot_engine.py

import logging
import uuid
import time
import threading
import os
from datetime import datetime, timedelta

from .configs import bot_config
from .module_manager import ModuleManager
from core.snippets import SnippetsRunner
from services.slack_service import SlackService

logger = logging.getLogger(__name__)

# snippet_id -> {
#   "code", "summary", "channel", "thread_ts", "expires_at",
#   "user_request", "initial_role_info",
#   "start_time",  # creation time
#   "alerted_admin",
#   "final_decision"  # "confirm" | "cancel" | None
# }
snippet_storage = {}

class BotEngine:
    """
    Slack event orchestrator.
    - typed snippet confirm/cancel/extend
    - snippet watchers => auto terminate if user unresponsive
    """

    def __init__(self):
        logger.info("[INIT] BotEngine: loading modules & watchers.")
        self.module_manager = ModuleManager()
        self.module_manager.load_modules()

        self.personality_manager = self.module_manager.get_module("personality_manager")
        self.classifier_manager = self.module_manager.get_module("classification_manager")

        # Start snippet freeze watchers
        threading.Thread(target=self._snippet_watchdog, daemon=True).start()
        # Start snippet expiration cleanup
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

        # 1) Attempt typed snippet commands
        if self._handle_typed_snippet_command(user_text, user_id, channel, thread_ts):
            return

        # 2) Otherwise do classification
        classification = self.classifier_manager.handle_classification(user_text, user_id, channel, thread_ts)
        req_type = classification.get("request_type", "ASKTHEWORLD")
        role_info = classification.get("role_info", "default")
        extra_data = classification.get("extra_data", {})

        logger.info("[BOT_ENGINE] classification => request_type=%s, role=%s, extra_data=%s",
                    req_type, role_info, extra_data)

        if req_type == "ASKTHEBOT":
            self._handle_askthebot(user_text, user_id, channel, thread_ts)
        elif req_type == "CODER":
            self._handle_coder_flow(user_text, channel, thread_ts, user_id, extra_data)
        else:
            self._handle_asktheworld_flow(user_text, role_info, extra_data, channel, thread_ts)

    def _handle_askthebot(self, user_text, user_id, channel, thread_ts):
        logger.debug("[BOT_ENGINE] Handling ASKTHEBOT => '%s'", user_text)
        askbot_manager = self.module_manager.get_module("askthebot_manager")
        if not askbot_manager:
            logger.error("[BOT_ENGINE] askthebot_manager not found.")
            return

        resp_text = askbot_manager.handle_bot_question(user_text, user_id, channel, thread_ts)
        SlackService().post_message(channel=channel, text=resp_text, thread_ts=thread_ts)

    def _handle_coder_flow(self, user_text, channel, thread_ts, user_id, extra_data):
        logger.debug("[BOT_ENGINE] CODER flow => user_text='%s'", user_text)
        coder_mgr = self.module_manager.get_module("coder_manager")
        if not coder_mgr:
            logger.error("[BOT_ENGINE] coder_manager not found.")
            return

        snippet_code = coder_mgr.generate_snippet(user_text)
        line_limit = bot_config.get("snippet_line_limit", 250)
        lines = snippet_code.strip().split("\n")
        if len(lines) > line_limit:
            SlackService().post_message(
                channel=channel,
                text=(f"Snippet too large ({len(lines)} lines), limit={line_limit}. Please shorten."),
                thread_ts=thread_ts
            )
            return

        # second pass snippet summary with Classification GPT
        prompt_review = (
            "This snippet is proposed but NOT executed. Summarize in plain language:\n"
            f"```python\n{snippet_code}\n```"
        )
        snippet_summary = self.classifier_manager.review_snippet(prompt_review)

        expiry_minutes = bot_config.get("snippet_expiration_minutes", 5)
        now = datetime.utcnow()
        expires_at = now + timedelta(minutes=expiry_minutes)

        snippet_id = str(uuid.uuid4())
        snippet_storage[snippet_id] = {
            "code": snippet_code,
            "summary": snippet_summary,
            "channel": channel,
            "thread_ts": thread_ts,
            "expires_at": expires_at,
            "user_request": user_text,
            "initial_role_info": extra_data.get("role_info","N/A"),
            "start_time": now,
            "alerted_admin": False,
            "final_decision": None
        }

        SlackService().post_message(
            channel=channel,
            text=(
                f":robot_face: *Snippet Proposed (ID={snippet_id})*\n"
                f"*role_info:* {extra_data.get('role_info','N/A')}\n"
                f"*User request:* {user_text}\n\n"
                f"*Snippet (truncated)*:\n```python\n{snippet_code[:1000]}...\n```\n\n"
                f"*Snippet Summary*:\n{snippet_summary}\n\n"
                f"Type `confirm` to run, `cancel` to discard, or `extend` to push expiry. "
                f"(Expires in {expiry_minutes}m)"
            ),
            thread_ts=thread_ts
        )

    def _handle_typed_snippet_command(self, user_text, user_id, channel, thread_ts):
        text_lower = user_text.strip().lower()
        if text_lower not in ["confirm","cancel","extend"]:
            return False

        # find snippet in this channel/thread with final_decision=None
        best_sid = None
        best_time = None
        for sid, data in snippet_storage.items():
            if data["channel"] == channel and data["thread_ts"] == thread_ts and data["final_decision"] is None:
                if best_time is None or data["start_time"] > best_time:
                    best_sid = sid
                    best_time = data["start_time"]

        if not best_sid:
            return False

        self._apply_typed_action(best_sid, text_lower, user_id)
        return True

    def _apply_typed_action(self, snippet_id, action_value, user_id):
        if snippet_id not in snippet_storage:
            SlackService().post_message(
                channel="",  # no known channel
                text="Snippet not found in this thread.",
                thread_ts=None
            )
            return

        entry = snippet_storage[snippet_id]
        now = datetime.utcnow()
        if now > entry["expires_at"]:
            SlackService().post_message(
                channel=entry["channel"],
                text="Snippet expired. No changes made.",
                thread_ts=entry["thread_ts"]
            )
            snippet_storage.pop(snippet_id, None)
            return

        if action_value == "confirm":
            entry["final_decision"] = "confirm"
            snippet_storage.pop(snippet_id, None)

            from modules.coder_manager import CoderManager
            coder_mgr = self.module_manager.get_module("coder_manager")
            snippet_callable = coder_mgr.create_snippet_callable(entry["code"])
            if snippet_callable:
                sr = SnippetsRunner()
                sr.run_snippet_now(snippet_callable, entry["channel"], entry["thread_ts"])
                SlackService().post_message(
                    channel=entry["channel"],
                    text="Snippet executed successfully!",
                    thread_ts=entry["thread_ts"]
                )
                logger.info("[BOT_ENGINE] Snippet executed => '%s'", entry["user_request"])
            else:
                SlackService().post_message(
                    channel=entry["channel"],
                    text="Failed to create snippet callable.",
                    thread_ts=entry["thread_ts"]
                )
                logger.error("[BOT_ENGINE] snippet callable creation failed => '%s'", entry["user_request"])

        elif action_value == "cancel":
            entry["final_decision"] = "cancel"
            snippet_storage.pop(snippet_id, None)
            SlackService().post_message(
                channel=entry["channel"],
                text="Snippet canceled. No changes made.",
                thread_ts=entry["thread_ts"]
            )

        elif action_value == "extend":
            # keep final_decision=None
            new_expires = entry["expires_at"] + timedelta(minutes=5)
            entry["expires_at"] = new_expires
            SlackService().post_message(
                channel=entry["channel"],
                text=f"Snippet expiration extended to {new_expires} UTC.",
                thread_ts=entry["thread_ts"]
            )

    def _handle_asktheworld_flow(self, user_text, role_info, extra_data, channel, thread_ts):
        logger.debug("[BOT_ENGINE] ASKTHEWORLD => text='%s'", user_text)
        asktheworld_manager = self.module_manager.get_module_by_type("ASKTHEWORLD")
        if not asktheworld_manager:
            logger.error("[BOT_ENGINE] asktheworld_manager not found.")
            return

        role_temp = extra_data.get("role_temperature")
        sys_prompt, default_temp = self.personality_manager.get_system_prompt_and_temp(role_info)
        temperature = role_temp if role_temp is not None else default_temp

        asktheworld_manager.handle_inquiry(
            user_text=user_text,
            system_prompt=sys_prompt,
            temperature=temperature,
            user_id=None,
            channel=channel,
            thread_ts=thread_ts
        )

    def _snippet_watchdog(self):
        """
        Waits snippet_watchdog_seconds => warns admin if snippet is pending
        Then if admin_watchdog_timeout_seconds passes => forcibly terminate container
        """
        while True:
            time.sleep(5)
            now = datetime.utcnow()

            watch_secs = bot_config.get("snippet_watchdog_seconds", 10)
            admin_timeout = bot_config.get("admin_watchdog_timeout_seconds", 3600)
            force_terminate = bot_config.get("force_bot_termination_on_snippet_freeze", True)

            for sid, data in list(snippet_storage.items()):
                if data["final_decision"] is not None:
                    continue

                age = (now - data["start_time"]).total_seconds()

                if (not data["alerted_admin"]) and (age > watch_secs):
                    SlackService().post_message(
                        channel=data["channel"],
                        text=(f":warning: Snippet ID={sid} stuck for ~{int(age)}s. "
                              "Type `confirm`/`cancel`/`extend` in this thread. "
                              f"If no action in {int(admin_timeout/60)}min, bot may terminate."),
                        thread_ts=data["thread_ts"]
                    )
                    data["alerted_admin"] = True

                if force_terminate and age > admin_timeout:
                    logger.error("[BOT_ENGINE] Snippet ID=%s stuck >%ds => forcibly terminating container", sid, admin_timeout)
                    os._exit(1)

    def _cleanup_expired_snippets(self):
        """
        Periodically checks snippet_storage for time-based expiry (expires_at).
        If expired + no final decision => remove it + post message.
        """
        while True:
            time.sleep(30)
            now = datetime.utcnow()
            for sid, data in list(snippet_storage.items()):
                if now > data["expires_at"]:
                    if data["final_decision"] is None:
                        SlackService().post_message(
                            channel=data["channel"],
                            text=(f"Snippet ID={sid} expired with no final decision. "
                                  "No changes applied."),
                            thread_ts=data["thread_ts"]
                        )
                    snippet_storage.pop(sid, None)
