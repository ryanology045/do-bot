# project_root/modules/snippet_manager.py

import logging
import uuid
import os
import time
import threading
from datetime import datetime, timedelta

from core.module_manager import BaseModule
from core.configs import bot_config
from core.snippets import SnippetsRunner
from services.slack_service import SlackService

logger = logging.getLogger(__name__)

snippet_storage = {}

class SnippetManager(BaseModule):
    module_name = "snippet_manager"
    module_type = "SNIPPET_MANAGER"

    def initialize(self):
        logger.info("[INIT] SnippetManager with watchers for snippet freeze & expiry.")
        threading.Thread(target=self._snippet_watchdog, daemon=True).start()
        threading.Thread(target=self._cleanup_expired_snippets, daemon=True).start()

    def propose_snippet(self, snippet_code, snippet_summary, user_text, channel, thread_ts, role_info="N/A"):
        line_limit = bot_config.get("snippet_line_limit", 250)
        lines = snippet_code.strip().split("\n")
        if len(lines) > line_limit:
            SlackService().post_message(
                channel=channel,
                text=f"Snippet too large ({len(lines)}/{line_limit} lines). Please simplify or break it down.",
                thread_ts=thread_ts
            )
            return None

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
            "initial_role_info": role_info,
            "start_time": now,
            "alerted_admin": False,
            "final_decision": None
        }

        SlackService().post_message(
            channel=channel,
            text=(
                f":robot_face: *Snippet Proposed (ID={snippet_id})*\n"
                f"*role_info:* {role_info}\n"
                f"*User request:* {user_text}\n\n"
                f"*Snippet Code*:\n```python\n{snippet_code}\n```\n\n"
                f"*Snippet Summary:*\n{snippet_summary}\n\n"
                "Type EXACTLY `confirm` to run, `cancel` to discard, or `extend` to push expiry. "
                f"(Expires in {expiry_minutes} min.)"
            ),
            thread_ts=thread_ts
        )
        return snippet_id

    def handle_typed_command(self, user_text, user_id, channel, thread_ts):
        """
        If user_text is 'confirm','cancel','extend', apply snippet action. 
        Return a dict with "action": "execute_snippet" if confirm => BotEngine does it
        Or None if no snippet or if canceled, etc.
        """
        import re
        raw = user_text.strip().lower()
        raw = re.sub(r"<@[^>]+>", "", raw).strip()
        raw = raw.strip("?!.,:;@").strip()

        if raw not in ["confirm","cancel","extend"]:
            return None

        # find snippet in snippet_storage
        best_sid = None
        best_time = None
        for sid, data in snippet_storage.items():
            if data["channel"] == channel and data["thread_ts"] == thread_ts and data["final_decision"] is None:
                if best_time is None or data["start_time"] > best_time:
                    best_sid = sid
                    best_time = data["start_time"]

        if not best_sid:
            return None

        return self._apply_snippet_action(best_sid, raw)

    def _apply_snippet_action(self, snippet_id, action_value):
        if snippet_id not in snippet_storage:
            return None

        entry = snippet_storage[snippet_id]
        now = datetime.utcnow()
        if now > entry["expires_at"]:
            SlackService().post_message(
                channel=entry["channel"],
                text="Snippet expired. No changes made.",
                thread_ts=entry["thread_ts"]
            )
            snippet_storage.pop(snippet_id, None)
            return None

        if action_value == "confirm":
            entry["final_decision"] = "confirm"
            snippet_storage.pop(snippet_id, None)

            # Instead of calling coder_manager, we just return an event to BotEngine
            return {
                "action": "execute_snippet",
                "snippet": entry
            }

        elif action_value == "cancel":
            entry["final_decision"] = "cancel"
            snippet_storage.pop(snippet_id, None)
            SlackService().post_message(
                channel=entry["channel"],
                text="Snippet canceled. No changes made.",
                thread_ts=entry["thread_ts"]
            )
            return None

        elif action_value == "extend":
            new_expires = entry["expires_at"] + timedelta(minutes=5)
            entry["expires_at"] = new_expires
            SlackService().post_message(
                channel=entry["channel"],
                text=f"Snippet expiration extended to {new_expires} UTC.",
                thread_ts=entry["thread_ts"]
            )
            return None

    # No more _execute_snippet here

    def _snippet_watchdog(self):
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
                        text=(f":warning: Snippet ID={sid} waiting ~{int(age)}s. "
                              "Type `confirm`, `cancel`, or `extend` in this thread. "
                              f"If no action in {int(admin_timeout/60)} min, bot may terminate."),
                        thread_ts=data["thread_ts"]
                    )
                    data["alerted_admin"] = True

                if force_terminate and (age > admin_timeout):
                    logger.error("[SNIPPET_MANAGER] Snippet ID=%s stuck >%ds => forcibly terminating container", sid, admin_timeout)
                    os._exit(1)

    def _cleanup_expired_snippets(self):
        while True:
            time.sleep(30)
            now = datetime.utcnow()
            for sid, data in list(snippet_storage.items()):
                if now > data["expires_at"]:
                    if data["final_decision"] is None:
                        SlackService().post_message(
                            channel=data["channel"],
                            text=(f"Snippet ID={sid} expired with no final decision. No changes applied."),
                            thread_ts=data["thread_ts"]
                        )
                    snippet_storage.pop(sid, None)
