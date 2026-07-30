"""E2E: co-owner management endpoints over real HTTP (owner-side).

Proves the co-owner surface is reachable, CSRF-protected, org-scoped, and enforces
validation + the last-owner guard end-to-end against the running platform, using
the shared mock-login ``authed_session``.

Cross-user *grant* (a second real HTTP user logging in and seeing the shared
resource) is covered in-process by ``backend/permissions/tests/test_owner_management.py``
— OSS mock-login authenticates a single user, so a second HTTP session is not
available in this harness.
"""

from __future__ import annotations

import secrets

import pytest
import requests

from tests.rig.runtime import PlatformEndpoints

pytestmark = [pytest.mark.e2e, pytest.mark.critical]


def _csrf(session: requests.Session) -> dict[str, str]:
    """Django double-submit CSRF header echoing the session's csrftoken cookie."""
    return {"X-CSRFToken": session.cookies.get("csrftoken", "")}


def _tenant_prefix(platform: PlatformEndpoints, session: requests.Session) -> str:
    """Return ``.../api/v1/unstract/{org_id}`` for the session's active org."""
    base = platform.backend_url.rstrip("/")
    orgs = session.get(f"{base}/api/v1/organization", timeout=10)
    orgs.raise_for_status()
    org_id = orgs.json()["organizations"][0]["id"]
    return f"{base}/api/v1/unstract/{org_id}"


def _co_owners(session: requests.Session, prefix: str, wf_id: str) -> list[dict]:
    resp = session.get(f"{prefix}/workflow/{wf_id}/users/", timeout=10)
    resp.raise_for_status()
    return resp.json().get("co_owners", [])


@pytest.fixture
def workflow(platform: PlatformEndpoints, authed_session: requests.Session):
    """Create a throwaway workflow owned by the logged-in user; delete on teardown."""
    prefix = _tenant_prefix(platform, authed_session)
    resp = authed_session.post(
        f"{prefix}/workflow/",
        json={"workflow_name": f"e2e-coowner-{secrets.token_hex(4)}"},
        headers=_csrf(authed_session),
        timeout=30,
    )
    resp.raise_for_status()
    wf_id = resp.json()["id"]
    yield prefix, wf_id
    authed_session.delete(
        f"{prefix}/workflow/{wf_id}/", headers=_csrf(authed_session), timeout=30
    )


@pytest.mark.critical_path("co-owner-manage")
def test_creator_owns_and_last_owner_guard(
    platform: PlatformEndpoints,
    authed_session: requests.Session,
    workflow: tuple[str, str],
) -> None:
    prefix, wf_id = workflow

    # The creator is auto-seeded as the sole owner, surfaced over HTTP.
    owners = _co_owners(authed_session, prefix, wf_id)
    assert len(owners) == 1, f"expected creator as sole owner, got {owners}"
    owner_id = owners[0]["id"]

    # Adding a non-member is rejected — endpoint reachable + input validated.
    add = authed_session.post(
        f"{prefix}/workflow/{wf_id}/owners/",
        json={"user_id": 999_999_999},
        headers=_csrf(authed_session),
        timeout=10,
    )
    assert add.status_code == 400, f"non-member add should 400, got {add.status_code}: {add.text}"

    # Last-owner guard: removing the sole owner is refused; the owner survives.
    guard = authed_session.delete(
        f"{prefix}/workflow/{wf_id}/owners/{owner_id}/",
        headers=_csrf(authed_session),
        timeout=10,
    )
    assert guard.status_code == 400, (
        f"last-owner removal should 400, got {guard.status_code}: {guard.text}"
    )
    assert len(_co_owners(authed_session, prefix, wf_id)) == 1
