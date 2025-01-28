# services/openai_service.py
"""
Service for interacting with OpenAI models (Chat Completions, rewrites, etc.).
Implements:
- A per-(model, instance_id) queue system for sequential requests (via process_request).
- A ChatGPTSessionManager for multi-turn conversations (via generate_response).
- A global BOT_ROLE (system message) that can be set dynamically.
"""

import os
import openai
from queue import Queue
from threading import Lock

openai.api_key = os.environ.get("OPENAI_API_KEY")

# We'll keep track of "available" model names that can be referenced.
# You can set a default set here, and allow dynamic updates (e.g., via model_manager plugin).
AVAILABLE_MODELS = set([
    "gpt-3.5-turbo",
    "gpt-3.5-turbo-16k",
    "gpt-4",
    "text-davinci-003",
    # Add or remove as needed
])

# ---------------------------------------------------------------------
# NEW: A global "BOT_ROLE" for the system message. Can be updated by users at runtime.
# ---------------------------------------------------------------------
BOT_ROLE = "You are an impartial analyst with deep knowledge of Do Kwon, founder of Terraform Labs, and his cryptocurrency Luna. Provide concise, well-researched insights into his personality, leadership style, and public image, referencing known facts and events. Present the information objectively, acknowledging various viewpoints and controversies."

# Queues per (model, instance_id) for sequential requests
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
    Calls OpenAI ChatCompletion with a single-turn approach (no conversation history).
    Incorporates BOT_ROLE as the system message.
    """
    response = openai.ChatCompletion.create(
        model=model,
        messages=[
            {"role": "system", "content": BOT_ROLE},
            {"role": "user", "content": user_prompt}
        ],
        temperature=0.7
    )
    return response.choices[0].message["content"]

def process_request(model, instance_id, user_prompt):
    """
    For a single-turn request: puts the request in the queue for (model, instance_id),
    then processes it sequentially. Returns the assistant's reply.
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

    # Produce
    q.put(job)

    # Consume synchronously here (blocking).
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
        return user_text  # fallback if the model isn't available
    try:
        response = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": "Rewrite the user's request in a clearer, more concise way."},
                {"role": "user", "content": user_text}
            ]
        )
        return response.choices[0].message["content"]
    except Exception as e:
        return f"Rewrite error: {str(e)}"

# ---------------------------------------------------------------------
# Multi-turn conversation manager, with BOT_ROLE as a system message.
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
        key = (model, instance_id)
        if key not in self._conversations:
            self._conversations[key] = []

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
        Retrieve the entire conversation for (model, instance_id). Returns an empty list if none exists.
        """
        return self._conversations.get((model, instance_id), [])

    def generate_response(self, model: str, instance_id: str, user_text: str) -> str:
        """
        Multi-turn approach: add user's message, call ChatCompletion with BOT_ROLE as system,
        store assistant reply, and return it. Uses queue for concurrency control.
        """
        if model not in AVAILABLE_MODELS:
            return f"Model '{model}' is not available. Please add it or choose another."

        # Initialize conversation if needed
        self._init_conversation(model, instance_id)

        # Add the user's latest message
        self.add_user_message(model, instance_id, user_text)

        # Worker function that calls OpenAI API with system + conversation messages
        def worker():
            # Build messages: system role first, then conversation
            messages = [{"role": "system", "content": BOT_ROLE}]
            messages += self.get_conversation(model, instance_id)

            try:
                response = openai.ChatCompletion.create(
                    model=model,
                    messages=messages,
                    temperature=0.7
                )
                assistant_text = response.choices[0].message["content"]
                self.add_assistant_message(model, instance_id, assistant_text)
                return assistant_text
            except Exception as e:
                return f"OpenAI API error: {str(e)}"

        # Use the same queue approach
        q = _get_queue(model, instance_id)
        result_holder = []

        def job():
            result_holder.append(worker())

        q.put(job)
        task = q.get()
        task()
        q.task_done()

        return result_holder[0]

# A single instance of ChatGPTSessionManager for the entire bot
_session_manager = ChatGPTSessionManager()

def generate_response(model: str, instance_id: str, user_text: str) -> str:
    """
    Public function to handle multi-turn conversation flows. 
    This is used by the gpt_interaction plugin in the Slack event.
    """
    return _session_manager.generate_response(model, instance_id, user_text)
