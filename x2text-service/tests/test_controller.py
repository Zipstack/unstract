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
        mock.patch.object(
            am.AuthenticationMiddleware, "validate_bearer_token", return_value=True
        ),
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
    r._content_consumed = True  # as after a real read; close() then skips raw
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
def test_refused_url_is_400_and_never_dialled(
    client, audit, monkeypatch, path, with_file
):
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
        "detail": "Unstructured API returned HTTP 401; check the API key, or whether this server needs one",
    }
    assert rq.call_args.kwargs["timeout"] == TIMEOUT
    # Default mode: requests follows redirects itself, as before the guard.
    assert "allow_redirects" not in rq.call_args.kwargs


def test_test_connection_timeout_is_504(client):
    with mock.patch.object(
        controller.requests, "request", side_effect=requests.ReadTimeout()
    ):
        r = _post(client, "/x2text/test-connection", "http://localhost:8000/x")
    assert r.status_code == 504
    assert r.get_json()["detail"] == controller.TIMED_OUT


PUBLIC = "http://93.184.215.14/general/v0/general"
OTHER_PUBLIC = "http://93.184.215.15/general/v0/general"


@pytest.fixture
def block_private(monkeypatch):
    monkeypatch.setenv("UNSTRUCTURED_URL_ALLOW_PRIVATE", "false")


@pytest.mark.parametrize(
    ("path", "with_file"), [("/x2text/test-connection", False), ("/x2text/process", True)]
)
def test_block_mode_refuses_redirect_to_private(
    client, audit, block_private, path, with_file
):
    upstream = _response(307, "", {"Location": "http://169.254.169.254/latest"})
    with mock.patch.object(controller.requests, "request", return_value=upstream) as rq:
        r = _post(client, path, PUBLIC, with_file)
    assert r.status_code == 400
    assert "private" in r.get_json()["detail"]
    assert rq.call_count == 1
    assert rq.call_args.kwargs["allow_redirects"] is False
    if with_file:
        assert audit.status == "Failed"
        audit.save.assert_called()


def test_block_mode_follows_allowed_307_replaying_upload(client, audit, block_private):
    hop = _response(307, "", {"Location": "/v1/general"})
    done = _response(200, '[{"text": "hello"}]', {"Content-Type": "application/json"})
    sent = []

    def record(method, url, **kwargs):
        sent.append(
            (
                method,
                url,
                kwargs["files"]["files"][1].read(),
                kwargs["headers"].get("unstructured-api-key"),
            )
        )
        return [hop, done][len(sent) - 1]

    with mock.patch.object(controller.requests, "request", side_effect=record):
        r = _post(client, "/x2text/process", PUBLIC, with_file=True)
    assert r.status_code == 200
    assert r.data == b"hello"
    assert sent == [
        ("POST", PUBLIC, b"abc", "k"),
        # Same host: the key goes with the upload.
        ("POST", "http://93.184.215.14/v1/general", b"abc", "k"),
    ]


def test_block_mode_303_becomes_get_and_cross_host_drops_key(client, block_private):
    hop = _response(303, "", {"Location": OTHER_PUBLIC})
    with mock.patch.object(
        controller.requests, "request", side_effect=[hop, _response(400)]
    ) as rq:
        r = _post(client, "/x2text/test-connection", PUBLIC)
    assert r.status_code == 200
    second = rq.call_args_list[1]
    assert second.args[:2] == ("GET", OTHER_PUBLIC)
    assert second.kwargs["files"] is None
    assert "unstructured-api-key" not in second.kwargs["headers"]
    assert "unstructured-api-key" in rq.call_args_list[0].kwargs["headers"]


def test_block_mode_caps_redirects(client, block_private):
    loop = _response(302, "", {"Location": PUBLIC})
    with mock.patch.object(controller.requests, "request", return_value=loop) as rq:
        r = _post(client, "/x2text/test-connection", PUBLIC)
    assert r.status_code == 400
    assert "redirects" in r.get_json()["detail"]
    assert rq.call_count == controller_max_redirects() + 1


def controller_max_redirects():
    from app import unstructured_url

    return unstructured_url.MAX_REDIRECTS


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
    # Default mode: requests follows redirects itself, as before the guard.
    assert "allow_redirects" not in rq.call_args.kwargs


def test_test_connection_unreachable_has_detail(client):
    with mock.patch.object(
        controller.requests, "request", side_effect=requests.ConnectionError()
    ):
        r = _post(client, "/x2text/test-connection", "http://localhost:8000/x")
    assert r.status_code == 400
    assert r.get_json()["detail"] == controller.UNREACHABLE


@pytest.mark.parametrize(
    ("path", "with_file"), [("/x2text/test-connection", False), ("/x2text/process", True)]
)
@pytest.mark.parametrize(
    "error_type", [requests.ConnectionError, requests.exceptions.InvalidURL]
)
def test_transport_error_log_omits_url_query(
    client, audit, caplog, path, with_file, error_type
):
    url = "http://localhost:8000/general?api_key=SECRET"
    error = error_type(f"Max retries exceeded with url: {url}")
    with mock.patch.object(controller.requests, "request", side_effect=error):
        _post(client, path, url, with_file)
    assert "localhost" in caplog.text
    assert "SECRET" not in caplog.text


@pytest.mark.parametrize(
    ("status", "hint"),
    [
        (500, ""),
        (404, "; check the URL path"),
        (403, "; check the API key, or whether this server needs one"),
    ],
)
def test_test_connection_status_detail(client, status, hint):
    upstream = _response(status, "internal page")
    with mock.patch.object(controller.requests, "request", return_value=upstream):
        r = _post(client, "/x2text/test-connection", "http://localhost:8000/x")
    assert r.get_json()["detail"] == f"Unstructured API returned HTTP {status}{hint}"


def test_test_connection_unexpected_error_has_detail(client):
    with mock.patch.object(
        controller.requests, "request", side_effect=RuntimeError("boom")
    ):
        r = _post(client, "/x2text/test-connection", "http://localhost:8000/x")
    assert r.status_code == 400
    assert r.get_json()["detail"] == "Test connection failed"


def test_block_mode_process_303_drops_body(client, audit, block_private):
    hop = _response(303, "", {"Location": "/v1/result"})
    done = _response(200, '[{"text": "hello"}]', {"Content-Type": "application/json"})
    with mock.patch.object(controller.requests, "request", side_effect=[hop, done]) as rq:
        r = _post(client, "/x2text/process", PUBLIC, with_file=True)
    assert r.status_code == 200
    second = rq.call_args_list[1]
    assert second.args[0] == "GET"
    assert second.kwargs["data"] is None
    assert second.kwargs["files"] is None
    assert rq.call_args_list[0].kwargs["data"] is not None


@pytest.mark.parametrize(
    ("location", "keeps_key"),
    [
        ("https://93.184.215.14/general/v0/general", True),  # http->https upgrade
        ("http://93.184.215.14:8081/general/v0/general", False),  # port change
    ],
)
def test_block_mode_key_follows_requests_strip_rule(
    client, block_private, location, keeps_key
):
    hop = _response(307, "", {"Location": location})
    with mock.patch.object(
        controller.requests, "request", side_effect=[hop, _response(400)]
    ) as rq:
        _post(client, "/x2text/test-connection", PUBLIC)
    assert ("unstructured-api-key" in rq.call_args_list[1].kwargs["headers"]) is keeps_key


def test_block_mode_https_to_http_drops_key(client, block_private):
    start = "https://93.184.215.14/general/v0/general"
    hop = _response(307, "", {"Location": PUBLIC})
    with mock.patch.object(
        controller.requests, "request", side_effect=[hop, _response(400)]
    ) as rq:
        _post(client, "/x2text/test-connection", start)
    assert "unstructured-api-key" not in rq.call_args_list[1].kwargs["headers"]


@pytest.mark.parametrize(
    ("path", "with_file"), [("/x2text/test-connection", False), ("/x2text/process", True)]
)
def test_block_mode_unparseable_location_is_refused(
    client, audit, block_private, path, with_file
):
    hop = _response(307, "", {"Location": "http://[abc/x"})
    with mock.patch.object(controller.requests, "request", return_value=hop):
        r = _post(client, path, PUBLIC, with_file)
    assert r.status_code == 400
    assert "unparseable Location" in r.get_json()["detail"]
    if with_file:
        assert audit.status == "Failed"
