"""Tests for the S3 DeleteObjects Content-MD5 hook (UN-4224).

botocore >= 1.36 sends a CRC32 checksum instead of Content-MD5 on
DeleteObjects; MinIO older than RELEASE.2025-01-20 rejects that with
MissingContentMD5. The hook puts Content-MD5 back on every session.
"""

import base64
import hashlib
from typing import Any

import botocore.handlers
import botocore.session
import pytest
from botocore.awsrequest import AWSResponse
from unstract.sdk1.patches import s3_delete_objects_md5 as hook

_DELETE_RESULT = (
    b'<?xml version="1.0" encoding="UTF-8"?>'
    b'<DeleteResult xmlns="http://s3.amazonaws.com/doc/2006-03-01/"></DeleteResult>'
)


class _Raw:
    def stream(self, **_: Any) -> Any:  # noqa: ANN401
        yield _DELETE_RESULT


def _capture_delete_objects(keys: list[str]) -> dict[str, Any]:
    """Send a real botocore DeleteObjects and capture the wire request."""
    session = botocore.session.get_session()
    client = session.create_client(
        "s3",
        region_name="us-east-1",
        endpoint_url="http://minio.invalid:9000",
        aws_access_key_id="k",
        aws_secret_access_key="s",
    )
    seen: dict[str, Any] = {}

    def fake_send(request: Any, **_: Any) -> AWSResponse:  # noqa: ANN401
        # Prepared request headers are bytes on the wire; compare as text.
        seen["headers"] = {
            k: v.decode() if isinstance(v, bytes) else v
            for k, v in request.headers.items()
        }
        seen["body"] = request.body
        return AWSResponse(request.url, 200, {}, _Raw())

    client.meta.events.register("before-send.s3.DeleteObjects", fake_send)
    client.delete_objects(Bucket="b", Delete={"Objects": [{"Key": k} for k in keys]})
    return seen


def _md5_b64(body: bytes) -> str:
    return base64.b64encode(hashlib.md5(body, usedforsecurity=False).digest()).decode()


def test_delete_objects_carries_content_md5_of_the_final_body() -> None:
    seen = _capture_delete_objects(["a.txt", "dir/b.txt"])
    body = seen["body"] if isinstance(seen["body"], bytes) else seen["body"].read()
    assert seen["headers"]["Content-MD5"] == _md5_b64(body)


def test_digest_covers_xml_escaped_keys() -> None:
    # botocore's `escape_xml_payload` rewrites the body on the same event; the
    # hook must run after it or MinIO rejects the digest as BadDigest.
    seen = _capture_delete_objects(["a\r\nb.txt"])
    body = seen["body"] if isinstance(seen["body"], bytes) else seen["body"].read()
    assert b"&#xD;" in body
    assert seen["headers"]["Content-MD5"] == _md5_b64(body)


def _registered_md5_handlers() -> list[tuple[str, Any]]:
    return [
        h
        for h in botocore.handlers.BUILTIN_HANDLERS
        if getattr(h[1], "__name__", "") == "add_content_md5"
    ]


def test_registered_once_after_its_builtin_xml_escaping() -> None:
    entries = _registered_md5_handlers()
    assert [e[0] for e in entries] == [hook._EVENT]
    hook.register()  # idempotent
    assert _registered_md5_handlers() == entries
    names = [
        h[1].__name__ for h in botocore.handlers.BUILTIN_HANDLERS if h[0] == hook._EVENT
    ]
    assert names.index("escape_xml_payload") < names.index("add_content_md5")


@pytest.mark.parametrize(
    "params",
    [
        {"headers": {"Content-MD5": "preset"}, "body": b"<x/>"},
        {
            "headers": {},
            "body": b"<x/>",
            "context": {"endpoint_properties": {"backend": "S3Express"}},
        },
        {"headers": {}, "body": None},
    ],
    ids=["keeps-existing-header", "skips-s3-express", "skips-streaming-body"],
)
def test_leaves_request_alone_when_it_should(params: dict[str, Any]) -> None:
    before = dict(params["headers"])
    hook.add_content_md5(params)
    assert params["headers"] == before
