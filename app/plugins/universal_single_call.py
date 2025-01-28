# plugins/universal_single_call.py
import os
import json
import logging
import openai
from slack_bolt import App

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# In-memory trackers
# Key: user_id -> (action, data?), if waiting for "yes" to confirm
PENDING_CONFIRMATIONS = {}

# Example environment-based admin check (optional)
ADMIN_USER_IDS = set(os.environ.get("ADMIN_USER_IDS", "").split(","))

# Suppose we rely on openai_service.py for:
#   - BOT_ROLE, BOT_TEMPERATURE
#   - AVAILABLE_MODELS
#   - process_request(...) or generate_response(...) if we do normal GPT chat
import services.openai_service as openai_service
from services.github_service import rollback_to_tag

# A system prompt that tells GPT how to produce the JSON snippet
SYSTEM_PROMPT = """\
You are a Slackbot that merges multiple functionalities in one pass:
1) If user requests code from a file, set:
   "action":"show_code", "filename":"<the file>", ...
2) If user wants to override the bot's role, set:
   "action":"override_role", "role_value":"<the new role>"
3) If user wants to update GPT model, set:
   "action":"update_model", "model_name":"<the new model>"
4) If user wants to do a rollback, set:
   "action":"rollback", "rollback_target":"<version/tag>"
5) If user is just chatting, set "action":"none" or "other".
6) If user specifically or implicitly indicates 'upgrade' or something risky, set "confirmation_needed":true.
7) Return normal chat text, then append a single JSON snippet:

<<JSON:
{
  "action": "...",
  "filename": "...",
  "confirmation_needed": false,
  "role_value": "",
  "model_name": "",
  "rollback_target": "",
  "explanation": "..."
}
JSON>>

The JSON must be valid and parseable. 
"""

def read_any_file(filepath: str) -> str:
    """
    Reads a file from disk with no restrictions.
    """
    if not os.path.isfile(filepath):
        return f"File not found: {filepath}"
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            content = f.read()
        return f"```python\n{content}\n```"
    except Exception as e:
        return f"Error reading file '{filepath}': {str(e)}"

def register(app: App):
    @app.message(lambda msg: True)
    def handle_all_messages(message, say):
        user_id = message.get("user", "")
        text = message.get("text", "").strip()

        # 1) Check if user is confirming an action:
        if text.lower() == "yes":
            if user_id in PENDING_CONFIRMATIONS:
                # We stored something like ("show_code", filename) or ("rollback", target)
                pending_action, pending_data = PENDING_CONFIRMATIONS.pop(user_id)
                if pending_action == "show_code":
                    file_content = read_any_file(pending_data)
                    say(f"<@{user_id}> (Confirmed) Here's `{pending_data}`:\n{file_content}")
                elif pending_action == "rollback":
                    # Example: do rollback
                    rollback_to_tag(pending_data)
                    say(f"<@{user_id}> Rolled back to {pending_data} (confirmed).")
                elif pending_action == "override_role":
                    openai_service.BOT_ROLE = pending_data
                    say(f"<@{user_id}> Overrode bot role to: {pending_data}")
                elif pending_action == "update_model":
                    if pending_data not in openai_service.AVAILABLE_MODELS:
                        say(f"<@{user_id}> Model '{pending_data}' is not in AVAILABLE_MODELS.")
                    else:
                        openai_service.DEFAULT_MODEL = pending_data
                        say(f"<@{user_id}> Updated default GPT model to {pending_data}.")
                else:
                    say(f"<@{user_id}> Confirmed, but unknown action '{pending_action}'?")
                return
            # else no pending confirmations, fall through to normal flow

        # 2) Single GPT call for classification + normal text
        try:
            response = openai.ChatCompletion.create(
                model="gpt-3.5-turbo",  # or gpt-4
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": text}
                ],
                temperature=0.7
            )
            gpt_answer = response["choices"][0]["message"]["content"]
        except Exception as e:
            logger.error(f"GPT error: {e}")
            say(f"<@{user_id}> Sorry, I encountered an error calling GPT.")
            return

        # 3) Extract JSON snippet from GPT's answer
        start_tag = "<<JSON:"
        end_tag = "JSON>>"

        user_facing_text = gpt_answer
        action = "none"
        filename = ""
        confirmation_needed = False
        role_value = ""
        model_name = ""
        rollback_target = ""

        start_idx = gpt_answer.find(start_tag)
        end_idx = gpt_answer.find(end_tag)
        if start_idx != -1 and end_idx != -1 and end_idx > start_idx:
            # Extract
            json_part = gpt_answer[start_idx + len(start_tag):end_idx].strip()
            user_facing_text = (gpt_answer[:start_idx] + gpt_answer[end_idx + len(end_tag):]).strip()
            try:
                data = json.loads(json_part)
                action = data.get("action", "none")
                filename = data.get("filename", "")
                confirmation_needed = data.get("confirmation_needed", False)
                role_value = data.get("role_value", "")
                model_name = data.get("model_name", "")
                rollback_target = data.get("rollback_target", "")
            except Exception as e:
                logger.warning(f"Could not parse GPT JSON block: {e}")

        # 4) Send the user-facing text to Slack (the conversation part)
        if user_facing_text:
            say(f"<@{user_id}> {user_facing_text}")

        # 5) Handle the action
        if action == "show_code":
            # If confirmation needed, store & prompt
            if confirmation_needed:
                PENDING_CONFIRMATIONS[user_id] = ("show_code", filename)
                say(f"<@{user_id}> GPT flagged this as an upgrade or risky. Type 'yes' to confirm showing `{filename}`.")
            else:
                # Show code immediately
                code_content = read_any_file(filename)
                say(f"<@{user_id}> Here's `{filename}`:\n{code_content}")

        elif action == "override_role":
            # Possibly check admin?
            if user_id not in ADMIN_USER_IDS:
                say(f"<@{user_id}> Sorry, you are not an admin. Can't override role.")
                return
            if confirmation_needed:
                PENDING_CONFIRMATIONS[user_id] = ("override_role", role_value)
                say(f"<@{user_id}> Type 'yes' to confirm overriding bot role to:\n{role_value}")
            else:
                openai_service.BOT_ROLE = role_value
                say(f"<@{user_id}> Overrode bot role to: {role_value}")

        elif action == "update_model":
            # Check if user is admin, or skip if all users allowed
            if user_id not in ADMIN_USER_IDS:
                say(f"<@{user_id}> Sorry, you are not authorized to update the model.")
                return
            if confirmation_needed:
                PENDING_CONFIRMATIONS[user_id] = ("update_model", model_name)
                say(f"<@{user_id}> Type 'yes' to confirm updating GPT model to '{model_name}'")
            else:
                if model_name not in openai_service.AVAILABLE_MODELS:
                    say(f"<@{user_id}> Model '{model_name}' not in AVAILABLE_MODELS.")
                else:
                    openai_service.DEFAULT_MODEL = model_name
                    say(f"<@{user_id}> Updated default GPT model to {model_name}.")

        elif action == "rollback":
            if user_id not in ADMIN_USER_IDS:
                say(f"<@{user_id}> Sorry, you're not allowed to do rollback.")
                return
            if confirmation_needed:
                PENDING_CONFIRMATIONS[user_id] = ("rollback", rollback_target)
                say(f"<@{user_id}> Type 'yes' to confirm rollback to '{rollback_target}'")
            else:
                rollback_to_tag(rollback_target)
                say(f"<@{user_id}> Rolled back immediately to {rollback_target}.")

        # else if none or other, do nothing special
        # We already responded with normal text from GPT

