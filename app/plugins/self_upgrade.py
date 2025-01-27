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
    get_last_deployment_tag
)
from plugins.rate_limiting import rate_limit_check

def register(app: App):
    """
    Register the Self-Upgrade plugin with the given Slack Bolt app.
    
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
    
    # Constants
    UPGRADE_CHANNEL_NAME = "upgrade_channel_name"  # Only allow upgrade requests in #upgrade_channel_name
    MULTI_ADMIN_REQUIRED = True  # Set to True if core/pseudo-immutable changes require multi-admin approvals
    
    # In-memory storage for pending upgrades
    # Key: user_id, Value: upgrade_data dict
    PENDING_UPGRADES = {}
    
    # Regex patterns
    REQUEST_UPGRADE_REGEX = re.compile(r"^request\s+upgrade\s*:\s*(?P<description>.+)$", re.IGNORECASE)
    CONFIRM_UPGRADE_REGEX = re.compile(r"^confirm\s+upgrade$", re.IGNORECASE)
    NEW_CODE_REGEX = re.compile(r"^new\s+code\s*:\s*(?P<code>.+)$", re.IGNORECASE)
    DO_SANITY_CHECK_REGEX = re.compile(r"^do\s+sanity\s+check$", re.IGNORECASE)
    FINALIZE_UPGRADE_REGEX = re.compile(r"^finalize\s+upgrade$", re.IGNORECASE)
    
    # Admin User IDs (comma-separated Slack user IDs)
    ADMIN_USER_IDS = set(uid.strip() for uid in os.environ.get("ADMIN_USER_IDS", "").split(",") if uid.strip())
    if not ADMIN_USER_IDS:
        logger.warning("No ADMIN_USER_IDS defined. Only the bot itself can perform admin actions.")
    
    @app.event("app_mention")
    def handle_app_mention_events(event, say, logger):
        """
        Handle 'app_mention' events to process self-upgrade commands.
        
        Expected command formats:
            - "@BotName request upgrade: [description]"
            - "@BotName confirm upgrade"
            - "@BotName new code: [code_snippet]"
            - "@BotName do sanity check"
            - "@BotName finalize upgrade"
        
        Args:
            event (dict): The event payload from Slack.
            say (function): Function to send messages back to Slack.
            logger (Logger): Logger instance for logging.
        """
        user_id = event.get("user")
        channel_id = event.get("channel")
        text = event.get("text", "")
        
        if not user_id or not text:
            logger.warning("Received app_mention event without user ID or text.")
            return
        
        # Enforce upgrade channel
        channel_name = get_channel_name(channel_id)
        if UPGRADE_CHANNEL_NAME.lower() not in channel_name.lower():
            say("Upgrades must be requested in #upgrade_channel_name.")
            logger.info(f"Upgrade request from user {user_id} in unauthorized channel '{channel_name}'.")
            return
        
        # Remove all bot mentions from the text
        # Slack mentions are in the format <@U12345678>
        mention_pattern = re.compile(r"<@[\w]+>")
        stripped_text = mention_pattern.sub("", text).strip()
        
        if not stripped_text:
            say(f"<@{user_id}>, please provide a command after mentioning me.")
            return
        
        # Check rate limiting
        if not rate_limit_check(user_id):
            say(f"<@{user_id}>, you've hit the rate limit. Try again later or request an admin override.")
            logger.info(f"User {user_id} hit the rate limit during self-upgrade request.")
            return
        
        # Parse the command
        if REQUEST_UPGRADE_REGEX.match(stripped_text):
            handle_request_upgrade(event, say, logger, user_id, stripped_text)
        elif CONFIRM_UPGRADE_REGEX.match(stripped_text):
            handle_confirm_upgrade(event, say, logger, user_id)
        elif NEW_CODE_REGEX.match(stripped_text):
            handle_new_code(event, say, logger, user_id)
        elif DO_SANITY_CHECK_REGEX.match(stripped_text):
            handle_do_sanity_check(event, say, logger, user_id)
        elif FINALIZE_UPGRADE_REGEX.match(stripped_text):
            handle_finalize_upgrade(event, say, logger, user_id)
        else:
            say("Unrecognized command. Available commands:\n"
                "- `request upgrade: [description]`\n"
                "- `confirm upgrade`\n"
                "- `new code: [code_snippet]`\n"
                "- `do sanity check`\n"
                "- `finalize upgrade`")
            logger.info(f"User {user_id} sent an unrecognized self-upgrade command: '{stripped_text}'")
    
    def get_channel_name(channel_id: str) -> str:
        """
        Retrieves the channel name given its ID using Slack Web API.
        
        Args:
            channel_id (str): The Slack channel ID.
        
        Returns:
            str: The Slack channel name.
        """
        from slack_sdk import WebClient
        from slack_sdk.errors import SlackApiError
        
        client = WebClient(token=os.environ.get("SLACK_BOT_TOKEN"))
        try:
            response = client.conversations_info(channel=channel_id)
            return response['channel']['name']
        except SlackApiError as e:
            logger.error(f"Error fetching channel info for {channel_id}: {e.response['error']}")
            return ""
    
    def handle_request_upgrade(event, say, logger, user_id, stripped_text):
        """
        Handles the 'request upgrade' command.
        
        Args:
            event (dict): The event payload from Slack.
            say (function): Function to send messages back to Slack.
            logger (Logger): Logger instance for logging.
            user_id (str): Slack user ID.
            stripped_text (str): The command text without bot mentions.
        """
        match = re.match(r"^request\s+upgrade\s*:\s*(?P<description>.+)$", stripped_text, re.IGNORECASE)
        if not match:
            say("Invalid format for 'request upgrade'. Usage: `request upgrade: [description]`")
            logger.warning(f"User {user_id} sent invalid 'request upgrade' command.")
            return
        
        description = match.group("description").strip()
        if not description:
            say("Please provide a description for the upgrade.")
            logger.warning(f"User {user_id} provided empty description for upgrade request.")
            return
        
        # Use GPT to rewrite the request
        try:
            rewritten_request = ChatGPTSessionManager.generate_response(
                model="gpt-3.5-turbo",  # Or any preferred model
                instance_id="self_upgrade",  # Using a fixed instance ID for self-upgrade
                user_text=f"Rewrite the following upgrade request for implementation: {description}"
            )
            logger.info(f"Rewritten upgrade request for user {user_id}: {rewritten_request}")
        except Exception as e:
            say("Sorry, I couldn't process your request at the moment.")
            logger.error(f"Error rewriting upgrade request for user {user_id}: {e}")
            return
        
        # Store the pending upgrade
        PENDING_UPGRADES[user_id] = {
            'original_description': description,
            'rewritten_request': rewritten_request,
            'status': 'pending_review',
            'branch_name': None,
            'code_snippet': None
        }
        
        say(f"<@{user_id}>, here is the rewritten request:\n```{rewritten_request}```\n"
            f"Please review or edit, then confirm the upgrade by saying `confirm upgrade`.")
    
    def handle_confirm_upgrade(event, say, logger, user_id):
        """
        Handles the 'confirm upgrade' command.
        
        Args:
            event (dict): The event payload from Slack.
            say (function): Function to send messages back to Slack.
            logger (Logger): Logger instance for logging.
            user_id (str): Slack user ID.
        """
        upgrade = PENDING_UPGRADES.get(user_id)
        if not upgrade or upgrade['status'] != 'pending_review':
            say("No pending upgrade found or upgrade is not in a state to be confirmed.")
            logger.warning(f"User {user_id} attempted to confirm upgrade without a valid pending upgrade.")
            return
        
        # Proceed to create an upgrade branch in GitHub
        try:
            branch_name = create_upgrade_branch()
            upgrade['branch_name'] = branch_name
            logger.info(f"Created upgrade branch '{branch_name}' for user {user_id}.")
        except Exception as e:
            say("Failed to initiate the upgrade process. Please try again later.")
            logger.error(f"Error creating upgrade branch for user {user_id}: {e}")
            return
        
        upgrade['status'] = 'code_needed'
        say(f"<@{user_id}>, please provide your new code by saying `new code: [paste your code here]`. "
            f"This code will be merged into the upgrade branch `{branch_name}`.")
    
    def handle_new_code(event, say, logger, user_id):
        """
        Handles the 'new code' command.
        
        Args:
            event (dict): The event payload from Slack.
            say (function): Function to send messages back to Slack.
            logger (Logger): Logger instance for logging.
            user_id (str): Slack user ID.
        """
        upgrade = PENDING_UPGRADES.get(user_id)
        if not upgrade or upgrade['status'] != 'code_needed':
            say("No pending upgrade found or upgrade is not in a state to accept new code.")
            logger.warning(f"User {user_id} attempted to submit code without a valid pending upgrade.")
            return
        
        match = re.match(r"^new\s+code\s*:\s*(?P<code>.+)$", stripped_text := event.get("text", ""), re.IGNORECASE)
        if not match:
            say("Invalid format for 'new code'. Usage: `new code: [your code snippet]`")
            logger.warning(f"User {user_id} sent invalid 'new code' command.")
            return
        
        code_snippet = match.group("code").strip()
        if not code_snippet:
            say("Please provide a valid code snippet.")
            logger.warning(f"User {user_id} provided empty code snippet.")
            return
        
        upgrade['code_snippet'] = code_snippet
        upgrade['status'] = 'pending_sanity_check'
        
        say(f"<@{user_id}>, received your code snippet. Next, perform a sanity check by saying `do sanity check`.")
        logger.info(f"Received code snippet from user {user_id} for upgrade.")
    
    def handle_do_sanity_check(event, say, logger, user_id):
        """
        Handles the 'do sanity check' command.
        
        Args:
            event (dict): The event payload from Slack.
            say (function): Function to send messages back to Slack.
            logger (Logger): Logger instance for logging.
            user_id (str): Slack user ID.
        """
        upgrade = PENDING_UPGRADES.get(user_id)
        if not upgrade or upgrade['status'] != 'pending_sanity_check':
            say("No pending upgrade found or upgrade is not in a state for sanity check.")
            logger.warning(f"User {user_id} attempted to perform sanity check without a valid pending upgrade.")
            return
        
        # Use GPT to perform a sanity check on the provided code
        try:
            sanity_check_response = ChatGPTSessionManager.generate_response(
                model="gpt-3.5-turbo",  # Or any preferred model
                instance_id="self_upgrade_sanity",
                user_text=f"Perform a sanity check on the following code snippet and report any issues or improvements:\n{upgrade['code_snippet']}"
            )
            logger.info(f"Sanity check result for user {user_id}: {sanity_check_response}")
        except Exception as e:
            say("Sanity check failed due to an internal error. Please try again later.")
            logger.error(f"Error performing sanity check for user {user_id}: {e}")
            return
        
        upgrade['status'] = 'awaiting_final_approval'
        say(f"Sanity check complete. Here's the feedback:\n```{sanity_check_response}```\n"
            f"If everything looks good, confirm the upgrade by saying `finalize upgrade`. If you need to abort, say `abort upgrade`.")
    
    @app.message(re.compile(r"finalize\s+upgrade", re.IGNORECASE))
    def handle_finalize_upgrade(event, say, logger, user_id):
        """
        Handles the 'finalize upgrade' command.
        
        Args:
            event (dict): The event payload from Slack.
            say (function): Function to send messages back to Slack.
            logger (Logger): Logger instance for logging.
            user_id (str): Slack user ID.
        """
        upgrade = PENDING_UPGRADES.get(user_id)
        if not upgrade or upgrade['status'] != 'awaiting_final_approval':
            say("No pending upgrade found or upgrade is not in a state to be finalized.")
            logger.warning(f"User {user_id} attempted to finalize upgrade without a valid pending upgrade.")
            return
        
        # Check if the upgrade modifies core or pseudo-immutable modules
        # For demonstration, let's assume all upgrades are core changes requiring multi-admin approval
        is_core_change = True  # This should be determined based on the upgrade's nature
        
        if is_core_change and MULTI_ADMIN_REQUIRED:
            # Initiate multi-admin approval process
            initiate_multi_admin_approval(app, say, logger, user_id, upgrade)
            return
        
        # Proceed with single-admin approval
        try:
            # Commit the new code to the upgrade branch
            commit_file_to_branch(
                branch_name=upgrade['branch_name'],
                file_path="plugins/new_feature.py",  # Replace with actual file paths
                content=upgrade['code_snippet'],
                commit_message="Self-upgrade: Adding new feature"
            )
            logger.info(f"Committed new code to branch '{upgrade['branch_name']}' for user {user_id}.")
            
            # Merge the upgrade branch into main
            merge_upgrade_branch(upgrade['branch_name'])
            logger.info(f"Merged branch '{upgrade['branch_name']}' into main.")
            
            # Optionally, trigger a redeployment or ECS update via CI/CD pipeline
            say("Upgrade has been finalized and merged to main. Redeployment will occur automatically.")
            logger.info(f"Upgrade for user {user_id} has been successfully finalized.")
            
            # Clean up the pending upgrade
            del PENDING_UPGRADES[user_id]
        except Exception as e:
            say("Failed to finalize the upgrade due to an internal error. Please contact an admin.")
            logger.error(f"Error finalizing upgrade for user {user_id}: {e}")
    
    @app.message(re.compile(r"abort\s+upgrade", re.IGNORECASE))
    def handle_abort_upgrade(event, say, logger, user_id):
        """
        Handles the 'abort upgrade' command.
        
        Args:
            event (dict): The event payload from Slack.
            say (function): Function to send messages back to Slack.
            logger (Logger): Logger instance for logging.
            user_id (str): Slack user ID.
        """
        upgrade = PENDING_UPGRADES.get(user_id)
        if not upgrade:
            say("No pending upgrade found to abort.")
            logger.warning(f"User {user_id} attempted to abort a non-existent upgrade.")
            return
        
        # Optionally, delete the upgrade branch in GitHub
        try:
            from services.github_service import delete_upgrade_branch
            delete_upgrade_branch(upgrade['branch_name'])
            logger.info(f"Deleted upgrade branch '{upgrade['branch_name']}' for user {user_id}.")
        except Exception as e:
            logger.error(f"Error deleting upgrade branch '{upgrade['branch_name']}' for user {user_id}: {e}")
            # Not critical to inform the user about branch deletion failure
        
        # Remove the pending upgrade
        del PENDING_UPGRADES[user_id]
        say("Your upgrade request has been aborted.")
        logger.info(f"Upgrade request for user {user_id} has been aborted.")
    
    def initiate_multi_admin_approval(app: App, say, logger, requester_id: str, upgrade_data: dict):
        """
        Initiates a multi-admin approval process for critical upgrades.
        
        Args:
            app (App): The Slack Bolt App instance.
            say (function): Function to send messages back to Slack.
            logger (Logger): Logger instance for logging.
            requester_id (str): Slack user ID who requested the upgrade.
            upgrade_data (dict): The pending upgrade data.
        """
        # Retrieve all admin user IDs except the requester
        admin_ids = ADMIN_USER_IDS - {requester_id}
        if not admin_ids:
            say("No other admins available to approve the upgrade. Please contact an admin.")
            logger.error("No other admins available for multi-admin approval.")
            return
        
        # Notify all admins for approval
        approval_message = (f"<@{requester_id}> has requested a critical upgrade:\n"
                            f"**Rewritten Request:**\n```{upgrade_data['rewritten_request']}```\n"
                            f"Admins, please approve this upgrade by saying `approve upgrade for {requester_id}` "
                            f"or deny by saying `deny upgrade for {requester_id}`.")
        for admin_id in admin_ids:
            app.client.chat_postMessage(channel=admin_id, text=approval_message)
            logger.info(f"Sent upgrade approval request to admin {admin_id} for user {requester_id}.")
        
        # Update the upgrade status to pending admin approval
        upgrade_data['status'] = 'pending_admin_approval'
        PENDING_UPGRADES[requester_id] = upgrade_data
    
    # Regex patterns for admin approvals
    APPROVE_UPGRADE_REGEX = re.compile(r"^approve\s+upgrade\s+for\s+(?P<user_id>U[\w]+)$", re.IGNORECASE)
    DENY_UPGRADE_REGEX = re.compile(r"^deny\s+upgrade\s+for\s+(?P<user_id>U[\w]+)$", re.IGNORECASE)
    
    @app.event("app_mention")
    def handle_admin_approval_events(event, say, logger):
        """
        Handle admin approval events for critical upgrades.
        
        Expected command formats:
            - "@BotName approve upgrade for U12345678"
            - "@BotName deny upgrade for U12345678"
        
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
        
        # Only admins can approve or deny upgrades
        if user_id not in ADMIN_USER_IDS:
            return  # Ignore non-admin mentions for approvals
        
        # Remove all bot mentions from the text
        mention_pattern = re.compile(r"<@[\w]+>")
        stripped_text = mention_pattern.sub("", text).strip()
        
        if APPROVE_UPGRADE_REGEX.match(stripped_text):
            match = APPROVE_UPGRADE_REGEX.match(stripped_text)
            target_user_id = match.group("user_id")
            approve_upgrade(app, say, logger, target_user_id, approving_admin_id=user_id)
        elif DENY_UPGRADE_REGEX.match(stripped_text):
            match = DENY_UPGRADE_REGEX.match(stripped_text)
            target_user_id = match.group("user_id")
            deny_upgrade(app, say, logger, target_user_id, denying_admin_id=user_id)
    
    def approve_upgrade(app: App, say, logger, target_user_id: str, approving_admin_id: str):
        """
        Approves a pending upgrade for a specific user.
        
        Args:
            app (App): The Slack Bolt App instance.
            say (function): Function to send messages back to Slack.
            logger (Logger): Logger instance for logging.
            target_user_id (str): Slack user ID who requested the upgrade.
            approving_admin_id (str): Slack user ID of the admin approving the upgrade.
        """
        upgrade = PENDING_UPGRADES.get(target_user_id)
        if not upgrade or upgrade['status'] != 'pending_admin_approval':
            say(f"<@{approving_admin_id}>, no pending upgrade found for user <@{target_user_id}>.")
            logger.warning(f"Admin {approving_admin_id} attempted to approve non-existent upgrade for user {target_user_id}.")
            return
        
        # Proceed with the upgrade similar to single-admin approval
        try:
            # Commit the new code to the upgrade branch
            commit_file_to_branch(
                branch_name=upgrade['branch_name'],
                file_path="plugins/new_feature.py",  # Replace with actual file paths
                content=upgrade['code_snippet'],
                commit_message="Self-upgrade: Adding new feature"
            )
            logger.info(f"Committed new code to branch '{upgrade['branch_name']}' for user {target_user_id}.")
            
            # Merge the upgrade branch into main
            merge_upgrade_branch(upgrade['branch_name'])
            logger.info(f"Merged branch '{upgrade['branch_name']}' into main.")
            
            # Notify the requester
            say(f"<@{approving_admin_id}> approved the upgrade for <@{target_user_id}>. "
                f"Upgrade has been finalized and merged to main. Redeployment will occur automatically.")
            logger.info(f"Upgrade for user {target_user_id} has been approved and finalized by admin {approving_admin_id}.")
            
            # Clean up the pending upgrade
            del PENDING_UPGRADES[target_user_id]
        except Exception as e:
            say(f"Failed to approve the upgrade for <@{target_user_id}> due to an internal error.")
            logger.error(f"Error approving upgrade for user {target_user_id}: {e}")
    
    def deny_upgrade(app: App, say, logger, target_user_id: str, denying_admin_id: str):
        """
        Denies a pending upgrade for a specific user.
        
        Args:
            app (App): The Slack Bolt App instance.
            say (function): Function to send messages back to Slack.
            logger (Logger): Logger instance for logging.
            target_user_id (str): Slack user ID who requested the upgrade.
            denying_admin_id (str): Slack user ID of the admin denying the upgrade.
        """
        upgrade = PENDING_UPGRADES.get(target_user_id)
        if not upgrade or upgrade['status'] != 'pending_admin_approval':
            say(f"<@{denying_admin_id}>, no pending upgrade found for user <@{target_user_id}>.")
            logger.warning(f"Admin {denying_admin_id} attempted to deny non-existent upgrade for user {target_user_id}.")
            return
        
        # Optionally, delete the upgrade branch in GitHub
        try:
            from services.github_service import delete_upgrade_branch
            delete_upgrade_branch(upgrade['branch_name'])
            logger.info(f"Deleted upgrade branch '{upgrade['branch_name']}' for user {target_user_id}.")
        except Exception as e:
            logger.error(f"Error deleting upgrade branch '{upgrade['branch_name']}' for user {target_user_id}: {e}")
            # Not critical to inform the admin about branch deletion failure
        
        # Remove the pending upgrade
        del PENDING_UPGRADES[target_user_id]
        say(f"<@{denying_admin_id}> has denied the upgrade request for <@{target_user_id}>.")
        logger.info(f"Upgrade request for user {target_user_id} has been denied by admin {denying_admin_id}.")
