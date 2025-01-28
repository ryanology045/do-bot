# plugins/rate_limiting.py
"""
Plugin enforcing basic user/global rate limits (1 r/s, 50 r/day by default).
We keep only the rate_limit_check logic, no mention-based Slack code.
"""

import time
import logging
from datetime import datetime
from collections import defaultdict

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

REQUESTS_PER_SECOND = 1.0
REQUESTS_PER_DAY = 50

user_usage = defaultdict(lambda: {
    'last_request_time': 0.0,
    'requests_today': 0,
    'day_start': datetime.utcnow().date()
})

def rate_limit_check(user_id: str) -> bool:
    """
    Returns True if user is under the limit, False if not.
    - 1 request/second
    - 50 requests/day by default
    """
    now = time.time()
    today = datetime.utcnow().date()
    usage = user_usage[user_id]

    # Reset daily if new day
    if usage['day_start'] != today:
        usage['requests_today'] = 0
        usage['day_start'] = today

    # Daily limit
    if usage['requests_today'] >= REQUESTS_PER_DAY:
        return False

    # Per-second limit
    elapsed = now - usage['last_request_time']
    if elapsed < (1.0 / REQUESTS_PER_SECOND):
        return False

    # Update usage
    usage['last_request_time'] = now
    usage['requests_today'] += 1
    return True

def register(app):
    """
    No mention-based handlers here. We do nothing in register, 
    but keep it for compatibility with the plugin_manager if needed.
    """
    pass
