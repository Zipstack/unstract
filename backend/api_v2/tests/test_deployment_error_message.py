"""Every error the public deployment endpoint returns also carries
`message.error`, and the keys clients already parse are left untouched.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest
from middleware.exception import drf_logging_exc_handler
from rest_framework.exceptions import ValidationError
from rest_framework.test import APIRequestFactory

from api_v2.api_deployment_views import DeploymentExecution
from api_v2.error_message import add_error_message, flatten_error
from api_v2.exceptions import (
    APINotFound,
    InvalidAPIRequest,
    RateLimitExceeded,
    UnauthorizedKey,
)

URL = "/deployment/api/org/api/"
AUTH = {"HTTP_AUTHORIZATION": "Bearer 00000000-0000-0000-0000-000000000000"}


def _call(method: str, **headers):
    request = getattr(APIRequestFactory(), method)(URL, **headers)
    return DeploymentExecution.as_view()(request, org_name="org", api_name="api")


def _handler_body(exc: Exception, method: str = "post") -> dict:
    """What the project-wide handler sends for `exc` on its own, i.e. the body
    clients parsed before `message` was added.
    """
    request = getattr(APIRequestFactory(), method)(URL)
    return dict(drf_logging_exc_handler(exc=exc, context={"request": request}).data)


@pytest.mark.parametrize("method", ["post", "get"])
def test_missing_key_keeps_its_body_and_gains_message(method) -> None:
    response = _call(method)

    assert response.status_code == 403
    legacy = {k: v for k, v in response.data.items() if k != "message"}
    assert legacy == {
        "type": "client_error",
        "errors": [{"code": "error", "detail": "Missing api key", "attr": None}],
    }
    assert response.data["message"] == {
        "execution_status": "ERROR",
        "error": "Missing api key",
    }


@pytest.mark.parametrize("method", ["post", "get"])
@pytest.mark.parametrize(
    ("exc", "status", "error"),
    [
        (UnauthorizedKey(), 401, "Unauthorized"),
        (APINotFound(), 404, "API not found"),
        (InvalidAPIRequest("Missing params api_name"), 400, "Missing params api_name"),
        (RateLimitExceeded(detail="Too many"), 429, "Too many"),
        (
            ValidationError({"timeout": ["Ensure this value is less than 300."]}),
            400,
            "timeout: Ensure this value is less than 300.",
        ),
    ],
)
def test_raised_errors_keep_the_handler_body_and_gain_message(
    method, exc, status, error
) -> None:
    with patch(
        "api_v2.api_deployment_views.DeploymentHelper.validate_parameters",
        side_effect=exc,
    ):
        response = _call(method, **AUTH)

    assert response.status_code == status
    legacy = {k: v for k, v in response.data.items() if k != "message"}
    assert legacy == _handler_body(exc, method)
    assert response.data["message"] == {"execution_status": "ERROR", "error": error}


def test_validation_errors_flatten_in_order_with_field_prefix() -> None:
    data = {
        "type": "validation_error",
        "errors": [
            {"code": "invalid", "detail": "Not a valid URL.", "attr": "presigned_urls.0"},
            {"code": "invalid", "detail": "At least one file.", "attr": None},
        ],
    }

    assert flatten_error(data) == (
        "presigned_urls.0: Not a valid URL.; At least one file."
    )


@pytest.mark.parametrize(
    ("data", "error"),
    [
        # The cloud subscription middleware sends `errors` as a plain string.
        ({"type": "subscription_error", "errors": "Trial expired"}, "Trial expired"),
        ({"type": "sdk_error", "error": "Adapter failed"}, "Adapter failed"),
    ],
)
def test_non_list_error_bodies_are_flattened(data, error) -> None:
    assert flatten_error(data) == error


def test_an_existing_message_is_never_overwritten() -> None:
    data = {"message": {"execution_status": "ERROR", "error": "boom"}}

    assert add_error_message(data) == {
        "message": {"execution_status": "ERROR", "error": "boom"}
    }
