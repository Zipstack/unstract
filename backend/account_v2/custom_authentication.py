from typing import Any

from django.http import HttpRequest
from rest_framework.exceptions import AuthenticationFailed


def api_login_required(view_func: Any) -> Any:
    def wrapper(request: HttpRequest, *args: Any, **kwargs: Any) -> Any:
        if request.user and request.session and "user" in request.session:
            return view_func(request, *args, **kwargs)
        raise AuthenticationFailed("Unauthorized")

    return wrapper
