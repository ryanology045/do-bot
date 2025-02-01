# project_root/core/configs.py

bot_config = {
    # The default model for normal Q&A
    "default_qna_model": "gpt-3.5-turbo",

    # Role definitions: you can expand more roles as needed
    "roles_definitions": {
        "default": {
            "system_prompt": "You are Do Kwon, founder of Terraform Labs and the cryptocurrency Luna. Always speak casually, using crypto slang (gm, wagmi, LFG, etc.) and a direct, confident tone—even for questions not related to Terra, Luna, or crypto. Acknowledge any controversies if relevant, but do not block or refuse typical chatbot functions. Keep responses short and stay in-character as Do Kwon at all times.",
            "temperature": 0.6,
            "description": "Do Kwon."
        },
        "friendly": {
            "system_prompt": "You are a friendly, upbeat assistant who greets warmly.",
            "temperature": 0.9,
            "description": "Cheerful, positive role."
        },
        "tech_expert": {
            "system_prompt": "You are a highly technical expert. Provide in-depth details.",
            "temperature": 0.6,
            "description": "Deeper domain knowledge persona."
        }
        # ... add more roles here if needed
    },

    # Additional prompts or large text for the classifier or coder usage
    "initial_prompts": {
        # The "bot_context" can be an ultra-expanded text that the classification manager
        # uses once at initialization (for the single global GPT session).
        "bot_context": """
FULL BOT CONTEXT (Example):
1) File/Module Overview:
   - core/main.py: Entrypoint with Flask & Slack routes.
   - core/bot_engine.py: Orchestrates classification & advanced flows.
   - core/configs.py: This file. Holds bot_config with roles_definitions and initial_prompts.
   - core/module_manager.py: Dynamically loads modules from 'modules/' folder.
   - core/scheduler.py: Schedules code snippet tasks. (not focusing on it now)
   - core/snippets.py: Runs GPT-generated code snippets immediately or at scheduled times.

2) Modules:
   - modules/classification_manager.py: Single global GPT session for classification. 
     returns JSON => {request_type, role_info, extra_data}.
   - modules/coder_manager.py: For code snippet tasks or advanced config modifications.
   - modules/askthebot_manager.py: Handles user questions about this bot's architecture/design.
   - modules/asktheworld_manager.py: Normal Q&A conversation flow.
   - modules/personality_manager.py: Stores role-based system prompts.

3) Services:
   - services/slack_service.py: Slack inbound/outbound logic.
   - services/chatgpt_service.py: GPT API calls.
   - services/github_service.py: (Optional) read/write code from GitHub.

4) If user wants code/config changes => request_type=CODER
   If user is asking about the bot => request_type=ASKTHEBOT
   Otherwise => request_type=ASKTHEWORLD

5) Coder GPT usage:
   - classification_manager calls handle_classification().
   - If result is { request_type=CODER, ... }, the bot engine calls coder_manager to produce a snippet. 
   - The snippet may be executed to modify roles, config, or code. 
   - This can be risky in production (must sandbox or do PR merges).

6) Additional Info:
   - bot_config['default_qna_model'] = "gpt-3.5-turbo" by default.
   - We unify all advanced logic under "CODER" with forced extra_data['bot_knowledge'] = the big context.
   - One single classification conversation across the entire Slack workspace for simplicity, but it can lead to cross-thread influences.
"""
    }
}
