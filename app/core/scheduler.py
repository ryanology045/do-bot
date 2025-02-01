# project_root/core/scheduler.py

import logging
from datetime import datetime, timedelta
import threading

logger = logging.getLogger(__name__)

class TaskScheduler:
    """
    The only non-event-driven code. Invokes a function of a given module
    at a specified time, with the specified args.
    """

    def __init__(self):
        self.scheduled_tasks = []

    def schedule(self, run_time, func, *args, **kwargs):
        logger.info("[SCHEDULER] Task scheduled at %s for %s(%s, %s)",
                    run_time, func.__name__, args, kwargs)
        self.scheduled_tasks.append((run_time, func, args, kwargs))
        t = threading.Thread(target=self._wait_and_run, args=(run_time, func, args, kwargs))
        t.daemon = True
        t.start()

    def _wait_and_run(self, run_time, func, args, kwargs):
        now = datetime.now()
        delta = (run_time - now).total_seconds()
        if delta > 0:
            logger.debug("[SCHEDULER] Waiting %s seconds before running %s", delta, func.__name__)
        else:
            logger.debug("[SCHEDULER] run_time is in the past for %s, running now.", func.__name__)
            delta = 0
        threading.Event().wait(delta)
        logger.info("[SCHEDULER] Running scheduled task: %s", func.__name__)
        func(*args, **kwargs)

    def schedule_in(self, seconds, func, *args, **kwargs):
        run_time = datetime.now() + timedelta(seconds=seconds)
        self.schedule(run_time, func, *args, **kwargs)
