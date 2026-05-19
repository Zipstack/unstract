"""Single placeholder e2e smoke test.

Exercises the rig's e2e plumbing end-to-end (platform bring-up → HTTP → tear-down)
without depending on auth state or seed data. Real workflow + API-deployment
tests will land in adjacent files (tests/e2e/workflows/, tests/e2e/api_deployment/, ...).
"""

from __future__ import annotations

import pytest
import requests

pytestmark = [pytest.mark.e2e, pytest.mark.critical]


def test_backend_health(platform) -> None:
    response = requests.get(f"{platform.backend_url.rstrip('/')}/health/", timeout=10)
    assert response.status_code < 500, f"backend /health returned {response.status_code}"
