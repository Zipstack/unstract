import logging
from typing import Any

from django.contrib.auth.signals import user_logged_in, user_logged_out
from django.db import transaction
from django.dispatch import receiver
from django.http import HttpRequest

from account_v2.session_tracking import SessionTracker

logger = logging.getLogger(__name__)


# Both receivers run inside sign-in and sign-out. Recording where a user is signed
# in must never be the reason either fails, so errors are logged and swallowed.


@receiver(user_logged_in)
def record_session_on_sign_in(
    sender: Any, request: HttpRequest | None, user: Any, **kwargs: Any
) -> None:
    if request is None or not hasattr(request, "session"):
        return
    try:
        SessionTracker.record_sign_in(request, user)
    except Exception:
        logger.warning(
            "Failed to record signed-in session of user %s", user.pk, exc_info=True
        )


@receiver(user_logged_out)
def forget_session_on_sign_out(
    sender: Any, request: HttpRequest | None, user: Any, **kwargs: Any
) -> None:
    if request is None or not hasattr(request, "session"):
        return
    try:
        with transaction.atomic():
            SessionTracker.forget(request.session.session_key)
    except Exception:
        logger.warning(
            "Failed to forget signed-out session of user %s",
            getattr(user, "pk", None),
            exc_info=True,
        )
