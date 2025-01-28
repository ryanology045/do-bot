# plugins/self_context.py
"""
Plugin to let the bot provide its own code on request.
Example usage:
  "@BotName can you get main.py of your code?"
"""

import os
import re
import logging
from slack_bolt import App

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# Restrict which files can be accessed (security measure).
ALLOWED_FILES = {
    "core/main.py",
    "core/slack_app.py",
    "plugins/plugin_manager.py",
    "plugins/gpt_interaction.py",
    "plugins/model_manager.py",
    "plugins/rate_limiting.py",
    "plugins/rollback.py",
    "plugins/self_upgrade.py",
    "services/openai_service.py",
    "services/github_service.py",
    "services/scheduler_service.py",
    "plugins/self_context.py",
    "plugins/internal_config.py",
    "plugins/role_manager.py",
}

FILE_REQUEST_REGEX = re.compile(
    r"(?i)\bget\s+([\w./]+)\s+of\s+(?:your|the)\s+code\??",
    re.IGNORECASE
)

def read_file_content(filepath: str) -> str:
    """
    Safely read the contents of a file if it is in ALLOWED_FILES.
    """
    if filepath not in ALLOWED_FILES:
        return f"Access to '{filepath}' is not allowed or the file is not recognized."
    if not os.path.isfile(filepath):
        return f"The file '{filepath}' was not found in the container."
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            return f"```python\n{f.read()}\n```"
    except Exception as e:
        return f"Error reading file '{filepath}': {str(e)}"

def register(app: App):
    @app.message(FILE_REQUEST_REGEX)
    def handle_file_request(message, say, context):
        """
        When a user says something like:
        '@BotName can you get main.py of your code?'
        """
        text = message.get("text", "")
        user_id = message.get("user", "")
        match = FILE_REQUEST_REGEX.search(text)
        if not match:
            return  # Not a recognized file request

        requested_file = match.group(1).strip()
        # Some minimal normalization to avoid weird paths
        requested_file = requested_file.replace("\\", "/").replace("//", "/")

        # Provide the file content or an error message
        content = read_file_content(requested_file)
        say(f"<@{user_id}>\n{content}")
