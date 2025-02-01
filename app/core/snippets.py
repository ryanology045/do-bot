# project_root/core/snippets.py

import logging
from .scheduler import TaskScheduler

logger = logging.getLogger(__name__)

class SnippetsRunner:
    """
    Runs one-time GPT-generated snippets. May schedule them with TaskScheduler
    if they need delayed or repeated invocation. 
    """

    def __init__(self):
        self.scheduler = TaskScheduler()

    def run_snippet_now(self, snippet_callable, *args, **kwargs):
        """
        Immediately run the snippet (which might be a function or code object).
        For demonstration, snippet_callable is just a Python function reference.
        """
        logger.info("[SNIPPETS] Running snippet immediately: %s", snippet_callable.__name__)
        return snippet_callable(*args, **kwargs)

    def schedule_snippet(self, run_time, snippet_callable, *args, **kwargs):
        """
        Schedules the snippet to run at run_time.
        """
        logger.info("[SNIPPETS] Scheduling snippet %s at %s", snippet_callable.__name__, run_time)
        self.scheduler.schedule(run_time, snippet_callable, *args, **kwargs)

    def schedule_snippet_in(self, seconds, snippet_callable, *args, **kwargs):
        """
        Schedules the snippet to run in X seconds from now.
        """
        logger.info("[SNIPPETS] Scheduling snippet %s in %s seconds", snippet_callable.__name__, seconds)
        self.scheduler.schedule_in(seconds, snippet_callable, *args, **kwargs)
