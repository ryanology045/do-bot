# project_root/core/snippets.py

import logging
from .scheduler import TaskScheduler

logger = logging.getLogger(__name__)

class SnippetsRunner:
    """
    Runs GPT-generated snippets. Possibly schedules them if needed. 
    The snippet code must be cooperative about 'stop_snippet' if loops.
    """

    def __init__(self):
        self.scheduler = TaskScheduler()

    def run_snippet_now(self, snippet_callable, channel, thread_ts):
        """
        Immediately run the snippet (a Python function).
        Capture stdout so we can post any `print` output to Slack.
        If snippet throws an exception, we also post an error message to Slack.
        """
        import sys, io
        logger.info("[SNIPPETS] Running snippet immediately: %s", snippet_callable.__name__)

        old_stdout = sys.stdout
        captured_out = io.StringIO()
        sys.stdout = captured_out

        try:
            # Execute the snippet function
            snippet_callable(channel, thread_ts)
        except Exception as e:
            # If snippet crashed, log the error, post partial output + error message to Slack
            logger.error("[SNIPPETS] Snippet threw exception: %s", e, exc_info=True)

            snippet_output = captured_out.getvalue().strip()
            if snippet_output:
                SlackService().post_message(
                    channel=channel,
                    text=f"**Snippet partial output before crash**:\n```\n{snippet_output}\n```",
                    thread_ts=thread_ts
                )

            SlackService().post_message(
                channel=channel,
                text=f":x: The snippet crashed with an exception:\n```\n{e}\n```",
                thread_ts=thread_ts
            )
        else:
            # If snippet succeeded, post any captured print output plus success message
            snippet_output = captured_out.getvalue().strip()
            if snippet_output:
                SlackService().post_message(
                    channel=channel,
                    text=f"**Snippet output**:\n```\n{snippet_output}\n```",
                    thread_ts=thread_ts
                )

            SlackService().post_message(
                channel=channel, 
                text="Snippet executed successfully!",
                thread_ts=thread_ts
            )
        finally:
            # Restore stdout no matter what
            sys.stdout = old_stdout

    def schedule_snippet(self, run_time, snippet_callable, *args, **kwargs):
        logger.info("[SNIPPETS] Scheduling snippet %s at %s", snippet_callable.__name__, run_time)
        self.scheduler.schedule(run_time, snippet_callable, *args, **kwargs)

    def schedule_snippet_in(self, seconds, snippet_callable, *args, **kwargs):
        logger.info("[SNIPPETS] Scheduling snippet %s in %s seconds", snippet_callable.__name__, seconds)
        self.scheduler.schedule_in(seconds, snippet_callable, *args, **kwargs)
