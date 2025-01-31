# project_root/core/main.py

import os
from flask import Flask, jsonify

def create_app():
    from core.bot_engine import BotEngine
    from services.slack_service import SlackService

    app = Flask(__name__)

    @app.route("/health", methods=["GET"])
    def health_check():
        return jsonify({"status": "ok"}), 200

    bot_engine = BotEngine()
    slack_service = SlackService(bot_engine=bot_engine)
    slack_service.register_routes(app)

    return app

if __name__ == "__main__":
    app = create_app()
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)
