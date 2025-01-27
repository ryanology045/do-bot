# plugins/rollback.py
#"""
#Plugin for rolling back the bot to a previous deployment using GitHub tags.
#"""

import os
from slack_bolt import App
from core.slack_app import app
from services.github_service import rollback_to_tag

@app.message("rollback")
def rollback_command(message, say):
    text = message.get('text', '')
    parts = text.split()
    if len(parts) < 2:
        say("Usage: '@BotName rollback last' or '@BotName rollback to <tag>'.")
        return
    
    if "last" in parts:
        # Implement logic to get the last known deployment tag
        say("Rolling back to the last deployment version (placeholder).")
        # Example: "production-deployment-YYYYMMDD-HHMM"
        # For demonstration, let's say we pick the last from a known list:
        # In real usage, we'd fetch from GitHub or your versioning system
        last_tag = "production-deployment-20250127-0000"
        rollback_to_tag(last_tag)
        say(f"Rollback to {last_tag} completed.")
    elif "to" in parts:
        idx = parts.index("to")
        if idx == len(parts) - 1:
            say("Please specify a tag.")
        else:
            target_tag = parts[idx+1]
            rollback_to_tag(target_tag)
            say(f"Rollback to {target_tag} completed.")
