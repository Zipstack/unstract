"""Gevent initialization module - MUST be imported first in Celery workers
This module handles gevent monkey patching before any other imports occur.
"""

import os
import sys


def apply_gevent_patches():
    """Apply gevent monkey patches if running in gevent mode."""
    # Only patch if CELERY_POOL=gevent is set
    if os.environ.get("CELERY_POOL") != "gevent":
        return False

    # Check if we're running as a Celery worker
    argv_str = " ".join(sys.argv)
    is_celery_worker = "celery" in sys.argv[0] and "worker" in argv_str

    # Don't patch Django processes
    is_django_process = any(
        cmd in argv_str for cmd in ["runserver", "gunicorn", "manage.py"]
    )

    if is_celery_worker and not is_django_process:
        # Apply gevent patches before any other imports
        from gevent import monkey

        monkey.patch_all(
            socket=True,
            dns=True,
            time=True,
            select=True,
            thread=True,
            os=True,
            ssl=True,
            subprocess=True,
            sys=True,
            aggressive=True,
            Event=True,
            builtins=True,
            signal=True,
        )

        import logging

        logger = logging.getLogger(__name__)
        logger.info("GEVENT PATCHES APPLIED EARLY - Before SSL/threading imports")
        return True

    return False


# Apply patches immediately when this module is imported
_GEVENT_APPLIED = apply_gevent_patches()
