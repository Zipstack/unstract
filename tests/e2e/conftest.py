"""E2E fixtures: a session-scoped ``platform`` fixture that yields URLs/creds.

The rig brings the platform up at the *rig* level (once per ``run`` invocation,
not per pytest session) and propagates URLs into pytest via env vars. This
conftest reads those env vars; if they're missing, e2e tests are skipped with
a clear message rather than spuriously failing.
"""

from __future__ import annotations

import os
import uuid
from dataclasses import dataclass

import pytest
import requests

from tests.rig.runtime import LLM_MOCK_RESPONSE_ENV, PlatformEndpoints

# Adapter registry ids from unstract.sdk1, chosen so no real service is needed:
# the NoOp rows return canned output and the LLM is mocked. Fake creds persist
# because adapter create does not validate connectivity.
_LLM_ADAPTER = "openai|502ecf49-e47c-445c-9907-6d4b90c5cd17"
_EMBED_ADAPTER = "openai|717a0b0e-3bbc-41dc-9f0c-5689437a1151"
_VECTORDB_ADAPTER = "noOpVectorDb|ca4d6056-4971-4bc8-97e3-9e36290b5bc0"
_X2TEXT_ADAPTER = "noOpX2text|mp66d1op-7100-d340-9101-846fc7115676"


@pytest.fixture(scope="session")
def platform() -> PlatformEndpoints:
    if not os.environ.get("UNSTRACT_BACKEND_URL"):
        pytest.skip(
            "platform URLs not set in env; run via "
            "`python -m tests.rig run --tier e2e ...` or export "
            "UNSTRACT_BACKEND_URL (etc.) yourself."
        )
    return PlatformEndpoints.from_env()


@pytest.fixture(scope="session")
def authed_session(platform: PlatformEndpoints) -> requests.Session:
    """A logged-in session with the active organization set.

    Standardizes the OSS mock-login flow so tests don't re-implement it: form
    POST to /api/v1/login (302 + sessionid), then the org handshake
    (GET /organization seeds the csrftoken cookie, POST /organization/{id}/set
    with X-CSRFToken) so org-scoped endpoints are reachable. Session-scoped:
    logged in once, reused across tests. Tests that exercise login itself
    should build their own session instead.
    """
    base = platform.backend_url.rstrip("/")
    session = requests.Session()

    resp = session.post(
        f"{base}/api/v1/login",
        data={"username": platform.admin_user, "password": platform.admin_password},
        allow_redirects=False,
        timeout=10,
    )
    assert resp.status_code == 302, (
        f"login failed: expected 302, got {resp.status_code} "
        "(200 with HTML means bad credentials)"
    )

    # GET /organization sets the csrftoken cookie and returns the org id, which
    # the following POST needs both as a cookie and echoed in the CSRF header.
    orgs = session.get(f"{base}/api/v1/organization", timeout=10)
    orgs.raise_for_status()
    org_list = orgs.json().get("organizations", [])
    assert org_list, (
        f"no organizations returned by /api/v1/organization — is seed data "
        f"loaded? response: {orgs.text}"
    )
    org_id = org_list[0]["id"]
    resp = session.post(
        f"{base}/api/v1/organization/{org_id}/set",
        headers={"X-CSRFToken": session.cookies.get("csrftoken", "")},
        timeout=10,
    )
    resp.raise_for_status()
    return session


@pytest.fixture(scope="session")
def llm_mock_response() -> str:
    """The exact string the workers were told to return for every completion.

    Skips rather than guesses when unset: there is no deterministic answer to
    assert unless the workers got the same value.
    """
    value = os.environ.get(LLM_MOCK_RESPONSE_ENV)
    if not value:
        pytest.skip(
            f"{LLM_MOCK_RESPONSE_ENV} not set — execute-path e2e needs the LLM "
            "mock; the rig sets it when it boots the platform."
        )
    return value


@dataclass(frozen=True)
class ProvisionedWorkflow:
    """Handles for a hermetic, execute-ready workflow (one Prompt Studio tool)."""

    session: requests.Session
    base: str  # backend root, e.g. http://localhost:8000
    prefix: str  # tenant-scoped API root: {base}/api/v1/unstract/{org_id}
    org_id: str
    workflow_id: str
    tool_id: str
    prompt_registry_id: str
    profile_id: str
    prompt_id: str
    prompt_key: str


def _org_id(session: requests.Session, base: str) -> str:
    orgs = session.get(f"{base}/api/v1/organization", timeout=10)
    orgs.raise_for_status()
    return orgs.json()["organizations"][0]["id"]


def _post(session: requests.Session, url: str, **kw: object) -> requests.Response:
    headers = dict(kw.pop("headers", {}))
    headers["X-CSRFToken"] = session.cookies.get("csrftoken", "")
    return session.post(url, headers=headers, timeout=60, **kw)


def _patch(session: requests.Session, url: str, **kw: object) -> requests.Response:
    headers = dict(kw.pop("headers", {}))
    headers["X-CSRFToken"] = session.cookies.get("csrftoken", "")
    return session.patch(url, headers=headers, timeout=60, **kw)


@pytest.fixture(scope="session")
def provisioned_workflow(
    platform: PlatformEndpoints, authed_session: requests.Session
) -> ProvisionedWorkflow:
    """Stand up an API workflow backed by a single Prompt Studio tool.

    Provisioned over HTTP rather than via the ORM so setup exercises the same
    surface as the app. Executes hermetically: the LLM is mocked, and
    chunk_size=0 keeps embedding and vectordb out of the path.
    """
    s = authed_session
    base = platform.backend_url.rstrip("/")
    org_id = _org_id(s, base)
    prefix = f"{base}/api/v1/unstract/{org_id}"
    sfx = uuid.uuid4().hex[:8]  # adapter/tool names are unique per org

    def create_adapter(adapter_id: str, adapter_type: str, metadata: dict) -> str:
        name = f"e2e-{adapter_type.lower()}-{sfx}"
        resp = _post(
            s,
            f"{prefix}/adapter/",
            json={
                "adapter_id": adapter_id,
                "adapter_name": name,
                "adapter_type": adapter_type,
                "adapter_metadata": {"adapter_name": name, **metadata},
            },
        )
        assert resp.status_code == 201, f"adapter {adapter_type}: {resp.text}"
        return resp.json()["id"]

    # api_base is required even though the completion is mocked: params are
    # validated before the mock short-circuits.
    llm_id = create_adapter(
        _LLM_ADAPTER,
        "LLM",
        {
            "api_key": "sk-test",
            "model": "gpt-4o",
            "api_base": "https://api.openai.com/v1",
        },
    )
    embed_id = create_adapter(
        _EMBED_ADAPTER,
        "EMBEDDING",
        {"api_key": "sk-test", "model": "text-embedding-3-small"},
    )
    vdb_id = create_adapter(_VECTORDB_ADAPTER, "VECTOR_DB", {"wait_time": 0})
    x2t_id = create_adapter(_X2TEXT_ADAPTER, "X2TEXT", {"wait_time": 0})

    resp = _post(
        s,
        f"{prefix}/prompt-studio/",
        json={"tool_name": f"e2e-{sfx}", "description": "e2e execute", "author": "e2e"},
    )
    assert resp.status_code == 201, f"prompt-studio project: {resp.text}"
    tool_id = resp.json()["tool_id"]

    # Patch the auto-created default profile; a second one would break export.
    resp = s.get(f"{prefix}/prompt-studio/prompt-studio-profile/{tool_id}/", timeout=30)
    resp.raise_for_status()
    profile_id = next(p["profile_id"] for p in resp.json() if p.get("is_default"))
    resp = _patch(
        s,
        f"{prefix}/prompt-studio/profile-manager/{profile_id}/",
        json={
            "llm": llm_id,
            "embedding_model": embed_id,
            "vector_store": vdb_id,
            "x2text": x2t_id,
            "chunk_size": 0,
            "chunk_overlap": 0,
        },
    )
    assert resp.status_code == 200, f"profile patch: {resp.text}"

    prompt_key = "answer"
    resp = _post(
        s,
        f"{prefix}/prompt-studio/prompt-studio-prompt/{tool_id}/",
        json={
            "tool_id": tool_id,
            "prompt_key": prompt_key,
            "prompt": "What is this document about?",
            "prompt_type": "PROMPT",
            # text keeps the answer the raw completion; the structured types are
            # re-serialised on the way out and would not match the mock verbatim.
            "enforce_type": "text",
            "sequence_number": 1,
            "active": True,
            "profile_manager": profile_id,
        },
    )
    assert resp.status_code == 201, f"add prompt: {resp.text}"
    prompt_id = resp.json()["prompt_id"]

    resp = _post(
        s,
        f"{prefix}/prompt-studio/export/{tool_id}",
        json={"force_export": True, "is_shared_with_org": True},
    )
    assert resp.status_code == 200, f"export: {resp.text}"
    # The filter arg is mandatory: without one the view returns no queryset.
    resp = s.get(
        f"{prefix}/prompt-studio/registry/", params={"custom_tool": tool_id}, timeout=30
    )
    resp.raise_for_status()
    regs = resp.json()
    reg_list = regs if isinstance(regs, list) else regs.get("results", [])
    assert reg_list, f"registry empty for tool {tool_id}"
    prompt_registry_id = reg_list[0]["prompt_registry_id"]

    resp = _post(s, f"{prefix}/workflow/", json={"workflow_name": f"e2e-wf-{sfx}"})
    assert resp.status_code == 201, f"create workflow: {resp.text}"
    workflow_id = resp.json()["id"]

    resp = s.get(
        f"{prefix}/workflow/endpoint/", params={"workflow": workflow_id}, timeout=30
    )
    resp.raise_for_status()
    eps = resp.json()
    eps = eps if isinstance(eps, list) else eps.get("results", [])
    patched = 0
    for endpoint in eps:
        if endpoint.get("workflow") == workflow_id:
            resp = _patch(
                s,
                f"{prefix}/workflow/endpoint/{endpoint['id']}/",
                json={"connection_type": "API"},
            )
            assert resp.status_code == 200, f"patch endpoint: {resp.text}"
            patched += 1
    # Fail here, not in a downstream execute test, if no endpoint matched.
    assert patched, f"no endpoint matched workflow_id={workflow_id}: {eps}"

    resp = _post(
        s,
        f"{prefix}/tool_instance/",
        json={"workflow_id": workflow_id, "tool_id": prompt_registry_id},
    )
    assert resp.status_code == 201, f"attach tool: {resp.text}"

    return ProvisionedWorkflow(
        session=s,
        base=base,
        prefix=prefix,
        org_id=org_id,
        workflow_id=workflow_id,
        tool_id=tool_id,
        prompt_registry_id=prompt_registry_id,
        profile_id=profile_id,
        prompt_id=prompt_id,
        prompt_key=prompt_key,
    )
