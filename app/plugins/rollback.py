# plugins/rollback.py
"""
Plugin for rolling back the bot to a previous deployment using GitHub tags.
Only admins can execute rollback commands.
"""

import re
import logging
import os
from slack_bolt import App
from services.github_service import rollback_to_tag

def register(app: App):
    """
    Register the Rollback plugin with the given Slack Bolt app.

    Args:
        app (App): The Slack Bolt App instance to register event listeners with.
    """
    logger = logging.getLogger(__name__)
    logger.setLevel(logging.INFO)

    # Create a console handler with a higher log level
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)

    # Create a formatter and set it for the handler
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    console_handler.setFormatter(formatter)

    # Add the handler to the logger if it doesn't already have handlers
    if not logger.hasHandlers():
        logger.addHandler(console_handler)

    # Retrieve admin user IDs from environment variable (comma-separated)
    ADMIN_USER_IDS = os.environ.get("ADMIN_USER_IDS", "")
    ADMIN_USER_IDS = set(uid.strip() for uid in ADMIN_USER_IDS.split(",") if uid.strip())

    if not ADMIN_USER_IDS:
        logger.warning("No ADMIN_USER_IDS defined. Only the bot itself can perform admin actions.")

    # Regex to parse commands: "rollback last" or "rollback to <tag>"
    ROLLBACK_LAST_REGEX = re.compile(r"^rollback\s+last$", re.IGNORECASE)
    ROLLBACK_TO_REGEX = re.compile(r"^rollback\s+to\s+(?P<tag>[\w-]+)$", re.IGNORECASE)

    @app.event("app_mention")
    def handle_app_mention_events(event, say, logger):
        """
        Handle 'app_mention' events to process rollback commands.

        Expected command formats:
            - "@BotName rollback last"
            - "@BotName rollback to <tag>"

        Args:
            event (dict): The event payload from Slack.
            say (function): Function to send messages back to Slack.
            logger (Logger): Logger instance for logging.
        """
        user_id = event.get("user")
        text = event.get("text", "")

        if not user_id or not text:
            logger.warning("Received app_mention event without user ID or text.")
            return

        # Remove all bot mentions from the text
        # Slack mentions are in the format <@U12345678>
        mention_pattern = re.compile(r"<@[\w]+>")
        stripped_text = mention_pattern.sub("", text).strip()

        if not stripped_text:
            say(f"<@{user_id}>, please provide a rollback command after mentioning me.")
            return

        # Check if the user is an admin
        is_admin = user_id in ADMIN_USER_IDS
        if not is_admin:
            say(f"<@{user_id}>, you do not have permission to perform this action.")
            logger.info(f"Unauthorized user {user_id} attempted to execute rollback.")
            return

        # Attempt to match 'rollback last' command
        if ROLLBACK_LAST_REGEX.match(stripped_text):
            logger.info(f"Admin {user_id} requested rollback to the last deployment.")
            try:
                # Fetch the last deployment tag from GitHub
                # This function should be implemented in github_service.py
                last_tag = get_last_deployment_tag()
                if not last_tag:
                    say("No previous deployment tags found. Cannot perform rollback.")
                    logger.error("No previous deployment tags found.")
                    return

                # Perform the rollback
                rollback_to_tag(last_tag)
                say(f"Successfully rolled back to the last deployment: `{last_tag}`.")
                logger.info(f"Successfully rolled back to tag '{last_tag}'.")
            except Exception as e:
                say("An error occurred while attempting to rollback. Please try again later.")
                logger.error(f"Error during rollback to last deployment: {e}")
            return

        # Attempt to match 'rollback to <tag>' command
        rollback_to_match = ROLLBACK_TO_REGEX.match(stripped_text)
        if rollback_to_match:
            target_tag = rollback_to_match.group("tag")
            logger.info(f"Admin {user_id} requested rollback to tag '{target_tag}'.")
            try:
                # Perform the rollback to the specified tag
                rollback_to_tag(target_tag)
                say(f"Successfully rolled back to deployment: `{target_tag}`.")
                logger.info(f"Successfully rolled back to tag '{target_tag}'.")
            except Exception as e:
                say(f"An error occurred while attempting to rollback to `{target_tag}`. Please try again later.")
                logger.error(f"Error during rollback to tag '{target_tag}': {e}")
            return

        # If command not recognized
        say("Could not parse rollback command. Use `rollback last` or `rollback to <tag>`.")
        logger.info(f"User {user_id} sent an unrecognized rollback command: '{stripped_text}'")

def get_last_deployment_tag() -> str:
    """
    Retrieves the last deployment tag from GitHub.

    Returns:
        str: The last deployment tag.

    Raises:
        Exception: If unable to fetch tags or no tags are found.
    """
    import requests

    GITHUB_API_URL = "https://api.github.com/repos/{owner}/{repo}/tags"
    GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN")
    OWNER = os.environ.get("GITHUB_OWNER")  # e.g., "your-username"
    REPO = os.environ.get("GITHUB_REPO")    # e.g., "your-repo"

    if not GITHUB_TOKEN or not OWNER or not REPO:
        raise Exception("GITHUB_TOKEN, GITHUB_OWNER, and GITHUB_REPO must be set as environment variables.")

    headers = {
        "Authorization": f"token {GITHUB_TOKEN}",
        "Accept": "application/vnd.github.v3+json"
    }

    response = requests.get(GITHUB_API_URL.format(owner=OWNER, repo=REPO), headers=headers)
    if response.status_code != 200:
        raise Exception(f"GitHub API responded with status code {response.status_code}: {response.text}")

    tags = response.json()
    if not tags:
        raise Exception("No tags found in the GitHub repository.")

    # Assuming the tags are sorted by creation date, latest first
    last_tag = tags[0].get("name")
    if not last_tag:
        raise Exception("Latest tag does not have a name.")

    return last_tag
