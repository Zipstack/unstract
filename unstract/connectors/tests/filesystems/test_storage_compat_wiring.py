"""The connectors load sdk1's storage_compat on their own (UN-4224).

Each probe runs in a fresh interpreter and imports only the connector module,
so nothing in this test process can satisfy it. Deleting the import from the
connector must fail these tests.
"""

import os
import subprocess
import sys

from unstract.connectors.filesystems.minio.minio import MinioFS
from unstract.connectors.filesystems.ucs.ucs import UnstractCloudStorage

_EXPECTED_CHECKSUM_CONFIG = {
    "request_checksum_calculation": "when_required",
    "response_checksum_validation": "when_required",
}


def _run_probe(probe: str) -> None:
    env = {
        k: v for k, v in os.environ.items() if k != "GCSFS_EXPERIMENTAL_ZB_HNS_SUPPORT"
    }
    # The connectors package is on the path via pytest's `pythonpath`, which a
    # child interpreter does not inherit.
    env["PYTHONPATH"] = os.pathsep.join(p for p in sys.path if p)
    result = subprocess.run(
        [sys.executable, "-c", probe], env=env, capture_output=True, text=True
    )
    assert result.returncode == 0, result.stderr[-2000:]


def test_minio_connector_import_registers_delete_objects_md5() -> None:
    _run_probe(
        "import unstract.connectors.filesystems.minio.minio\n"
        "import botocore.handlers\n"
        "names = [h[1].__name__ for h in botocore.handlers.BUILTIN_HANDLERS\n"
        "         if h[0] == 'before-call.s3.DeleteObjects']\n"
        "assert 'add_content_md5' in names, names\n"
    )


def test_gcs_connector_import_keeps_core_gcsfs() -> None:
    _run_probe(
        "import unstract.connectors.filesystems.google_cloud_storage."
        "google_cloud_storage\n"
        "import gcsfs\n"
        "assert gcsfs.GCSFileSystem.__name__ == 'GCSFileSystem', gcsfs.GCSFileSystem\n"
    )


def test_minio_and_ucs_send_plain_uploads() -> None:
    # No aws-chunked uploads: UCS is GCS's S3 interop API, MinIO may sit behind
    # TLS; both get the payload-signed requests boto3 1.34 sent.
    settings = {
        "key": "k",
        "secret": "s",
        "endpoint_url": "https://storage.example",
        "bucket": "b",
    }
    for fs_class in (MinioFS, UnstractCloudStorage):
        s3 = fs_class(settings).s3
        assert s3.config_kwargs == _EXPECTED_CHECKSUM_CONFIG, fs_class.__name__
