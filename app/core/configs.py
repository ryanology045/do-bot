# project_root/core/configs.py

bot_config = {
    # Default model for normal Q&A
    "default_qna_model": "gpt-3.5-turbo",

    # Roles definitions
    "roles_definitions": {
        "default": {
            "system_prompt": "You are a helpful assistant. Respond succinctly.",
            "temperature": 0.7,
            "description": "Default fallback role."
        },
        "friendly": {
            "system_prompt": "You are a friendly, upbeat assistant who greets warmly.",
            "temperature": 0.9,
            "description": "Cheerful persona."
        },
        "tech_expert": {
            "system_prompt": "You are a highly technical expert. Provide in-depth details.",
            "temperature": 0.6,
            "description": "Deep domain knowledge persona."
        }
    },

    # Single place for all large system prompts
    "initial_prompts": {
        "classification_system_prompt": """
You are the classification system with memory of prior messages.
Decide among:
 - ASKTHEWORLD => normal Q&A
 - ASKTHEBOT => user wants architecture details
 - CODER => any code or config modifications.
Output strictly valid JSON => { "request_type":"...", "role_info":"...", "extra_data": {...} }.
        """,

        "coder_system_prompt": """
You are a coding-oriented GPT. The user wants a Python code snippet or function. 
Return minimal, valid code. The function must be named 'generated_snippet' with no extra text.
If references to Slack or config, import from the correct paths:
 - from core.configs import bot_config
 - from services.slack_service import SlackService
No docstrings or disclaimers. Just the function code in Python 3.10 syntax.
        """,

        "bot_context": """
FULL BOT CONTEXT (Ultra-Expanded):
1) File Structure:
   - core/  (main.py, bot_engine.py, configs.py, module_manager.py, scheduler.py, snippets.py)
   - modules/ (classification_manager.py, coder_manager.py, askthebot_manager.py, asktheworld_manager.py, personality_manager.py)
   - services/ (slack_service.py, chatgpt_service.py, github_service.py)
2) The Slackbot uses a single classification GPT session. 
   If 'CODER', we do snippet code with coder_manager. 
   If 'ASKTHEBOT', we answer architecture Qs. 
   If 'ASKTHEWORLD', normal Q&A.
3) coder_manager.generate_snippet(...) => returns code string.
   coder_manager.create_snippet_callable(...) => returns a function or None.
...
(You can add more details as needed.)
        """
    }
}
