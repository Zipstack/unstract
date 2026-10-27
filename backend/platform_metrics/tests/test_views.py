"""GET /metrics: routing, auth exemption, bearer token, content type."""

from unittest.mock import MagicMock, patch

import pytest
from django.test import Client, override_settings

BODY = b"# HELP stub stub\n# TYPE stub gauge\nstub 1.0\n"


@pytest.fixture(autouse=True)
def exporter():
    fake = MagicMock()
    fake.render.return_value = BODY
    with patch("platform_metrics.views.get_exporter", return_value=fake):
        yield fake


@pytest.fixture
def client():
    return Client()


@override_settings(PLATFORM_METRICS_TOKEN="")
def test_served_without_a_session_when_no_token_is_configured(client):
    response = client.get("/metrics")

    assert response.status_code == 200
    assert response["Content-Type"] == "text/plain; version=0.0.4; charset=utf-8"
    assert response.content == BODY


@override_settings(PLATFORM_METRICS_TOKEN="s3cret")
def test_token_configured_rejects_a_missing_header(client, exporter):
    response = client.get("/metrics")

    assert response.status_code == 401
    assert response["WWW-Authenticate"].startswith("Bearer")
    exporter.render.assert_not_called()


@override_settings(PLATFORM_METRICS_TOKEN="s3cret")
@pytest.mark.parametrize("header", ["Bearer wrong", "Basic s3cret", "s3cret", "Bearer "])
def test_token_configured_rejects_a_wrong_header(client, exporter, header):
    response = client.get("/metrics", HTTP_AUTHORIZATION=header)

    assert response.status_code == 401
    exporter.render.assert_not_called()


@override_settings(PLATFORM_METRICS_TOKEN="s3cret")
def test_token_configured_accepts_the_right_bearer(client):
    response = client.get("/metrics", HTTP_AUTHORIZATION="Bearer s3cret")

    assert response.status_code == 200
    assert response.content == BODY


def test_only_get_is_allowed(client):
    assert client.post("/metrics").status_code == 405
