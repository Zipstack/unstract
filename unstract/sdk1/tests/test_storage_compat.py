"""Tests for ``unstract.sdk1.patches.storage_compat`` (UN-4224).

The boto3 1.43 / gcsfs 2026 upgrade changed three defaults that reach every
storage backend: aws-chunked uploads, CRC32 instead of Content-MD5 on
DeleteObjects, and gcsfs's experimental filesystem class. The module puts all
three back; these tests pin that on the wire and pin that the production entry
point actually loads it.
"""

import base64
import hashlib
import os
import subprocess
import sys
from typing import Any
from unittest import mock

import aiobotocore.endpoint
import botocore.handlers
import botocore.session
import pytest
from botocore.awsrequest import AWSResponse
from unstract.sdk1.file_storage.impl import FileStorage
from unstract.sdk1.file_storage.provider import FileStorageProvider
from unstract.sdk1.patches import storage_compat as compat

_DELETE_RESULT = (
    b'<?xml version="1.0" encoding="UTF-8"?>'
    b'<DeleteResult xmlns="http://s3.amazonaws.com/doc/2006-03-01/"></DeleteResult>'
)


def _md5_b64(body: bytes) -> str:
    return base64.b64encode(hashlib.md5(body, usedforsecurity=False).digest()).decode()


def _text_headers(headers: Any) -> dict[str, str]:  # noqa: ANN401
    return {k: v.decode() if isinstance(v, bytes) else v for k, v in headers.items()}


# ── DeleteObjects Content-MD5 on a sync botocore client ─────────────────────


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
        seen["headers"] = _text_headers(request.headers)
        seen["body"] = request.body
        return AWSResponse(request.url, 200, {}, _Raw())

    client.meta.events.register("before-send.s3.DeleteObjects", fake_send)
    client.delete_objects(Bucket="b", Delete={"Objects": [{"Key": k} for k in keys]})
    return seen


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


def test_registered_once_after_its_builtin_xml_escaping() -> None:
    entries = [
        h for h in botocore.handlers.BUILTIN_HANDLERS if h[1] is compat.add_content_md5
    ]
    assert [e[0] for e in entries] == [compat._EVENT]
    compat.register()  # idempotent
    assert [
        h for h in botocore.handlers.BUILTIN_HANDLERS if h[1] is compat.add_content_md5
    ] == entries
    names = [
        h[1].__name__ for h in botocore.handlers.BUILTIN_HANDLERS if h[0] == compat._EVENT
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
    compat.add_content_md5(params)
    assert params["headers"] == before


# ── On the wire through FileStorage → s3fs → aiobotocore ────────────────────


class _CapturedError(Exception):
    pass


def _capture_via_file_storage(
    operation: str, storage_config: dict[str, Any] | None = None, **params: object
) -> dict[str, Any]:
    """Issue one S3 call through sdk1 FileStorage and capture the request.

    Goes through the same path production uses — FileStorageHelper builds the
    s3fs filesystem, s3fs drives an aiobotocore client — and stops at
    aiobotocore's send, so nothing reaches the network. HTTPS matters: that is
    where botocore >= 1.36 switches uploads to aws-chunked.
    """
    seen: dict[str, Any] = {}

    async def capture(self: Any, request: Any, *_: Any, **__: Any) -> None:  # noqa: ANN401
        seen["headers"] = _text_headers(request.headers)
        seen["body"] = request.body
        raise _CapturedError()

    config = {
        "key": "k",
        "secret": "s",
        "endpoint_url": "https://minio.invalid",
        "skip_instance_cache": True,
        **(storage_config or {}),
    }
    storage = FileStorage(FileStorageProvider.MINIO, **config)
    with mock.patch.object(aiobotocore.endpoint.AioEndpoint, "_send", capture):
        with pytest.raises(_CapturedError):
            storage.fs.call_s3(operation, **params)
    return seen


def test_uploads_are_plain_payload_signed_not_aws_chunked() -> None:
    headers = _capture_via_file_storage("put_object", Bucket="b", Key="k", Body=b"hello")[
        "headers"
    ]
    assert headers.get("Content-Encoding") != "aws-chunked"
    assert "X-Amz-Trailer" not in headers
    assert headers["X-Amz-Content-SHA256"] == hashlib.sha256(b"hello").hexdigest()


def test_s3fs_delete_objects_carries_content_md5() -> None:
    seen = _capture_via_file_storage(
        "delete_objects", Bucket="b", Delete={"Objects": [{"Key": "a.txt"}]}
    )
    body = seen["body"] if isinstance(seen["body"], bytes) else bytes(seen["body"])
    assert seen["headers"]["Content-MD5"] == _md5_b64(body)


def test_explicit_config_kwargs_still_win() -> None:
    storage = FileStorage(
        FileStorageProvider.MINIO,
        key="k",
        secret="s",
        endpoint_url="https://minio.invalid",
        skip_instance_cache=True,
        config_kwargs={"request_checksum_calculation": "when_supported"},
    )
    assert storage.fs.config_kwargs == {
        "request_checksum_calculation": "when_supported",
        "response_checksum_validation": "when_required",
    }


# ── Production entry point loads it (fresh interpreter) ─────────────────────


def test_file_storage_helper_import_applies_all_three_settings() -> None:
    """Only the helper is imported, so this test's own import cannot satisfy it."""
    probe = (
        "import unstract.sdk1.file_storage.helper\n"
        "import botocore.handlers, gcsfs, fsspec, os\n"
        "names = [h[1].__name__ for h in botocore.handlers.BUILTIN_HANDLERS\n"
        "         if h[0] == 'before-call.s3.DeleteObjects']\n"
        "assert 'add_content_md5' in names, names\n"
        "assert os.environ['GCSFS_EXPERIMENTAL_ZB_HNS_SUPPORT'] == 'false'\n"
        "assert gcsfs.GCSFileSystem.__name__ == 'GCSFileSystem', gcsfs.GCSFileSystem\n"
        "assert fsspec.get_filesystem_class('gcs').__name__ == 'GCSFileSystem'\n"
    )
    env = {
        k: v for k, v in os.environ.items() if k != "GCSFS_EXPERIMENTAL_ZB_HNS_SUPPORT"
    }
    result = subprocess.run(
        [sys.executable, "-c", probe], env=env, capture_output=True, text=True
    )
    assert result.returncode == 0, result.stderr[-2000:]


def test_operator_can_still_opt_into_experimental_gcsfs() -> None:
    probe = (
        "import unstract.sdk1.file_storage.helper, gcsfs\n"
        "assert gcsfs.GCSFileSystem.__name__ == 'ExtendedGcsFileSystem'\n"
    )
    env = {**os.environ, "GCSFS_EXPERIMENTAL_ZB_HNS_SUPPORT": "true"}
    result = subprocess.run(
        [sys.executable, "-c", probe], env=env, capture_output=True, text=True
    )
    assert result.returncode == 0, result.stderr[-2000:]
