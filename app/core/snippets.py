# project_root/core/snippets.py

import logging
from .scheduler import TaskScheduler

logger = logging.getLogger(__name__)

class SnippetsRunner:
    """
    Runs GPT-generated snippets. Possibly schedules them if needed.
    Rely on snippet code itself to check 'stop_snippet' if it has loops.
    """

    def __init__(self):
        self.scheduler = TaskScheduler()

    def run_snippet_now(self, snippet_callable, *args, **kwargs):
        logger.info("[SNIPPETS] Running snippet immediately: %s", snippet_callable.__name__)
        return snippet_callable(*args, **kwargs)

    def schedule_snippet(self, run_time, snippet_callable, *args, **kwargs):
        logger.info("[SNIPPETS] Scheduling snippet %s at %s", snippet_callable.__name__, run_time)
        self.scheduler.schedule(run_time, snippet_callable, *args, **kwargs)

    def schedule_snippet_in(self, seconds, snippet_callable, *args, **kwargs):
        logger.info("[SNIPPETS] Scheduling snippet %s in %s seconds", snippet_callable.__name__, seconds)
        self.scheduler.schedule_in(seconds, snippet_callable, *args, **kwargs)
