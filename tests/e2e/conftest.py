"""E2E fixtures: a session-scoped ``platform`` fixture that yields URLs/creds.

The rig brings the platform up at the *rig* level (once per ``run`` invocation,
not per pytest session) and propagates URLs into pytest via env vars. This
conftest reads those env vars; if they're missing, e2e tests are skipped with
a clear message rather than spuriously failing.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

import pytest
import requests


@dataclass(frozen=True)
class PlatformAccess:
    backend_url: str
    prompt_service_url: str
    platform_service_url: str
    runner_url: str
    admin_user: str
    admin_password: str

    def session(self) -> requests.Session:
        return requests.Session()


def _read_env() -> PlatformAccess | None:
    required = ("UNSTRACT_BACKEND_URL",)
    if not all(os.environ.get(k) for k in required):
        return None
    return PlatformAccess(
        backend_url=os.environ["UNSTRACT_BACKEND_URL"],
        prompt_service_url=os.environ.get("UNSTRACT_PROMPT_SERVICE_URL", ""),
        platform_service_url=os.environ.get("UNSTRACT_PLATFORM_SERVICE_URL", ""),
        runner_url=os.environ.get("UNSTRACT_RUNNER_URL", ""),
        admin_user=os.environ.get("UNSTRACT_ADMIN_USER", "unstract"),
        admin_password=os.environ.get("UNSTRACT_ADMIN_PASSWORD", "unstract"),
    )


@pytest.fixture(scope="session")
def platform() -> PlatformAccess:
    access = _read_env()
    if access is None:
        pytest.skip(
            "platform URLs not set in env; run via `python -m tests.rig run --tier e2e ...` "
            "or export UNSTRACT_BACKEND_URL (etc.) yourself."
        )
    return access
