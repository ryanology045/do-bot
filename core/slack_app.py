# core/slack_app.py
"""
Slack Bolt app initialization for both Socket Mode and HTTP event subscriptions.
"""

import os
from slack_bolt import App
from slack_bolt.adapter.socket_mode import SocketModeHandler

# Slack environment variables
SLACK_BOT_TOKEN = os.environ.get("SLACK_BOT_TOKEN")
SLACK_SIGNING_SECRET = os.environ.get("SLACK_SIGNING_SECRET")
SLACK_APP_TOKEN = os.environ.get("SLACK_APP_TOKEN")  # For Socket Mode

# Create the Slack Bolt App
# If signing_secret is None, some features may not work properly
# but we allow it for demonstration. In production, you must provide the signing secret.
app = App(
    token=SLACK_BOT_TOKEN,
    signing_secret=SLACK_SIGNING_SECRET
)

# Optionally start SocketModeHandler in a thread or later in main.py
def start_socket_mode(app_obj: App):
    """
    Starts Slack Socket Mode. This allows receiving events without public HTTP endpoints.
    """
    if SLACK_APP_TOKEN:
        handler = SocketModeHandler(app_obj, SLACK_APP_TOKEN)
        handler.start()  # blocking call
    else:
        print("Warning: SLACK_APP_TOKEN not set. Socket Mode will not start.")
