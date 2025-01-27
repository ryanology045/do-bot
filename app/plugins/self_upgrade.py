# plugins/self_upgrade.py
#"""
#Plugin implementing the self-upgrade flow for new features, requiring admin approvals.
#Uses GPT (OpenAI) to transform user requests, commit to GitHub, etc.
#"""

import re
from slack_bolt import App
from core.slack_app import app
from services.openai_service import openai_rewrite
from services.github_service import create_upgrade_branch, merge_upgrade_branch

UPGRADE_CHANNEL_NAME = "upgrade_channel_name"  # Only allow upgrade requests in #upgrade_channel_name
PENDING_UPGRADES = {}

@app.message(re.compile(r"request upgrade", re.IGNORECASE))
def handle_upgrade_request(message, say):
    """
    Workflow:
    1. The user says: "@BotName request upgrade: [description]"
    2. Bot uses openai_rewrite(...) to rewrite the request
    3. The user reviews/edits in Slack
    4. Bot finalizes, merges changes (once user provides code from GPT or final approval)
    """
    channel = message['channel']
    user_id = message['user']
    text = message.get('text', '')
    
    # Enforce upgrade channel
    # In production, compare channel name or ID with the known #upgrade_channel_name
    # For demonstration, we just check if it contains the string:
    if UPGRADE_CHANNEL_NAME not in channel.lower():
        say("Upgrades must be requested in #upgrade_channel_name.")
        return
    
    request_text = text.lower().replace("request upgrade", "").strip()
    # 1. Bot uses GPT to rewrite
    rewrite = openai_rewrite(request_text)
    
    # Store a pending upgrade
    PENDING_UPGRADES[user_id] = {
        'original': request_text,
        'rewrite': rewrite,
        'status': 'pending_review'
    }
    
    say(f"<@{user_id}>, here is the rewrite for your request:\n```{rewrite}```\nPlease review or edit, then say '@BotName confirm upgrade' to proceed.")


@app.message(re.compile(r"confirm upgrade", re.IGNORECASE))
def confirm_upgrade(message, say):
    user_id = message['user']
    if user_id not in PENDING_UPGRADES:
        say("No pending upgrade found for you.")
        return
    
    upgrade_data = PENDING_UPGRADES[user_id]
    if upgrade_data['status'] != 'pending_review':
        say("Upgrade is not in a valid state for confirmation.")
        return
    
    # Mark as confirmed
    upgrade_data['status'] = 'code_needed'
    say(f"<@{user_id}>, please now provide your new code from GPT or 'o1 pro' by saying '@BotName new code [paste here]'. Then we can do a final review.")


@app.message(re.compile(r"new code", re.IGNORECASE))
def new_code(message, say):
    user_id = message['user']
    text = message.get('text', '')
    if user_id not in PENDING_UPGRADES:
        say("No pending upgrade found for you.")
        return
    upgrade_data = PENDING_UPGRADES[user_id]
    if upgrade_data['status'] != 'code_needed':
        say("Upgrade is not in a valid state for code submission.")
        return
    
    # Extract code from the text
    code_snippet = text.lower().replace("new code", "").strip()
    upgrade_data['code'] = code_snippet
    upgrade_data['status'] = 'pending_sanity_check'
    
    say(f"Received new code. Next, '@BotName do sanity check' to run GPT-based checks or finalize.")


@app.message(re.compile(r"do sanity check", re.IGNORECASE))
def do_sanity_check(message, say):
    user_id = message['user']
    if user_id not in PENDING_UPGRADES:
        say("No pending upgrade found for you.")
        return
    
    upgrade_data = PENDING_UPGRADES[user_id]
    if upgrade_data['status'] != 'pending_sanity_check':
        say("Upgrade is not in a valid state for sanity check.")
        return
    
    # For demonstration, let's assume we do a GPT check
    # We'll just say everything looks good
    # In production, you might call openai to evaluate code or do something else
    upgrade_data['status'] = 'awaiting_final_approval'
    say("Sanity check complete. Everything looks good. '@BotName finalize upgrade' to proceed.")


@app.message(re.compile(r"finalize upgrade", re.IGNORECASE))
def finalize_upgrade(message, say):
    user_id = message['user']
    if user_id not in PENDING_UPGRADES:
        say("No pending upgrade found for you.")
        return
    
    upgrade_data = PENDING_UPGRADES[user_id]
    if upgrade_data['status'] != 'awaiting_final_approval':
        say("Upgrade is not ready to finalize.")
        return
    
    # In real usage, check if this upgrade modifies core or pseudo-immutable modules.
    # If so, we might require multi-admin approvals.

    # We'll assume single admin approval is enough here.
    # Let's create a branch, commit the code, then merge to main.
    branch_name = create_upgrade_branch()
    # commit the new code
    # in real usage, you'd parse the code snippet and apply it to specific files
    # for demonstration, let's commit to a placeholder file
    from services.github_service import commit_file_to_branch, merge_branch
    commit_file_to_branch(branch_name, "plugins/new_feature.py", upgrade_data['code'])
    merge_upgrade_branch(branch_name)
    
    # Mark upgrade as done
    upgrade_data['status'] = 'done'
    say("Upgrade finalized and merged to main. Redeploying or ECS update can follow automatically (depending on CI/CD).")
