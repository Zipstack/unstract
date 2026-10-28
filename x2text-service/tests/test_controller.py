"""x2text routes: refusal, redirect, timeout and response shape."""

import io
from unittest import mock

import pytest
import requests
from flask import Flask

import app.authentication_middleware as am
from app.controllers import controller

TIMEOUT = (10.0, 900.0)


@pytest.fixture
def client(monkeypatch):
    monkeypatch.delenv("UNSTRUCTURED_URL_ALLOW_PRIVATE", raising=False)
    monkeypatch.delenv("UNSTRUCTURED_REQUEST_TIMEOUT", raising=False)
    app = Flask(__name__)
    app.register_blueprint(controller.basic, url_prefix="/x2text")
    with (
        mock.patch.object(am.AuthenticationMiddleware, "validate_bearer_token", return_value=True),
        mock.patch.object(
            am.AuthenticationMiddleware,
            "get_organization_from_bearer_token",
            return_value=(None, "org"),
        ),
    ):
        yield app.test_client()


@pytest.fixture
def audit():
    with mock.patch.object(controller, "X2TextAudit") as model:
        yield model.create.return_value


def _response(status, text="", headers=None):
    r = requests.models.Response()
    r.status_code = status
    r._content = text.encode()
    r.headers.update(headers or {})
    return r


def _post(client, path, url, with_file=False):
    data = {"unstructured-url": url, "unstructured-api-key": "k"}
    if with_file:
        data["file"] = (io.BytesIO(b"abc"), "a.pdf")
    return client.post(
        path,
        data=data,
        headers={"Authorization": "Bearer t"},
        content_type="multipart/form-data",
    )


@pytest.mark.parametrize(
    ("path", "with_file"), [("/x2text/test-connection", False), ("/x2text/process", True)]
)
def test_refused_url_is_400_and_never_dialled(client, audit, monkeypatch, path, with_file):
    monkeypatch.setenv("UNSTRUCTURED_URL_ALLOW_PRIVATE", "false")
    with mock.patch.object(controller.requests, "request") as upstream:
        r = _post(client, path, "http://169.254.169.254/latest/meta-data", with_file)
    assert r.status_code == 400
    assert "private" in r.get_json()["detail"]
    upstream.assert_not_called()


def test_test_connection_upstream_body_is_json_and_not_in_detail(client):
    upstream = _response(401, "<script>x</script>")
    with mock.patch.object(controller.requests, "request", return_value=upstream) as rq:
        r = _post(client, "/x2text/test-connection", "http://localhost:8000/x")
    assert r.status_code == 401
    assert r.content_type == "application/json"
    # sdk1 shows ``detail`` to the user; the upstream body must not be in it.
    assert r.get_json() == {
        "message": "<script>x</script>",
        "detail": "Unstructured API returned HTTP 401; check the API key",
    }
    assert rq.call_args.kwargs["timeout"] == TIMEOUT
    assert rq.call_args.kwargs["allow_redirects"] is False


def test_test_connection_timeout_is_504(client):
    with mock.patch.object(controller.requests, "request", side_effect=requests.ReadTimeout()):
        r = _post(client, "/x2text/test-connection", "http://localhost:8000/x")
    assert r.status_code == 504
    assert r.get_json()["detail"] == controller.TIMED_OUT


@pytest.mark.parametrize(
    ("path", "with_file"), [("/x2text/test-connection", False), ("/x2text/process", True)]
)
def test_redirect_is_refused(client, audit, path, with_file):
    upstream = _response(307, "", {"Location": "http://169.254.169.254/"})
    with mock.patch.object(controller.requests, "request", return_value=upstream):
        r = _post(client, path, "http://localhost:8000/x", with_file)
    assert r.status_code == 400
    assert r.get_json()["detail"] == controller.REDIRECT_REFUSED
    if with_file:
        assert audit.status == "Failed"
        audit.save.assert_called()


@pytest.mark.parametrize(
    ("error", "status"),
    [(requests.ReadTimeout(), 504), (requests.ConnectionError(), 502)],
)
def test_process_transport_error_marks_audit_failed(client, audit, error, status):
    with mock.patch.object(controller.requests, "request", side_effect=error):
        r = _post(client, "/x2text/process", "http://localhost:8000/x", with_file=True)
    assert r.status_code == status
    assert "detail" in r.get_json()
    assert audit.status == "Failed"
    audit.save.assert_called()


def test_process_success_unchanged(client, audit):
    upstream = _response(200, '[{"text": "hello"}]', {"Content-Type": "application/json"})
    with mock.patch.object(controller.requests, "request", return_value=upstream) as rq:
        r = _post(client, "/x2text/process", "http://localhost:8000/x", with_file=True)
    assert r.status_code == 200
    assert r.data == b"hello"
    assert audit.status == "Success"
    assert rq.call_args.kwargs["timeout"] == TIMEOUT
    assert rq.call_args.kwargs["allow_redirects"] is False


def test_test_connection_unreachable_has_detail(client):
    with mock.patch.object(controller.requests, "request", side_effect=requests.ConnectionError()):
        r = _post(client, "/x2text/test-connection", "http://localhost:8000/x")
    assert r.status_code == 400
    assert r.get_json()["detail"] == controller.UNREACHABLE


@pytest.mark.parametrize(
    ("path", "with_file"), [("/x2text/test-connection", False), ("/x2text/process", True)]
)
@pytest.mark.parametrize("error_type", [requests.ConnectionError, requests.exceptions.InvalidURL])
def test_transport_error_log_omits_url_query(
    client, audit, caplog, path, with_file, error_type
):
    url = "http://localhost:8000/general?api_key=SECRET"
    error = error_type(f"Max retries exceeded with url: {url}")
    with mock.patch.object(controller.requests, "request", side_effect=error):
        _post(client, path, url, with_file)
    assert "localhost" in caplog.text
    assert "SECRET" not in caplog.text


@pytest.mark.parametrize(("status", "hint"), [(500, ""), (404, "; check the URL path")])
def test_test_connection_status_detail(client, status, hint):
    upstream = _response(status, "internal page")
    with mock.patch.object(controller.requests, "request", return_value=upstream):
        r = _post(client, "/x2text/test-connection", "http://localhost:8000/x")
    assert r.get_json()["detail"] == f"Unstructured API returned HTTP {status}{hint}"


def test_test_connection_unexpected_error_has_detail(client):
    with mock.patch.object(controller.requests, "request", side_effect=RuntimeError("boom")):
        r = _post(client, "/x2text/test-connection", "http://localhost:8000/x")
    assert r.status_code == 400
    assert r.get_json()["detail"] == "Test connection failed"
