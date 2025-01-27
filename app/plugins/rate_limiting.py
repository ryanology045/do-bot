# plugins/rate_limiting.py
#"""
#Plugin that enforces basic user or global rate limits.
#Default: 1 request/second, 50 requests/day per user. 
#Includes Slack commands to override: "@BotName set daily request limit 100" etc.
#"""

import time
from datetime import datetime, timedelta
from collections import defaultdict

# Track usage data: 
# user_usage[user_id] = {
#    'last_request_time': float (timestamp),
#    'requests_today': int,
#    'day_start': date
# }
user_usage = defaultdict(lambda: {'last_request_time': 0.0, 'requests_today': 0, 'day_start': datetime.utcnow().date()})

# Default limits
REQUESTS_PER_SECOND = 1.0
REQUESTS_PER_DAY = 50

def rate_limit_check(user_id: str) -> bool:
    """
    Returns True if the user is within the rate limit.
    Otherwise returns False.
    """
    now = time.time()
    today = datetime.utcnow().date()
    
    usage = user_usage[user_id]
    
    # Check if new day -> reset daily count
    if usage['day_start'] != today:
        usage['requests_today'] = 0
        usage['day_start'] = today
    
    # Check daily limit
    if usage['requests_today'] >= REQUESTS_PER_DAY:
        return False
    
    # Check per-second limit
    elapsed = now - usage['last_request_time']
    if elapsed < (1.0 / REQUESTS_PER_SECOND):
        return False
    
    # If we pass checks, update usage
    usage['last_request_time'] = now
    usage['requests_today'] += 1
    return True

from slack_bolt import App
from core.slack_app import app

@app.message("set daily request limit")
def set_daily_limit(message, say):
    """
    Admin command example: "@BotName set daily request limit 100"
    """
    text = message.get('text', '')
    # naive parse:
    parts = text.split()
    # We expect something like ["<@BotID>", "set", "daily", "request", "limit", "100"]
    if len(parts) < 6:
        return
    try:
        new_limit = int(parts[-1])
    except ValueError:
        say("Invalid limit.")
        return
    
    # In real usage, check if user is admin:
    # ...
    
    global REQUESTS_PER_DAY
    REQUESTS_PER_DAY = new_limit
    say(f"Daily request limit set to {REQUESTS_PER_DAY}")
