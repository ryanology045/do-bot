# services/openai_service.py
#"""
#Service for interacting with OpenAI models (Chat Completions, rewrites, etc.).
#Implements a per-instance queue system for sequential requests.
#"""

import os
import openai
from queue import Queue
from threading import Lock

openai.api_key = os.environ.get("OPENAI_API_KEY")

# We'll keep track of "available" model names that can be referenced
# You can set a default set here, and allow dynamic updates from model_manager plugin
AVAILABLE_MODELS = set([
    "gpt-3.5-turbo",
    "gpt-3.5-turbo-16k",
    "gpt-4",
    "text-davinci-003",
    # Add or remove as needed
])

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

def _chat_completion(model, user_prompt):
    """
    Calls OpenAI ChatCompletion create endpoint with the user prompt.
    """
    # Simple example, you can pass system or context messages as well
    response = openai.ChatCompletion.create(
        model=model,
        messages=[
            {"role": "user", "content": user_prompt}
        ],
        temperature=0.7
    )
    return response.choices[0].message["content"]

def process_request(model, instance_id, user_prompt):
    """
    Puts the request in the queue for the given (model, instance_id) and processes sequentially.
    """
    if model not in AVAILABLE_MODELS:
        return f"Model '{model}' is not available. Please add it or choose another."

    q = _get_queue(model, instance_id)
    
    # We'll define a small wrapper to run synchronously
    def worker():
        return _chat_completion(model, user_prompt)

    # Put the worker in the queue and wait for result
    result_container = []
    
    def job():
        result_container.append(worker())

    # Produce
    q.put(job)
    
    # Consume (synchronously for demonstration; in production you might run a separate thread)
    job_to_run = q.get()
    job_to_run()
    q.task_done()

    return result_container[0]

def openai_rewrite(user_text):
    """
    Example function to rewrite user text using openai.
    """
    if "gpt-3.5-turbo" not in AVAILABLE_MODELS:
        return user_text  # fallback if model not available
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

# services/openai_service.py

# [All your existing imports and code above remain unchanged]
# ...
# existing code: AVAILABLE_MODELS, _instance_queues, _queue_locks, etc.

class ChatGPTSessionManager:
    """
    A session manager that keeps track of conversations per (model, instance_id) and
    uses the existing queue-based approach for sequential ChatCompletion requests.
    """
    def __init__(self):
        """
        Initialize the ChatGPTSessionManager with an internal dictionary to store
        conversation history per (model, instance_id).
        """
        # Key: (model, instance_id), Value: list of chat messages (dicts with 'role', 'content')
        self._conversations = {}

    def _init_conversation(self, model: str, instance_id: str):
        """
        Create a new conversation list for (model, instance_id) if it doesn't exist yet.
        """
        key = (model, instance_id)
        if key not in self._conversations:
            self._conversations[key] = []

    def add_user_message(self, model: str, instance_id: str, user_text: str):
        """
        Add the user's message to the conversation history.
        """
        self._init_conversation(model, instance_id)
        self._conversations[(model, instance_id)].append({"role": "user", "content": user_text})

    def add_assistant_message(self, model: str, instance_id: str, assistant_text: str):
        """
        Add the assistant's (OpenAI's) message to the conversation history.
        """
        self._init_conversation(model, instance_id)
        self._conversations[(model, instance_id)].append({"role": "assistant", "content": assistant_text})

    def get_conversation(self, model: str, instance_id: str):
        """
        Retrieve the entire conversation list for (model, instance_id).
        Returns an empty list if none exists yet.
        """
        return self._conversations.get((model, instance_id), [])

    def generate_response(self, model: str, instance_id: str, user_text: str) -> str:
        """
        Adds the user's message to the conversation, then calls OpenAI's ChatCompletion,
        updates the conversation with the assistant reply, and returns the assistant's response.
        Uses the same queue-based approach as process_request for concurrency.
        """
        # 1. Check if model is available
        if model not in AVAILABLE_MODELS:
            return f"Model '{model}' is not available. Please add it or choose another."

        # 2. Initialize or retrieve the conversation
        self._init_conversation(model, instance_id)

        # 3. Add the user message to conversation
        self.add_user_message(model, instance_id, user_text)

        # 4. We'll define a small worker that calls the existing `_chat_completion`,
        #    but we pass in the entire conversation as the "messages" parameter.
        def worker():
            conversation_messages = self.get_conversation(model, instance_id)
            # Example usage with the existing openai.ChatCompletion:
            response = openai.ChatCompletion.create(
                model=model,
                messages=conversation_messages,
                temperature=0.7
            )
            reply = response.choices[0].message["content"]
            # Add the assistant's reply to the conversation
            self.add_assistant_message(model, instance_id, reply)
            return reply

        # 5. Use the same queue logic as process_request
        q = _get_queue(model, instance_id)
        result_container = []

        def job():
            result_container.append(worker())

        q.put(job)
        job_to_run = q.get()
        job_to_run()
        q.task_done()

        # 6. Return the assistant's generated reply
        return result_container[0]

# ---------------------------------------------------------------------
# Provide a single session_manager instance + a helper function
# ---------------------------------------------------------------------
_session_manager = ChatGPTSessionManager()

def generate_response(model: str, instance_id: str, user_text: str) -> str:
    """
    Wraps the ChatGPTSessionManager instance method.
    This is the function you can import and call directly.
    """
    return _session_manager.generate_response(model, instance_id, user_text)
