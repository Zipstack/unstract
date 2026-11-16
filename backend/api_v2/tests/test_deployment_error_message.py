"""Every error the execute endpoint returns also carries `message.error`, and
the keys clients already parse are left untouched on both endpoints.
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
from api_v2.tests.test_docstudio_spec import _schema

URL = "/deployment/api/org/api/"
AUTH = {"HTTP_AUTHORIZATION": "Bearer 00000000-0000-0000-0000-000000000000"}

RAISED = [
    (UnauthorizedKey(), 401, "Unauthorized"),
    (APINotFound(), 404, "API not found"),
    (InvalidAPIRequest("Missing params api_name"), 400, "Missing params api_name"),
    (RateLimitExceeded(detail="Too many"), 429, "Too many"),
    (
        ValidationError({"timeout": ["Ensure this value is less than 300."]}),
        400,
        "Ensure this value is less than 300.",
    ),
]


def _call(method: str, **headers):
    request = getattr(APIRequestFactory(), method)(URL, **headers)
    return DeploymentExecution.as_view()(request, org_name="org", api_name="api")


def _raise(method: str, exc: Exception):
    with patch(
        "api_v2.api_deployment_views.DeploymentHelper.validate_parameters",
        side_effect=exc,
    ):
        return _call(method, **AUTH)


def _handler_body(exc: Exception, method: str) -> dict:
    """What the project-wide handler sends for `exc` on its own, i.e. the body
    clients parsed before `message` was added.
    """
    request = getattr(APIRequestFactory(), method)(URL)
    return dict(drf_logging_exc_handler(exc=exc, context={"request": request}).data)


def test_missing_key_on_execute_keeps_its_body_and_gains_message() -> None:
    response = _call("post")

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


@pytest.mark.parametrize(("exc", "status", "error"), RAISED)
def test_execute_errors_keep_the_handler_body_and_gain_message(
    exc, status, error
) -> None:
    response = _raise("post", exc)

    assert response.status_code == status
    legacy = {k: v for k, v in response.data.items() if k != "message"}
    assert legacy == _handler_body(exc, "post")
    assert response.data["message"] == {"execution_status": "ERROR", "error": error}


@pytest.mark.parametrize(("exc", "status", "error"), RAISED)
def test_status_read_errors_are_unchanged(exc, status, error) -> None:
    """On the status read `message` is the result, and the published client
    copies it out as one; an error block there would read as a result.
    """
    response = _raise("get", exc)

    assert response.status_code == status
    assert dict(response.data) == _handler_body(exc, "get")


def test_the_documented_execute_error_body_is_the_one_the_view_sends() -> None:
    response = _raise("post", UnauthorizedKey())

    assert set(response.data) == set(_schema("DeploymentErrorResponse")["required"])
    assert set(response.data["message"]) == set(_schema("ErrorMessage")["required"])


def test_details_are_joined_without_their_field() -> None:
    """Matches the published client's own rendering of a refused request, so
    the error text a caller sees does not change.
    """
    data = {
        "type": "validation_error",
        "errors": [
            {"code": "invalid", "detail": "Not a valid URL.", "attr": "presigned_urls"},
            {"code": "invalid", "detail": "At least one file.", "attr": None},
        ],
    }

    assert flatten_error(data) == "Not a valid URL.; At least one file."


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
