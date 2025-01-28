# plugins/slash_command_directory.py
"""
A central "directory" of slash commands.
Any plugin can call 'register_slash_command' to add a command to this directory.
Then, if a user asks "What slash commands are available?",
we reply with a list of them.
"""

import logging
from slack_bolt import App

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# A global registry of slash commands
# Key: command string ("/something"), Value: short description
_SLASH_COMMANDS = {}

def register_slash_command(command_name: str, description: str):
    """
    Called by other plugins to register the slash command in the global directory.
    """
    if not command_name.startswith("/"):
        command_name = f"/{command_name}"  # ensure it starts with '/'
    _SLASH_COMMANDS[command_name] = description

def get_slash_commands_list() -> str:
    """
    Returns a nicely formatted list of all registered slash commands.
    """
    if not _SLASH_COMMANDS:
        return "No slash commands are registered yet."
    lines = []
    for cmd, desc in sorted(_SLASH_COMMANDS.items()):
        lines.append(f"- `{cmd}`: {desc}")
    return "\n".join(lines)

def register(app: App):
    """
    Register a message or slash command that, when invoked, shows the entire directory.
    """
    @app.message("list slash commands")
    def list_slash_commands_message(message, say):
        """
        If a user types "list slash commands" in a channel, we respond with the directory.
        This is purely an example. You could also parse more complicated text with GPT if desired.
        """
        user_id = message.get("user", "")
        directory_text = get_slash_commands_list()
        say(f"<@{user_id}>, here are all known slash commands:\n{directory_text}")

    # Optionally, define a slash command like /help_slash
    # If you want a user to type /help_slash to get the same info.
    @app.command("/help_slash")
    def help_slash_command(ack, say, command):
        ack()
        user_id = command.get("user_id", "")
        directory_text = get_slash_commands_list()
        say(f"<@{user_id}>, here are all known slash commands:\n{directory_text}")
