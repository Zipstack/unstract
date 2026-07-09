"""E2E fixtures: a session-scoped ``platform`` fixture that yields URLs/creds.

The rig brings the platform up at the *rig* level (once per ``run`` invocation,
not per pytest session) and propagates URLs into pytest via env vars. This
conftest reads those env vars; if they're missing, e2e tests are skipped with
a clear message rather than spuriously failing.
"""

from __future__ import annotations

import os

import pytest
import requests

from tests.rig.runtime import PlatformEndpoints


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
    org_id = orgs.json()["organizations"][0]["id"]
    resp = session.post(
        f"{base}/api/v1/organization/{org_id}/set",
        headers={"X-CSRFToken": session.cookies.get("csrftoken", "")},
        timeout=10,
    )
    resp.raise_for_status()
    return session
