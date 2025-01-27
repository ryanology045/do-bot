# core/main.py
#"""
#Main entry point: starts the Slack Bolt app with an HTTP server and optionally Socket Mode.
#Also initializes the scheduler and plugin loading.
#"""

import os
import threading
from slack_bolt import App
from slack_bolt.adapter.socket_mode import SocketModeHandler
from slack_bolt.adapter.flask import SlackRequestHandler
from core.slack_app import app, start_socket_mode
from services.scheduler_service import scheduler_start
from plugins.plugin_manager import PluginManager
from slack_bolt.oauth.oauth_settings import OAuthSettings

from flask import Flask, request, make_response

# 1) Create your Slack Bolt App
app = App(
    token=os.environ.get("SLACK_BOT_TOKEN"),
    signing_secret=os.environ.get("SLACK_SIGNING_SECRET"),
    # Add other configurations if necessary
)

# 2) Create a Flask instance
flask_app = Flask(__name__)

# 3) Tie Slack Bolt to the Flask instance
handler = SlackRequestHandler(app)

# Health check endpoint (for ECS)
@flask_app.route("/health", methods=["GET"])
def health_check():
    return make_response("OK", 200)

# If Slack requests a URL verification challenge, handle it:
# NOTE: In Slack Bolt, this is typically auto-handled, but we'll make it explicit just in case.
@flask_app.route("/slack/events", methods=["POST"])
def slack_events():
    if request.json and "challenge" in request.json:
        return make_response(request.json["challenge"], 200)
    return make_response(app.dispatch(request), 200)

# Initialize and load plugins
PluginManager.load_plugins(app)

def main():
    # Start the scheduler in a separate thread
    scheduler_start()
    
    # Optionally start Socket Mode in a separate thread if SLACK_APP_TOKEN is present
    if os.environ.get("SLACK_APP_TOKEN"):
        threading.Thread(target=start_socket_mode, args=(app, ), daemon=True).start()
    
    # Finally, start the built-in Slack Bolt web server on port 3000 (or whatever is set in $PORT)
    port = int(os.environ.get("PORT", 3000))
    app.start(port=port)


if __name__ == "__main__":
    main()
