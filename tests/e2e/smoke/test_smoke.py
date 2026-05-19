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


def test_backend_health(platform) -> None:
    # The rig is responsible for setting UNSTRACT_BACKEND_URL via the runtime
    # driver. If a stale value from the developer's shell leaked in, the test
    # could pass against the wrong stack — assert they match before hitting it.
    assert platform.backend_url == os.environ["UNSTRACT_BACKEND_URL"], (
        "platform fixture diverged from UNSTRACT_BACKEND_URL — rig wiring is "
        "broken or shell env leaked past the rig"
    )

    response = requests.get(f"{platform.backend_url.rstrip('/')}/health/", timeout=10)
    assert response.status_code < 500, f"backend /health returned {response.status_code}"
