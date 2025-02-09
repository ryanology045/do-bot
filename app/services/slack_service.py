# project_root/services/slack_service.py

import os
import logging
from flask import request, jsonify
from slack_sdk import WebClient
from slack_sdk.signature import SignatureVerifier

logger = logging.getLogger(__name__)

processed_event_ids = set()  # simple in-memory store. Could reset on restarts.

class SlackService:
    """
    Pure Slack interface: register_routes, post_message, remove_self_from_channel.
    """

    def __init__(self, bot_engine=None):
        self.bot_engine = bot_engine
        self.signing_secret = os.environ.get("SLACK_SIGNING_SECRET", "")
        self.signature_verifier = SignatureVerifier(self.signing_secret)
        self.web_client = WebClient(token=os.environ.get("SLACK_BOT_TOKEN", ""))

        # The Slack bot's user ID (e.g. "U089Q3FGMKQ"). 
        # Typically set via environment or found from Slack (whoami).
        self.bot_user_id = os.environ.get("BOT_USER_ID", "")

    def register_routes(self, app):
        @app.route("/slack/events", methods=["POST"])
        def slack_events():
            if "challenge" in request.json:
                return jsonify({"challenge": request.json["challenge"]}), 200

            if not self._is_request_valid(request):
                return "Invalid request signature", 401

            # Respond quickly so Slack doesn't retry
            resp = {"status": "ok"}

            event_data = request.json.get("event", {})
            event_id = request.json.get("event_id")
            event_type = event_data.get("type", "")
            user_id = event_data.get("user", "")
            bot_id = event_data.get("bot_id")

            # 1) Skip duplicates
            if event_id and event_id in processed_event_ids:
                logger.debug("Skipping duplicate event_id=%s", event_id)
                return jsonify(resp), 200
            if event_id:
                processed_event_ids.add(event_id)

            # 2) Skip if from the bot itself
            if bot_id is not None:
                logger.debug("Skipping event from the bot (bot_id=%s).", bot_id)
                return jsonify(resp), 200
            if user_id == self.bot_user_id:
                logger.debug("Skipping event from BOT_USER_ID=%s", user_id)
                return jsonify(resp), 200

            # 3) Distinguish app_mention vs. message
            if event_type == "app_mention":
                # The user explicitly tagged the bot => handle in bot_engine
                self.bot_engine.handle_incoming_slack_event(event_data)

            elif event_type == "message":
                # Possibly typed snippet commands, or snippet is pending
                channel_id = event_data.get("channel")
                thread_ts  = event_data.get("thread_ts") or event_data.get("ts")

                # If there's a snippet pending in that thread, 
                # we let bot_engine handle typed commands or confirm/cancel/extend
                if self.bot_engine.has_pending_snippet(channel_id, thread_ts):
                    self.bot_engine.handle_incoming_slack_event(event_data)
                # else do nothing for normal messages (no mention, no snippet pending)

            return jsonify(resp), 200

    def _is_request_valid(self, req):
        timestamp = req.headers.get("X-Slack-Request-Timestamp", "")
        signature = req.headers.get("X-Slack-Signature", "")
        body = req.get_data(as_text=True)
        return self.signature_verifier.is_valid(body, timestamp, signature)

    def post_message(self, channel, text, thread_ts=None):
        try:
            self.web_client.chat_postMessage(channel=channel, text=text, thread_ts=thread_ts)
        except Exception as e:
            logger.error(f"SlackService post_message error: {e}")

    def remove_self_from_channel(self, channel_id):
        from slack_sdk.errors import SlackApiError
        try:
            resp = self.web_client.conversations_leave(channel=channel_id)
            if not resp.get("ok", False):
                raise Exception(f"Failed to leave channel: {resp.get('error')}")
        except SlackApiError as e:
            raise Exception(f"Slack API error: {e.response['error']}")
