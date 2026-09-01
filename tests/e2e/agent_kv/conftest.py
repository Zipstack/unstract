"""Fixtures and HTTP helpers shared by the Agent-KV e2e tests.

This lane exercises the Agent-KV *product* API (``/agent-kv/...``, top-level,
API-key authed -- not the tenant-scoped platform surface most other e2e
lanes hit). It needs a deployment where the cloud ``agentic_kv`` executor
plugin is installed (``plugins.get_plugin("agent_kv")`` truthy) -- an
OSS-only build 501s every submit (see ``docs/agent-kv-api.md`` §11). The
module-level skip in ``test_agent_kv_e2e.py`` keeps this lane from running
by accident under a plain OSS e2e sweep; this conftest assumes that guard
already passed by the time any fixture here actually executes.
"""

from __future__ import annotations

import json
import time
import uuid
from dataclasses import dataclass
from pathlib import Path

import pytest
import requests

from tests.e2e.conftest import _org_id
from tests.rig.runtime import PlatformEndpoints

FIXTURES_DIR = Path(__file__).parent / "fixtures"
# A real, OCR-able 2-page invoice, generated for this lane with reportlab (the
# checked-in backend/agent_kv/tests/fixtures/two_page.pdf has no extractable
# text -- pdfplumber reads it as two blank pages -- so it can't stand in for
# an extraction fixture). It's a static binary checked into the repo; the e2e
# venv itself does not depend on reportlab to regenerate it at test time.
INVOICE_PDF = FIXTURES_DIR / "invoice.pdf"
# A small single-sheet invoice workbook (generated with openpyxl, checked in
# as a static binary like invoice.pdf): Excel exercises the no-pre-OCR-page-
# count path -- ``pages_total`` is None at submit and the engine enforces the
# post-OCR virtual-page cap instead.
INVOICE_XLSX = FIXTURES_DIR / "invoice.xlsx"

# The 3 leaves the happy-path schema asks for; also used to build the schema.
INVOICE_FIELDS = ("invoice_number", "vendor_name", "total_amount")

_DEFAULT_TIMEOUT = 30


@dataclass(frozen=True)
class AgentKVAuth:
    """A usable Agent-KV API key plus the backend root it's valid against."""

    base: str  # backend root, e.g. http://localhost:8000 (no trailing slash)
    key: str  # raw AgentKVKey UUID
    org_id: str

    @property
    def headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.key}"}

    @property
    def exec_url(self) -> str:
        return f"{self.base}/agent-kv/"

    def job_url(self, job_id: str, suffix: str = "") -> str:
        return f"{self.base}/agent-kv/{job_id}{suffix}"


@pytest.fixture(scope="session")
def agent_kv_key(
    platform: PlatformEndpoints, authed_session: requests.Session
) -> AgentKVAuth:
    """Create a fresh AgentKVKey for this session via the tenant API.

    Session-scoped: one key, reused by every test in the lane (mirrors
    ``api_deployment``'s ``api_deployment`` fixture). Key management sits
    under the tenant-scoped platform surface
    (``{base}/api/v1/unstract/{org_id}/agent-kv/keys/``), unlike the
    execution endpoints this key then authenticates against.
    """
    base = platform.backend_url.rstrip("/")
    org_id = _org_id(authed_session, base)
    prefix = f"{base}/api/v1/unstract/{org_id}"
    name = f"e2e-agent-kv-{uuid.uuid4().hex[:8]}"
    resp = authed_session.post(
        f"{prefix}/agent-kv/keys/",
        json={"name": name, "description": "agent-kv e2e lane"},
        timeout=_DEFAULT_TIMEOUT,
    )
    assert resp.status_code == 201, f"create agent-kv key: {resp.text}"
    body = resp.json()
    return AgentKVAuth(base=base, key=body["key"], org_id=org_id)


def submit_raw(
    auth: AgentKVAuth,
    file_bytes: bytes,
    filename: str,
    keys: dict | None,
    **fields: object,
) -> requests.Response:
    """POST a submit request and return the raw response -- no assertions.

    For tests that need to inspect a non-202 outcome (403, 400, 429, ...).
    ``keys=None`` omits the field entirely (covers submits that intend to
    fail before schema validation is even reached).
    """
    data = {str(k): v for k, v in fields.items()}
    if keys is not None:
        data["keys"] = json.dumps(keys)
    return requests.post(
        auth.exec_url,
        headers=auth.headers,
        files={"file": (filename, file_bytes, "application/octet-stream")},
        data=data,
        timeout=60,
    )


def submit(
    auth: AgentKVAuth,
    file_bytes: bytes,
    filename: str,
    keys: dict,
    **fields: object,
) -> tuple[str, str]:
    """POST a submit request expected to succeed; return (job_id, status_url).

    Asserts the 202 handshake (spec §7.1 / docs §3) so every caller only ever
    polls a genuinely dispatched job. A 501 here almost always means the
    cloud ``agentic_kv`` executor plugin isn't installed on this deployment
    -- this whole lane requires it (docs §11).
    """
    resp = submit_raw(auth, file_bytes, filename, keys, **fields)
    assert resp.status_code == 202, (
        f"submit: HTTP {resp.status_code} (expected 202; a 501 means the "
        f"agent-kv engine plugin isn't installed on this deployment): {resp.text}"
    )
    body = resp.json()
    job_id = body["job_id"]
    status_url = body["status_url"]
    assert job_id, body
    return job_id, status_url


TERMINAL_JOB_STATUSES = {"completed", "failed", "cancelled"}


def poll(auth: AgentKVAuth, job_id: str, timeout_s: float = 600) -> dict:
    """Poll the status document until the job reaches a terminal state.

    Returns the last status document. Fails loudly (rather than looping
    forever) once ``timeout_s`` elapses.
    """
    deadline = time.monotonic() + timeout_s
    last: dict = {}
    while time.monotonic() < deadline:
        resp = requests.get(
            auth.job_url(job_id), headers=auth.headers, timeout=_DEFAULT_TIMEOUT
        )
        assert resp.status_code == 200, f"status poll: {resp.status_code}: {resp.text}"
        last = resp.json()
        if last.get("status") in TERMINAL_JOB_STATUSES:
            return last
        time.sleep(2)
    pytest.fail(f"job {job_id} not terminal within {timeout_s}s; last status: {last}")


def result(auth: AgentKVAuth, job_id: str) -> requests.Response:
    """GET the result endpoint and return the raw response (any status)."""
    return requests.get(
        auth.job_url(job_id, "/result"), headers=auth.headers, timeout=_DEFAULT_TIMEOUT
    )


def cancel(auth: AgentKVAuth, job_id: str) -> requests.Response:
    return requests.post(
        auth.job_url(job_id, "/cancel"), headers=auth.headers, timeout=_DEFAULT_TIMEOUT
    )


def delete(auth: AgentKVAuth, job_id: str) -> requests.Response:
    return requests.delete(
        auth.job_url(job_id), headers=auth.headers, timeout=_DEFAULT_TIMEOUT
    )


def invoice_schema() -> dict:
    """A 3-leaf schema matching ``fixtures/invoice.pdf``'s obvious fields."""
    return {
        "invoice_number": {"description": "The invoice number", "required": True},
        "vendor_name": {"description": "The vendor or supplier name issuing the invoice"},
        "total_amount": {
            "description": "The total amount due on the invoice",
            "format": "currency",
        },
    }


def invalid_schema() -> dict:
    """A schema that fails to compile: a leaf missing the required 'description'."""
    return {"total": {"format": "currency"}}
