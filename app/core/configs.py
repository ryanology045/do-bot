# project_root/core/configs.py

bot_config = {
    "default_qna_model": "gpt-3.5-turbo",

    "roles_definitions": {
        "default": {
            "system_prompt": "You are a helpful assistant. Respond succinctly.",
            "temperature": 0.7,
            "description": "Default fallback role."
        },
        "friendly": {
            "system_prompt": "You are a friendly, upbeat assistant.",
            "temperature": 0.9,
            "description": "Cheerful persona."
        },
        "tech_expert": {
            "system_prompt": "You are a highly technical expert.",
            "temperature": 0.6,
            "description": "Deep knowledge persona."
        }
    },

    "initial_prompts": {

        "classification_system_prompt": """
You are the classification system with memory of prior messages.
Decide among:
 - ASKTHEWORLD => normal Q&A
 - ASKTHEBOT => user wants architecture details
 - CODER => user wants code or config modifications
Output strictly valid JSON => {"request_type":"...", "role_info":"...", "extra_data":{}}.
        """,

        # The thorough coder context with strict rules
        "coder_system_prompt": """
You are a Python code generator.

1) Always produce exactly one function named `generated_snippet(channel, thread_ts)`.
2) No triple backticks, docstrings, disclaimers, or extra lines. Must compile under Python 3.10.
3) If referencing Slack:
    from services.slack_service import SlackService
    SlackService().post_message(channel=channel, text="...", thread_ts=thread_ts)
4) If referencing config:
    from core.configs import bot_config
5) Use 'post_message', not 'send_message'.
6) Always indent everything under the function by exactly 4 spaces.

Example:

def generated_snippet(channel, thread_ts):
    from core.configs import bot_config
    from services.slack_service import SlackService
    SlackService().post_message(channel=channel, text=str(bot_config), thread_ts=thread_ts)

7) If you have no real logic, produce a minimal stub:

def generated_snippet(channel, thread_ts):
    pass

No code outside that function.
        """,

        "bot_context": """
FULL BOT CONTEXT (Ultra-Expanded):
1) File Structure:
   - core/ (main.py, bot_engine.py, configs.py, module_manager.py, scheduler.py, snippets.py)
   - modules/ (classification_manager.py, coder_manager.py, askthebot_manager.py, asktheworld_manager.py, personality_manager.py)
   - services/ (slack_service.py, chatgpt_service.py, github_service.py)

2) If request_type=CODER, coder_manager generates code with a single 'generated_snippet()' function. 
   If request_type=ASKTHEBOT, we answer internal architecture Qs. 
   If request_type=ASKTHEWORLD, normal Q&A.

3) coder_manager.generate_snippet(...) => code string
   coder_manager.create_snippet_callable(code_str) => a function or None
        """
    }
}
