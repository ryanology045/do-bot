# project_root/core/configs.py

bot_config = {
    "default_qna_model": "gpt-3.5-turbo",
    "rate_limit_per_second": 1,
    "daily_limit_per_user": 50,

    "roles_definitions": {
        "default": {
            "system_prompt": "You are a helpful assistant. Respond succinctly.",
            "temperature": 0.7,
            "description": "Default fallback role."
        },
        "friendly": {
            "system_prompt": "You are a friendly assistant. Respond with warmth and positivity.",
            "temperature": 0.9,
            "description": "Cheery persona."
        },
        "professional": {
            "system_prompt": "You are a professional assistant. Provide concise, formal responses.",
            "temperature": 0.4,
            "description": "Businesslike tone."
        },
        "tech_expert": {
            "system_prompt": "You are a highly technical expert. Provide in-depth, technical detail.",
            "temperature": 0.6,
            "description": "Deeper domain knowledge persona."
        }
    }
}
