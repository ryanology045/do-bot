# services/openai_service.py
"""
Service for interacting with OpenAI models (Chat Completions, rewrites, etc.).
Implements a per-instance queue system for sequential requests.
"""

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
