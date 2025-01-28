# plugins/rollback.py
"""
Plugin for rolling back the bot to a previous deployment using GitHub tags.
We keep the rollback_to_tag logic (and any supportive code).
We remove the mention-based Slack code, since universal_app_mention.py handles that.
"""

import logging
import os
from services.github_service import rollback_to_tag

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

def register(app):
    """
    No mention-based code here. If universal_app_mention triggers rollback, 
    it calls rollback_to_tag or other logic directly.
    """
    pass

# If you want any helper functions for direct usage:
def do_rollback_last():
    """
    Example helper if you want to call 'rollback last' from somewhere else.
    Could fetch last tag, then call rollback_to_tag.
    """
    # Up to you if you want to keep something like this
    pass
