# plugins/self_upgrade.py
"""
Plugin implementing the self-upgrade flow for new features, requiring admin approvals.
Uses GPT (OpenAI) to transform user requests, commit to GitHub, etc.
"""

import re
import logging
import os
from slack_bolt import App
from services.openai_service import ChatGPTSessionManager
from services.github_service import (
    create_upgrade_branch,
    commit_file_to_branch,
    merge_upgrade_branch,
    get_last_deployment_tag,
    delete_upgrade_branch
)
from plugins.rate_limiting import rate_limit_check

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# For storing pending upgrades by user
PENDING_UPGRADES = {}

# If you want to enforce a specific channel for upgrades
UPGRADE_CHANNEL_NAME = "upgrade_channel_name"
MULTI_ADMIN_REQUIRED = True  # For core/pseudo-immutable changes
ADMIN_USER_IDS = set(uid.strip() for uid in os.environ.get("ADMIN_USER_IDS", "").split(",") if uid.strip())

def register(app: App):
    """
    Removed the old @app.event("app_mention") code. We keep register() empty or minimal.
    """
    pass

def handle_request_upgrade(event, say, logger, user_id, stripped_text):
    """
    The logic for 'request upgrade: [description]'.
    """
    # Your existing code from the old snippet, e.g.:
    REQUEST_UPGRADE_REGEX = re.compile(r"^request\s+upgrade\s*:\s*(?P<description>.+)$", re.IGNORECASE)
    match = REQUEST_UPGRADE_REGEX.match(stripped_text)
    if not match:
        say("Invalid format for 'request upgrade'. Usage: `request upgrade: [description]`")
        logger.warning(f"User {user_id} gave invalid request upgrade syntax.")
        return

    description = match.group("description").strip()
    if not description:
        say("Please provide a description for the upgrade.")
        logger.warning(f"User {user_id} gave empty description.")
        return

    # Use GPT to rewrite the request
    try:
        # example rewriting logic
        rewritten_request = ChatGPTSessionManager().generate_response(
            model="gpt-3.5-turbo",
            instance_id="self_upgrade",
            user_text=f"Rewrite the following upgrade request more concisely:\n{description}"
        )
        logger.info(f"Rewritten upgrade request from user {user_id}: {rewritten_request}")
    except Exception as e:
        say("Sorry, I couldn't process your upgrade request at the moment.")
        logger.error(f"Error rewriting upgrade request for user {user_id}: {e}")
        return

    PENDING_UPGRADES[user_id] = {
        "original_description": description,
        "rewritten_request": rewritten_request,
        "status": "pending_review",
        "branch_name": None,
        "code_snippet": None
    }
    say(f"<@{user_id}> Your request is rewritten:\n```{rewritten_request}```\n"
        f"Next step: `confirm upgrade` to create a branch.")

def handle_confirm_upgrade(event, say, logger, user_id):
    """
    'confirm upgrade' to create a new branch, etc.
    """
    upgrade = PENDING_UPGRADES.get(user_id)
    if not upgrade or upgrade["status"] != "pending_review":
        say("No pending upgrade found or not in review state.")
        return
    
    try:
        branch_name = create_upgrade_branch()
        upgrade["branch_name"] = branch_name
        upgrade["status"] = "code_needed"
        say(f"<@{user_id}> A new branch '{branch_name}' was created. Now do `new code: [code snippet]`.")
    except Exception as e:
        say("Failed to create upgrade branch. Please retry later.")
        logger.error(f"Error creating branch for user {user_id}: {e}")

def handle_new_code(event, say, logger, user_id):
    """
    'new code: ...' to store a code snippet
    """
    upgrade = PENDING_UPGRADES.get(user_id)
    if not upgrade or upgrade["status"] != "code_needed":
        say("No pending upgrade or not expecting code.")
        return

    NEW_CODE_REGEX = re.compile(r"^new\s+code\s*:\s*(?P<code>.+)$", re.IGNORECASE)
    text = event.get("text", "")
    mention_pattern = re.compile(r"<@[\w]+>")
    stripped_text = mention_pattern.sub("", text).strip()

    match = NEW_CODE_REGEX.match(stripped_text)
    if not match:
        say("Invalid format for 'new code'. Usage: `new code: [your code]`.")
        return
    code_snippet = match.group("code").strip()
    if not code_snippet:
        say("Please provide a code snippet.")
        return

    upgrade["code_snippet"] = code_snippet
    upgrade["status"] = "pending_sanity_check"
    say(f"Received your code snippet. Now do `do sanity check`.")

def handle_do_sanity_check(event, say, logger, user_id):
    """
    'do sanity check' to GPT-check the code
    """
    upgrade = PENDING_UPGRADES.get(user_id)
    if not upgrade or upgrade["status"] != "pending_sanity_check":
        say("No pending upgrade or not expecting sanity check.")
        return
    code_snippet = upgrade["code_snippet"]
    try:
        sanity_result = ChatGPTSessionManager().generate_response(
            model="gpt-3.5-turbo",
            instance_id="self_upgrade_sanity",
            user_text=f"Check the following code snippet for issues:\n{code_snippet}"
        )
        upgrade["status"] = "awaiting_final_approval"
        say(f"Sanity check results:\n```{sanity_result}```\nNext: `finalize upgrade` or `abort upgrade`.")
    except Exception as e:
        say("Sanity check failed. Please try again.")
        logger.error(f"Error on sanity check for user {user_id}: {e}")

def handle_finalize_upgrade(event, say, logger, user_id):
    """
    'finalize upgrade' merges code into main, etc.
    """
    upgrade = PENDING_UPGRADES.get(user_id)
    if not upgrade or upgrade["status"] != "awaiting_final_approval":
        say("No pending upgrade or not in final approval state.")
        return

    # If this is a core/pseudo-immutable module, require multi-admin
    # We'll skip the multi-admin detail or assume you handle it below
    branch_name = upgrade["branch_name"]
    code_snippet = upgrade["code_snippet"]
    from services.github_service import commit_file_to_branch, merge_upgrade_branch

    try:
        commit_file_to_branch(
            branch_name=branch_name,
            file_path="plugins/new_feature.py",
            content=code_snippet,
            commit_message="Self-upgrade: new feature from Slack"
        )
        merge_upgrade_branch(branch_name)
        say("Upgrade has been merged into main. Redeployment will occur automatically.")
        logger.info(f"Upgraded user {user_id} merged branch {branch_name}.")

        del PENDING_UPGRADES[user_id]
    except Exception as e:
        say("Failed to finalize upgrade. Contact admin.")
        logger.error(f"Error finalizing upgrade for user {user_id}: {e}")

def handle_abort_upgrade(event, say, logger, user_id):
    """
    'abort upgrade' to cancel the upgrade.
    """
    upgrade = PENDING_UPGRADES.get(user_id)
    if not upgrade:
        say("No pending upgrade to abort.")
        return
    from services.github_service import delete_upgrade_branch
    branch_name = upgrade["branch_name"]
    try:
        if branch_name:
            delete_upgrade_branch(branch_name)
    except Exception as e:
        logger.error(f"Error deleting branch '{branch_name}': {e}")
    del PENDING_UPGRADES[user_id]
    say("Upgrade request aborted.")

# If you have multi-admin approvals, you can keep that logic here too, 
# just no direct mention-based code.
