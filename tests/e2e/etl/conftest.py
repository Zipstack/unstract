"""Fixtures for the ETL e2e tests: an object store and a filesystem workflow.

MinIO is the only storage connector the compose stack both boots and registers,
so it stands in for "a connector" here. The local-filesystem connector would
need no infra at all but is never registered, so it cannot be selected.
"""

from __future__ import annotations

import os
import uuid
from dataclasses import dataclass
from typing import TYPE_CHECKING

import pytest
import requests

from tests.e2e.conftest import ProvisionedWorkflow

if TYPE_CHECKING:
    from minio import Minio

# Registry id from unstract.connectors (filesystems/minio).
_MINIO_CONNECTOR = "minio|c799f6e3-2b57-434e-aaac-b5daa415da19"

# Created by the stack's minio-bootstrap; the ETL run only adds prefixes to it.
_BUCKET = "unstract"


@dataclass(frozen=True)
class MinioFixture:
    """Where the test and the workers each reach the object store."""

    client: Minio
    bucket: str
    # The workers resolve MinIO over the compose network, the test over a
    # published port, so the two see different endpoints for the same store.
    internal_url: str
    access_key: str
    secret_key: str


@dataclass(frozen=True)
class EtlWorkflow:
    """A workflow whose endpoints read and write an object store."""

    session: requests.Session
    prefix: str
    workflow_id: str
    input_prefix: str
    output_prefix: str


@pytest.fixture(scope="session")
def minio_store() -> MinioFixture:
    """The stack's MinIO, or a skip when this runtime doesn't publish one."""
    rig_session = os.environ.get("UNSTRACT_RIG_SESSION_ID")
    try:
        import minio
    except ImportError as exc:
        # The rig injects minio>=7.2.0, so a missing client under it is a
        # provisioning fault, not a legitimate "not installed" skip.
        if rig_session:
            pytest.fail(f"rig run but minio client not importable: {exc}")
        pytest.skip("minio client not installed")
    endpoint = os.environ.get("UNSTRACT_MINIO_ENDPOINT", "localhost:9000")
    access_key = os.environ.get("UNSTRACT_MINIO_ACCESS_KEY", "minio")
    secret_key = os.environ.get("UNSTRACT_MINIO_SECRET_KEY", "minio123")
    # One scheme drives both halves so they can't disagree: the workers' URL and
    # the test client's TLS flag. The compose stack serves MinIO plain; a
    # TLS-fronted deployment sets UNSTRACT_MINIO_SCHEME=https.
    scheme = os.environ.get("UNSTRACT_MINIO_SCHEME", "http")
    internal_url = os.environ.get(
        "UNSTRACT_MINIO_INTERNAL_URL", f"{scheme}://unstract-minio:9000"
    )
    client = minio.Minio(
        endpoint, access_key=access_key, secret_key=secret_key, secure=scheme == "https"
    )
    try:
        exists = client.bucket_exists(_BUCKET)
    except Exception as exc:  # noqa: BLE001 - narrow verdict below
        # Under the rig the stack is meant to be up, so an unusable MinIO is a
        # real failure to surface, not a store that legitimately isn't there.
        if rig_session:
            pytest.fail(f"rig provisioned the stack but MinIO is unusable: {exc}")
        pytest.skip(f"MinIO unreachable at {endpoint}: {exc}")
    if not exists:
        pytest.skip(f"MinIO bucket {_BUCKET!r} missing at {endpoint}")
    return MinioFixture(
        client=client,
        bucket=_BUCKET,
        internal_url=internal_url,
        access_key=access_key,
        secret_key=secret_key,
    )


def _post(session: requests.Session, url: str, **kwargs: object) -> requests.Response:
    return session.post(url, timeout=60, **kwargs)  # CsrfSession stamps the header


def _patch(session: requests.Session, url: str, **kwargs: object) -> requests.Response:
    return session.patch(url, timeout=60, **kwargs)


@pytest.fixture(scope="session")
def etl_workflow(
    provisioned_workflow: ProvisionedWorkflow, minio_store: MinioFixture
) -> EtlWorkflow:
    """A second workflow, reading and writing MinIO instead of the API.

    Reuses the exported tool but not the workflow: endpoints are per-workflow
    and the API one is already committed to serving the deployment tests.
    """
    pw = provisioned_workflow
    s = pw.session
    sfx = uuid.uuid4().hex[:8]
    input_prefix = f"e2e-in-{sfx}"
    output_prefix = f"e2e-out-{sfx}"

    def create_connector(connector_type: str) -> str:
        name = f"e2e-{connector_type.lower()}-{sfx}"
        resp = _post(
            s,
            f"{pw.prefix}/connector/",
            json={
                "connector_id": _MINIO_CONNECTOR,
                "connector_name": name,
                "connector_type": connector_type,
                "connector_metadata": {
                    "connectorName": name,
                    "key": minio_store.access_key,
                    "secret": minio_store.secret_key,
                    "endpoint_url": minio_store.internal_url,
                    "region_name": "us-east-1",
                },
            },
        )
        assert resp.status_code == 201, f"connector {connector_type}: {resp.text}"
        return resp.json()["id"]

    source_id = create_connector("INPUT")
    destination_id = create_connector("OUTPUT")

    resp = _post(s, f"{pw.prefix}/workflow/", json={"workflow_name": f"e2e-etl-{sfx}"})
    assert resp.status_code == 201, f"create workflow: {resp.text}"
    workflow_id = resp.json()["id"]

    resp = s.get(
        f"{pw.prefix}/workflow/endpoint/", params={"workflow": workflow_id}, timeout=30
    )
    resp.raise_for_status()
    body = resp.json()
    endpoints = body if isinstance(body, list) else body.get("results", [])
    by_type = {
        e["endpoint_type"]: e for e in endpoints if e.get("workflow") == workflow_id
    }
    assert {"SOURCE", "DESTINATION"} <= set(by_type), endpoints

    resp = _patch(
        s,
        f"{pw.prefix}/workflow/endpoint/{by_type['SOURCE']['id']}/",
        json={
            "connection_type": "FILESYSTEM",
            "connector_instance_id": source_id,
            "configuration": {
                "folders": [f"/{minio_store.bucket}/{input_prefix}"],
                "processSubDirectories": False,
                "maxFiles": 1,
                "fileProcessingOrder": "unordered",
            },
        },
    )
    assert resp.status_code == 200, f"source endpoint: {resp.text}"

    resp = _patch(
        s,
        f"{pw.prefix}/workflow/endpoint/{by_type['DESTINATION']['id']}/",
        json={
            "connection_type": "FILESYSTEM",
            "connector_instance_id": destination_id,
            "configuration": {"outputFolder": f"{minio_store.bucket}/{output_prefix}"},
        },
    )
    assert resp.status_code == 200, f"destination endpoint: {resp.text}"

    resp = _post(
        s,
        f"{pw.prefix}/tool_instance/",
        json={"workflow_id": workflow_id, "tool_id": pw.prompt_registry_id},
    )
    assert resp.status_code == 201, f"attach tool: {resp.text}"

    return EtlWorkflow(
        session=s,
        prefix=pw.prefix,
        workflow_id=workflow_id,
        input_prefix=input_prefix,
        output_prefix=output_prefix,
    )
