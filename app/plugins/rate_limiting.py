# plugins/rate_limiting.py
"""
Plugin that enforces basic user or global rate limits.
Default: 1 request/second, 50 requests/day per user.
Includes Slack commands to override:
    - "@BotName set daily request limit 100"
    - "@BotName set per second limit 2"
"""

import time
from datetime import datetime, timedelta
from collections import defaultdict
import logging
import os

from slack_bolt import App

# Configure logger for the Rate Limiting plugin
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# Create a console handler with a higher log level
console_handler = logging.StreamHandler()
console_handler.setLevel(logging.INFO)

# Create a formatter and set it for the handler
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
console_handler.setFormatter(formatter)

# Add the handler to the logger if it doesn't already have handlers
if not logger.hasHandlers():
    logger.addHandler(console_handler)

# Default rate limits
DEFAULT_REQUESTS_PER_SECOND = 1.0
DEFAULT_REQUESTS_PER_DAY = 50

# Initialize rate limit variables
REQUESTS_PER_SECOND = DEFAULT_REQUESTS_PER_SECOND
REQUESTS_PER_DAY = DEFAULT_REQUESTS_PER_DAY

# Track usage data: 
# user_usage[user_id] = {
#    'last_request_time': float (timestamp),
#    'requests_today': int,
#    'day_start': date
# }
user_usage = defaultdict(lambda: {
    'last_request_time': 0.0,
    'requests_today': 0,
    'day_start': datetime.utcnow().date()
})

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
        logger.info(f"User {user_id} exceeded daily limit: {usage['requests_today']}/{REQUESTS_PER_DAY}")
        return False
    
    # Check per-second limit
    elapsed = now - usage['last_request_time']
    if elapsed < (1.0 / REQUESTS_PER_SECOND):
        logger.info(f"User {user_id} exceeded per-second limit: {elapsed:.2f}s since last request")
        return False
    
    # If we pass checks, update usage
    usage['last_request_time'] = now
    usage['requests_today'] += 1
    logger.debug(f"User {user_id} request allowed: {usage['requests_today']}/{REQUESTS_PER_DAY} today")
    return True

def register(app: App):
    """
    Register rate limiting event listeners and commands with the given Slack Bolt app.
    
    Args:
        app (App): The Slack Bolt App instance to register event listeners with.
    """
    logger.info("Registering Rate Limiting plugin...")
    
    # Retrieve admin user IDs from environment variable (comma-separated)
    ADMIN_USER_IDS = os.environ.get("ADMIN_USER_IDS", "")
    ADMIN_USER_IDS = set(uid.strip() for uid in ADMIN_USER_IDS.split(",") if uid.strip())
    
    if not ADMIN_USER_IDS:
        logger.warning("No ADMIN_USER_IDS defined. Only the bot itself can perform admin actions.")
    
    # Regex to parse commands: "set daily request limit <number>" or "set per second limit <number>"
    SET_DAILY_REGEX = re.compile(r"^set\s+daily\s+request\s+limit\s+(?P<limit>\d+)$", re.IGNORECASE)
    SET_PER_SECOND_REGEX = re.compile(r"^set\s+per\s+second\s+limit\s+(?P<limit>\d+(\.\d+)?)$", re.IGNORECASE)
    
    @app.event("app_mention")
    def handle_app_mention_events(event, say, logger):
        """
        Handle 'app_mention' events to process rate limiting commands.
        
        Expected command formats:
            - "@BotName set daily request limit 100"
            - "@BotName set per second limit 2"
        """
        user_id = event.get("user")
        text = event.get("text", "")
        
        if not user_id or not text:
            logger.warning("Received app_mention event without user ID or text.")
            return
        
        # Remove all bot mentions from the text
        # Slack mentions are in the format <@U12345678>
        mention_pattern = re.compile(r"<@[\w]+>")
        stripped_text = mention_pattern.sub("", text).strip()
        
        if not stripped_text:
            say(f"<@{user_id}>, please provide a command after mentioning me.")
            return
        
        # Check if the user is an admin
        is_admin = user_id in ADMIN_USER_IDS
        if not is_admin:
            say(f"<@{user_id}>, you do not have permission to perform this action.")
            logger.info(f"Unauthorized user {user_id} attempted to modify rate limits.")
            return
        
        # Attempt to match 'set daily request limit' command
        daily_match = SET_DAILY_REGEX.match(stripped_text)
        if daily_match:
            new_limit = int(daily_match.group("limit"))
            set_daily_limit(new_limit, say)
            return
        
        # Attempt to match 'set per second limit' command
        per_second_match = SET_PER_SECOND_REGEX.match(stripped_text)
        if per_second_match:
            new_limit = float(per_second_match.group("limit"))
            set_per_second_limit(new_limit, say)
            return
        
        # If command not recognized
        say("Could not parse rate limit command. Use `set daily request limit <number>` or `set per second limit <number>`.")
        logger.info(f"User {user_id} sent unrecognized rate limit command: '{stripped_text}'")
    
    def set_daily_limit(new_limit: int, say):
        """
        Sets the daily request limit.
        
        Args:
            new_limit (int): The new daily request limit to set.
            say (function): Function to send messages back to Slack.
        """
        global REQUESTS_PER_DAY
        old_limit = REQUESTS_PER_DAY
        REQUESTS_PER_DAY = new_limit
        say(f"Daily request limit has been updated from {old_limit} to {REQUESTS_PER_DAY}.")
        logger.info(f"Daily request limit updated to {REQUESTS_PER_DAY}")
    
    def set_per_second_limit(new_limit: float, say):
        """
        Sets the per-second request limit.
        
        Args:
            new_limit (float): The new per-second request limit to set.
            say (function): Function to send messages back to Slack.
        """
        global REQUESTS_PER_SECOND
        old_limit = REQUESTS_PER_SECOND
        REQUESTS_PER_SECOND = new_limit
        say(f"Per-second request limit has been updated from {old_limit} to {REQUESTS_PER_SECOND}.")
        logger.info(f"Per-second request limit updated to {REQUESTS_PER_SECOND}")
    
    logger.info("Rate Limiting plugin registered successfully.")
