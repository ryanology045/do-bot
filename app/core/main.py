# core/main.py
import os
import threading
from slack_bolt import App
from slack_bolt.adapter.socket_mode import SocketModeHandler
from slack_bolt.adapter.flask import SlackRequestHandler
from services.scheduler_service import scheduler_start
from plugins.plugin_manager import PluginManager
from flask import Flask, request, make_response

# 1) Create your Slack Bolt App
bolt_app = App(
    token=os.environ.get("SLACK_BOT_TOKEN"),
    signing_secret=os.environ.get("SLACK_SIGNING_SECRET"),
    # etc.
)

# 2) Create a Flask instance
flask_app = Flask(__name__)

# 3) Tie Slack Bolt to the Flask instance
handler = SlackRequestHandler(bolt_app)

# Health check endpoint (for ECS)
@flask_app.route("/health", methods=["GET"])
def health_check():
    return make_response("OK", 200)

# Slack events route
@flask_app.route("/slack/events", methods=["POST"])
def slack_events():
    # Let Slack handle the request
    return handler.handle(request)

# Load plugins
PluginManager.load_plugins(bolt_app)

def main():
    # Start the scheduler in a separate thread
    scheduler_start()
    
    # Socket Mode if desired
    if os.environ.get("SLACK_APP_TOKEN"):
        threading.Thread(
            target=lambda: SocketModeHandler(bolt_app, os.environ["SLACK_APP_TOKEN"]).start(),
            daemon=True
        ).start()
    
    # Run the Flask server on port 3000 (or $PORT if set)
    port = int(os.environ.get("PORT", 3000))
    flask_app.run(host="0.0.0.0", port=port)

if __name__ == "__main__":
    main()
