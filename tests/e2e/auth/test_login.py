"""E2E: OSS mock-login over real HTTP (covers the ``auth-login`` critical path).

Self-contained on purpose — it builds its own session because it is the thing
under test. Other e2e tests should take the shared ``authed_session`` fixture.
"""

from __future__ import annotations

import pytest
import requests

from tests.rig.runtime import PlatformEndpoints

pytestmark = [pytest.mark.e2e, pytest.mark.critical]


@pytest.mark.critical_path("auth-login")
def test_login_sets_usable_session(platform: PlatformEndpoints) -> None:
    base = platform.backend_url.rstrip("/")
    session = requests.Session()

    resp = session.post(
        f"{base}/api/v1/login",
        data={"username": platform.admin_user, "password": platform.admin_password},
        allow_redirects=False,
        timeout=10,
    )
    assert resp.status_code == 302, (
        f"expected 302 redirect on login, got {resp.status_code} "
        "(200 with HTML means bad credentials)"
    )
    assert session.cookies.get("sessionid"), "login did not set a sessionid cookie"

    # The cookie is only meaningful if it authenticates a follow-up request.
    who = session.get(f"{base}/api/v1/session", timeout=10)
    assert who.status_code in (200, 201), f"/api/v1/session returned {who.status_code}"
    assert who.json().get("email"), f"/api/v1/session returned no user: {who.text}"


def test_login_rejects_bad_credentials(platform: PlatformEndpoints) -> None:
    base = platform.backend_url.rstrip("/")
    resp = requests.Session().post(
        f"{base}/api/v1/login",
        data={"username": "unstract", "password": "wrong-password"},
        allow_redirects=False,
        timeout=10,
    )
    # Bad creds re-render the login page (200 HTML), never a 302 redirect.
    assert resp.status_code != 302, "bad credentials should not yield a login redirect"
