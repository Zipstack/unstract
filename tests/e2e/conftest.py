"""E2E fixtures: a session-scoped ``platform`` fixture that yields URLs/creds.

The rig brings the platform up at the *rig* level (once per ``run`` invocation,
not per pytest session) and propagates URLs into pytest via env vars. This
conftest reads those env vars; if they're missing, e2e tests are skipped with
a clear message rather than spuriously failing.
"""

from __future__ import annotations

import os

import pytest

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
