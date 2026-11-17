"""Unit checks for the request id the backend logs and echoes.

Runs standalone like test_exception.py: a minimal settings object when the
suite hasn't configured Django.
"""

import uuid

import django
from django.conf import settings

if not settings.configured:
    settings.configure(INSTALLED_APPS=[], DATABASES={})
    django.setup()

from django.http import HttpResponse  # noqa: E402
from django.test import RequestFactory, override_settings  # noqa: E402

from middleware.request_id import CustomRequestIDMiddleware  # noqa: E402

SENT_ID = "00000000-0000-4000-8000-000000000001"


@override_settings(
    LOG_REQUEST_ID_HEADER="HTTP_X_REQUEST_ID",
    REQUEST_ID_RESPONSE_HEADER="X-Request-ID",
    GENERATE_REQUEST_ID_IF_NOT_IN_HEADER=True,
)
def _echoed_id(**headers: str) -> str:
    middleware = CustomRequestIDMiddleware(lambda request: HttpResponse())
    request = RequestFactory().get("/api/v1/health", headers=headers)
    response = middleware(request)
    echoed = str(request.id)
    assert response["X-Request-ID"] == echoed
    return echoed


def test_uses_the_clients_uuid() -> None:
    assert _echoed_id(x_request_id=SENT_ID) == SENT_ID


def test_replaces_a_non_uuid_value() -> None:
    echoed = _echoed_id(x_request_id="evil\nlog line")
    assert echoed != "evil\nlog line"
    assert uuid.UUID(echoed)


def test_generates_one_when_the_header_is_missing() -> None:
    assert uuid.UUID(_echoed_id())
