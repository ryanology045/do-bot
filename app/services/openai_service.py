# services/openai_service.py
"""
Service for interacting with OpenAI models (Chat Completions, rewrites, etc.).
Implements:
- A per-(model, instance_id) queue system for sequential requests (via process_request).
- A ChatGPTSessionManager for multi-turn conversations (via generate_response).
- A global BOT_ROLE and BOT_TEMPERATURE that can be dynamically updated from user text.
"""

import os
import openai
import re
from queue import Queue
from threading import Lock

openai.api_key = os.environ.get("OPENAI_API_KEY")

# We'll keep track of "available" model names that can be referenced
AVAILABLE_MODELS = set([
    "gpt-4o",
    "chatgpt-4o-latest",
    "gpt-4o-mini",
    "o1",
    "o1-mini",
    "o1-preview",
    "gpt-4o-realtime-preview",
    "gpt-4o-mini-realtime-preview",
    "gpt-4o-audio-preview",    
    
    "gpt-3.5-turbo",
    "gpt-3.5-turbo-16k",
    "gpt-4",
    "text-davinci-003",
])

# ---------------------------------------------------------------------
# BOT_ROLE and BOT_TEMPERATURE are global settings to guide the bot's behavior.
# BOT_ROLE is used as the system message; BOT_TEMPERATURE is passed to the API.
# ---------------------------------------------------------------------
BOT_ROLE = "You are Do Kwon, founder of Terraform Labs and the cryptocurrency Luna. Speak in the first person, reflecting on your motivations, decisions, and experiences. Acknowledge controversies and setbacks where relevant. Maintain a confident yet reflective tone. If you reference external data, clarify that you are interpreting it from your personal perspective."
BOT_TEMPERATURE = 0.6  # Default temperature

def set_role_and_temperature(role_text: str):
    """
    Parses 'role_text' for an optional temperature command and updates:
      - BOT_TEMPERATURE, if found
      - BOT_ROLE (the remainder of the text after removing temperature info)
    Examples of recognized patterns:
      "Set role to: You are an expert. temperature 1.0"
      "You are creative. temp=0.9"
      ...
    If no temperature is found, BOT_TEMPERATURE remains unchanged.
    """
    global BOT_ROLE, BOT_TEMPERATURE

    # Regex to capture temperature in forms like:
    # 'temp 0.9', 'temperature 1.2', 'temp=0.7', 'temperature=1.0'
    pattern = re.compile(r"(?i)\b(?:temp(?:erature)?\s*=?\s*)([0-9]*\.?[0-9]+)\b")

    match = pattern.search(role_text)
    if match:
        temp_str = match.group(1)
        try:
            parsed_temp = float(temp_str)
            # You can clamp or adjust if desired:
            if parsed_temp < 0.0:
                parsed_temp = 0.0
            elif parsed_temp > 2.0:
                parsed_temp = 2.0
            BOT_TEMPERATURE = parsed_temp
        except ValueError:
            # If parsing fails, do nothing special
            pass

        # Remove the temperature part from the role text
        role_text = pattern.sub("", role_text)

    BOT_ROLE = role_text.strip()


# Queues per (model, instance_id)
_instance_queues = {}
_queue_locks = Lock()

def _get_queue_key(model, instance_id):
    return f"{model}::{instance_id}"

def _get_queue(model, instance_id) -> Queue:
    """
    Get or create a queue for the (model, instance_id) pair.
    """
    with _queue_locks:
        key = _get_queue_key(model, instance_id)
        if key not in _instance_queues:
            _instance_queues[key] = Queue()
        return _instance_queues[key]

def _chat_completion_single(model, user_prompt):
    """
    Single-turn ChatCompletion, using BOT_ROLE as the system prompt and BOT_TEMPERATURE.
    """
    response = openai.ChatCompletion.create(
        model=model,
        messages=[
            {"role": "system", "content": f"{BOT_ROLE}\n(Temperature: {BOT_TEMPERATURE})"},
            {"role": "user", "content": user_prompt}
        ],
        temperature=BOT_TEMPERATURE
    )
    return response.choices[0].message["content"]

def process_request(model, instance_id, user_prompt):
    """
    Single-turn request: places the request in the queue for (model, instance_id),
    processes it sequentially, and returns the assistant reply.
    """
    if model not in AVAILABLE_MODELS:
        return f"Model '{model}' is not available. Please add it or choose another."

    q = _get_queue(model, instance_id)
    result_container = []

    def job():
        try:
            result = _chat_completion_single(model, user_prompt)
        except Exception as e:
            result_container.append(f"OpenAI API error: {str(e)}")
            return
        result_container.append(result)

    q.put(job)
    task = q.get()
    task()
    q.task_done()

    return result_container[0] if result_container else "No response."

def openai_rewrite(user_text):
    """
    Example function to rewrite user text using a default model (gpt-3.5-turbo).
    Returns rewritten text or an error message.
    """
    if "gpt-3.5-turbo" not in AVAILABLE_MODELS:
        return user_text  # fallback if that model isn't available
    try:
        response = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=[
                {
                    "role": "system",
                    "content": "Rewrite the user's request in a clearer, more concise way."
                },
                {"role": "user", "content": user_text}
            ]
        )
        return response.choices[0].message["content"]
    except Exception as e:
        return f"Rewrite error: {str(e)}"

# ---------------------------------------------------------------------
# Multi-turn conversation manager
# ---------------------------------------------------------------------
class ChatGPTSessionManager:
    """
    Manages conversation history per (model, instance_id) using the same
    queue-based approach for sequential ChatCompletion requests.
    """
    def __init__(self):
        # Key: (model, instance_id) -> list of {"role": "user"/"assistant"/"system", "content": str}
        self._conversations = {}

    def _init_conversation(self, model: str, instance_id: str):
        if (model, instance_id) not in self._conversations:
            self._conversations[(model, instance_id)] = []

    def add_user_message(self, model: str, instance_id: str, user_text: str):
        """
        Append user's message to the conversation history.
        """
        self._init_conversation(model, instance_id)
        self._conversations[(model, instance_id)].append({"role": "user", "content": user_text})

    def add_assistant_message(self, model: str, instance_id: str, assistant_text: str):
        """
        Append assistant's (OpenAI's) message to the conversation history.
        """
        self._init_conversation(model, instance_id)
        self._conversations[(model, instance_id)].append({"role": "assistant", "content": assistant_text})

    def get_conversation(self, model: str, instance_id: str):
        """
        Retrieve the entire conversation list for (model, instance_id).
        Returns an empty list if none exists.
        """
        return self._conversations.get((model, instance_id), [])

    def generate_response(self, model: str, instance_id: str, user_text: str) -> str:
        """
        Multi-turn approach: add user's message, call ChatCompletion with BOT_ROLE and BOT_TEMPERATURE,
        store the assistant reply, and return it. Uses the queue for concurrency control.
        """
        if model not in AVAILABLE_MODELS:
            return f"Model '{model}' is not available. Please add it or choose another."

        self._init_conversation(model, instance_id)
        self.add_user_message(model, instance_id, user_text)

        def worker():
            # Build full message list: system + prior conversation
            messages = [
                {
                    "role": "system",
                    "content": f"{BOT_ROLE}\n(Temperature: {BOT_TEMPERATURE})"
                }
            ] + self.get_conversation(model, instance_id)

            try:
                response = openai.ChatCompletion.create(
                    model=model,
                    messages=messages,
                    temperature=BOT_TEMPERATURE
                )
                reply = response.choices[0].message["content"]
                self.add_assistant_message(model, instance_id, reply)
                return reply
            except Exception as e:
                return f"OpenAI API error: {str(e)}"

        q = _get_queue(model, instance_id)
        result_holder = []

        def job():
            result_holder.append(worker())

        q.put(job)
        task = q.get()
        task()
        q.task_done()

        return result_holder[0]

# Single instance of ChatGPTSessionManager for the entire bot
_session_manager = ChatGPTSessionManager()

def generate_response(model: str, instance_id: str, user_text: str) -> str:
    """
    Public function to handle multi-turn conversation flows.
    This is what the gpt_interaction plugin would typically call.
    """
    return _session_manager.generate_response(model, instance_id, user_text)
