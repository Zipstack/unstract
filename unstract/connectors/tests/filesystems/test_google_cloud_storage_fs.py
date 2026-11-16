"""GCS connector test-connection request shape (UN-4224).

From gcsfs 2026.x, ``info("/")`` sends ``GET b/`` without the project, which
GCS rejects with ``Required parameter: project`` (400) for every connector.
Test connection must list buckets with the configured project instead — the
same request gcsfs 2024.x sent for ``info("/")``.
"""

from typing import Any

import pytest
from gcsfs import core as gcsfs_core

# The core class explicitly: production runs it (storage_compat keeps gcsfs off
# the experimental ExtendedGcsFileSystem), and `gcsfs.GCSFileSystem` would
# depend on whether gcsfs was imported before storage_compat in this process.
from gcsfs.core import GCSFileSystem

from unstract.connectors.filesystems.google_cloud_storage.google_cloud_storage import (
    GoogleCloudStorageFS,
)

_Calls = list[tuple[str, str, dict[str, Any]]]


@pytest.fixture
def gcs_requests(monkeypatch: pytest.MonkeyPatch) -> _Calls:
    """Record gcsfs API requests and answer the way GCS does."""
    calls: _Calls = []

    async def fake_call(
        self: GCSFileSystem, method: str, path: str, *args: Any, **kwargs: Any
    ) -> dict[str, Any]:
        calls.append((method, path, kwargs))
        if path.rstrip("/") == "b" and "project" not in kwargs:
            # What GCS answers for a bucket listing that carries no project.
            raise gcsfs_core.HttpError(
                {"code": 400, "message": "Required parameter: project"}
            )
        return {"kind": "storage#buckets", "items": [{"name": "bucket-a"}]}

    monkeypatch.setattr(gcsfs_core.GCSFileSystem, "_call", fake_call)
    return calls


def _connector(project: str) -> GoogleCloudStorageFS:
    connector = GoogleCloudStorageFS({"project_id": project, "json_credentials": "{}"})
    # Bypass the lazy credential-backed client; only the request shape matters.
    connector._gcs_fs = GCSFileSystem(
        token="anon", project=project, skip_instance_cache=True
    )
    return connector


def test_test_credentials_lists_buckets_with_the_configured_project(
    gcs_requests: _Calls,
) -> None:
    assert _connector("my-project").test_credentials() is True

    assert gcs_requests, "test_credentials made no request"
    method, path, kwargs = gcs_requests[0]
    assert (method, path) == ("GET", "b")
    assert kwargs.get("project") == "my-project"
    assert not any(c[1] == "b/" for c in gcs_requests), "sent the project-less GET b/"


def test_uses_the_core_gcsfs_class() -> None:
    assert type(_connector("my-project")._gcs_fs) is GCSFileSystem
    assert GCSFileSystem.__module__ == "gcsfs.core"
