# plugins/rate_limiting.py
"""
Plugin enforcing basic user or global rate limits.
Default: 1 request/second, 50 requests/day per user.
Also allows commands to update the rate limits:
  - "set daily request limit 100"
  - "set per second limit 2"
"""

import re
import logging
from datetime import datetime
from collections import defaultdict
from slack_bolt import App

# The actual limits
REQUESTS_PER_SECOND = 1.0
REQUESTS_PER_DAY = 50

# usage data
user_usage = defaultdict(lambda: {
    'last_request_time': 0.0,
    'requests_today': 0,
    'day_start': datetime.utcnow().date()
})

def rate_limit_check(user_id: str) -> bool:
    """
    Returns True if user is under the limit, False if not.
    """
    # ... existing logic ...
    from datetime import datetime
    import time

    now = time.time()
    today = datetime.utcnow().date()
    usage = user_usage[user_id]

    # Reset daily count if new day
    if usage['day_start'] != today:
        usage['requests_today'] = 0
        usage['day_start'] = today

    # Check daily
    if usage['requests_today'] >= REQUESTS_PER_DAY:
        return False

    # Check per-second
    elapsed = now - usage['last_request_time']
    if elapsed < (1.0 / REQUESTS_PER_SECOND):
        return False

    # Update usage
    usage['last_request_time'] = now
    usage['requests_today'] += 1
    return True

# Regex for "set daily request limit <number>" or "set per second limit <number>"
DAILY_LIMIT_REGEX = re.compile(r"(?i)\bset\s+daily\s+request\s+limit\s+(?P<value>\d+)\b")
PER_SECOND_REGEX = re.compile(r"(?i)\bset\s+per\s+second\s+limit\s+(?P<value>\d+)\b")

def register(app: App):
    logger = logging.getLogger(__name__)
    logger.setLevel(logging.INFO)

    @app.event("app_mention")
    def handle_rate_limit_commands(event, say, logger):
        """
        Listens for commands that set daily/per-second rate limits:
         - "set daily request limit <num>"
         - "set per second limit <num>"
        If it doesn't match, we do nothing so other plugins can respond.
        """
        user_id = event.get("user")
        text = event.get("text", "")

        if not user_id or not text:
            logger.warning("rate_limiting: got app_mention with no user_id or text.")
            return

        # remove Slack mention tokens, e.g. <@U123ABC>
        import re
        mention_pattern = re.compile(r"<@[\w]+>")
        stripped_text = mention_pattern.sub("", text).strip()

        # if there's nothing left, do nothing
        if not stripped_text:
            return

        # Check for daily limit
        daily_match = DAILY_LIMIT_REGEX.search(stripped_text)
        if daily_match:
            value_str = daily_match.group("value")
            try:
                new_limit = int(value_str)
                if new_limit < 1:
                    say("Daily limit must be at least 1.")
                    return
                global REQUESTS_PER_DAY
                REQUESTS_PER_DAY = new_limit
                say(f"Daily request limit set to {REQUESTS_PER_DAY}.")
                logger.info(f"User {user_id} set daily request limit to {REQUESTS_PER_DAY}.")
            except ValueError:
                say("Invalid number for daily request limit.")
            return

        # Check for per-second limit
        persec_match = PER_SECOND_REGEX.search(stripped_text)
        if persec_match:
            value_str = persec_match.group("value")
            try:
                new_limit = float(value_str)
                if new_limit <= 0:
                    say("Per-second limit must be > 0.")
                    return
                global REQUESTS_PER_SECOND
                REQUESTS_PER_SECOND = new_limit
                say(f"Per-second limit set to {REQUESTS_PER_SECOND}.")
                logger.info(f"User {user_id} set per-second request limit to {REQUESTS_PER_SECOND}.")
            except ValueError:
                say("Invalid number for per second limit.")
            return

        # If we get here, user didn't match either pattern => do nothing
        # so no fallback error message
        return
