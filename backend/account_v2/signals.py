from typing import Any

from django.contrib.auth.signals import user_logged_in, user_logged_out
from django.dispatch import receiver
from django.http import HttpRequest

from account_v2.session_tracking import SessionTracker


@receiver(user_logged_in)
def record_session_on_sign_in(
    sender: Any, request: HttpRequest | None, user: Any, **kwargs: Any
) -> None:
    # `login()` can be called without a request outside the HTTP flow.
    if request is not None and hasattr(request, "session"):
        SessionTracker.record_sign_in(request, user)


@receiver(user_logged_out)
def forget_session_on_sign_out(
    sender: Any, request: HttpRequest | None, user: Any, **kwargs: Any
) -> None:
    if request is not None and hasattr(request, "session"):
        SessionTracker.forget(request.session.session_key)
