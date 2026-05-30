"""Self-tests for runtime types.

Covers the small but load-bearing invariants on ``InfraEndpoints`` /
``PlatformEndpoints`` — the runtime drivers themselves (compose, testcontainers)
need a real Docker daemon to exercise and live outside this unit-rig group.
"""

from __future__ import annotations

import pytest

from tests.rig.runtime import InfraEndpoints, PlatformEndpoints


def test_infra_endpoints_rejects_partial_redis_pair() -> None:
    """Host without port (or vice versa) silently lands in downstream
    config if not rejected here. ``__post_init__`` is the only guard.
    """
    with pytest.raises(ValueError, match="redis_host and redis_port"):
        InfraEndpoints(redis_host="localhost")
    with pytest.raises(ValueError, match="redis_host and redis_port"):
        InfraEndpoints(redis_port=6379)


def test_infra_endpoints_rejects_partial_rabbitmq_pair() -> None:
    with pytest.raises(ValueError, match="rabbitmq_host and rabbitmq_port"):
        InfraEndpoints(rabbitmq_host="localhost")
    with pytest.raises(ValueError, match="rabbitmq_host and rabbitmq_port"):
        InfraEndpoints(rabbitmq_port=5672)


def test_infra_endpoints_allows_fully_specified_pairs() -> None:
    """Both halves of each pair present is the canonical happy path."""
    endpoints = InfraEndpoints(
        redis_host="localhost",
        redis_port=6379,
        rabbitmq_host="localhost",
        rabbitmq_port=5672,
    )
    assert endpoints.redis_host == "localhost"
    assert endpoints.redis_port == 6379


def test_infra_endpoints_allows_all_none() -> None:
    """No infra specified is also valid — that's the LocalRuntime case."""
    InfraEndpoints()  # must not raise


def test_platform_endpoints_from_env_uses_defaults(monkeypatch) -> None:
    """``from_env`` is the canonical constructor; an empty env should land
    on the dev-compose defaults rather than crash or produce empty URLs.
    """
    for key in (
        "UNSTRACT_BACKEND_URL",
        "UNSTRACT_PROMPT_SERVICE_URL",
        "UNSTRACT_PLATFORM_SERVICE_URL",
        "UNSTRACT_RUNNER_URL",
        "UNSTRACT_X2TEXT_URL",
    ):
        monkeypatch.delenv(key, raising=False)
    endpoints = PlatformEndpoints.from_env()
    assert endpoints.backend_url == "http://localhost:8000"
    assert endpoints.runner_url == "http://localhost:5002"
    assert endpoints.admin_user == "unstract"
