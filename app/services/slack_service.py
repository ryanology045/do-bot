# project_root/services/slack_service.py

import os
import logging
from flask import request, jsonify
from slack_sdk import WebClient
from slack_sdk.signature import SignatureVerifier

logger = logging.getLogger(__name__)

class SlackService:
    """
    Pure Slack interface: register_routes, post_message, remove_self_from_channel.
    """

    def __init__(self, bot_engine=None):
        self.bot_engine = bot_engine
        self.signing_secret = os.environ.get("SLACK_SIGNING_SECRET", "")
        self.signature_verifier = SignatureVerifier(self.signing_secret)
        self.web_client = WebClient(token=os.environ.get("SLACK_BOT_TOKEN", ""))

    def register_routes(self, app):
        @app.route("/slack/events", methods=["POST"])
        def slack_events():
            if "challenge" in request.json:
                return jsonify({"challenge": request.json["challenge"]}), 200

            if not self._is_request_valid(request):
                return "Invalid request signature", 401

            event_data = request.json.get("event", {})
            if (event_data.get("type") in ["message","app_mention"]) and not event_data.get("bot_id"):
                self.bot_engine.handle_incoming_slack_event(event_data)

            return jsonify({"status": "ok"}), 200

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
