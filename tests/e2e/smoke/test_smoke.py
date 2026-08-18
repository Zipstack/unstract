"""E2E smoke gate: rig plumbing is wired and every service is up.

Depends on no auth state or seed data, so it isolates "is the platform
healthy" from feature tests. The other e2e groups depend on this one, so a
red smoke run stops them before they produce confusing failures.
"""

from __future__ import annotations

import os

import pytest
import requests

from tests.rig.runtime import PlatformEndpoints, health_targets

pytestmark = [pytest.mark.e2e, pytest.mark.critical]


def test_rig_session_sentinel_present() -> None:
    """The rig stamps ``UNSTRACT_RIG_SESSION_ID`` into every group's env.
    Its absence means this test ran outside the rig (or with stale shell env
    that didn't get the sentinel), in which case the backend URL is suspect.
    """
    assert os.environ.get("UNSTRACT_RIG_SESSION_ID"), (
        "UNSTRACT_RIG_SESSION_ID not set — either this test wasn't launched "
        "via `python -m tests.rig run`, or the rig failed to propagate the "
        "sentinel. Re-run via the rig; if launched manually, set the env var "
        "yourself to assert acknowledgement that you've audited the platform "
        "URLs in your shell."
    )


def test_all_services_healthy(platform: PlatformEndpoints) -> None:
    """Every HTTP service in the stack answers its health endpoint with 200.

    This is the gate the rest of the e2e tier depends on — a half-booted stack
    should fail here loudly rather than surface as confusing downstream errors.
    """
    failures = []
    for name, url in health_targets(platform):
        try:
            resp = requests.get(url, timeout=10)
            if resp.status_code != 200:
                failures.append(f"{name} ({url}) -> HTTP {resp.status_code}")
        except requests.RequestException as exc:
            failures.append(f"{name} ({url}) -> {exc}")
    assert not failures, "unhealthy services: " + "; ".join(failures)
