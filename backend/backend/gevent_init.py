"""Gevent initialization module - DISABLED due to threading conflicts
Using Celery's built-in gevent pool instead of manual monkey patching.
"""

import logging
import os

logger = logging.getLogger(__name__)


def apply_gevent_patches():
    """Placeholder function - gevent patching disabled to avoid threading conflicts.

    Celery handles gevent integration natively when using --pool=gevent.
    Our pure boto3 implementation provides the same benefits without monkey patching.
    """
    if os.environ.get("CELERY_POOL") == "gevent":
        logger.info("Using Celery's native gevent pool - no manual patching needed")
    return False


# No patches applied - relying on Celery's native gevent support
_GEVENT_APPLIED = False
