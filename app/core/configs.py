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
Return ONLY a single function named 'generated_snippet()' with correct indentation.
No triple backticks, no docstrings, no disclaimers. Must compile under Python 3.10.

If referencing Slack:
  from services.slack_service import SlackService
  SlackService().post_message(channel="C12345", text="some text")

If referencing config:
  from core.configs import bot_config

Use 'post_message', not 'send_message'. 
Use standard indentation after 'def generated_snippet():'.
No code outside that function. No additional commentary or disclaimers.
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
