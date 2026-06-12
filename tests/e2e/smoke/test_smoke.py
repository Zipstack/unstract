"""Single placeholder e2e smoke test.

Exercises the rig's e2e plumbing end-to-end (platform up → URL injection →
pytest discovery → result aggregation → platform down) without depending on
auth state or seed data. Real workflow + API-deployment tests will land in
adjacent files (tests/e2e/workflows/, tests/e2e/api_deployment/, ...).
"""

from __future__ import annotations

import os

import pytest
import requests

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


def test_backend_health(platform) -> None:
    response = requests.get(f"{platform.backend_url.rstrip('/')}/health/", timeout=10)
    assert response.status_code < 500, f"backend /health returned {response.status_code}"
