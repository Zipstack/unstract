"""Platform runtime drivers for e2e tests.

Two strategies share a small protocol so the rig can pick by env/CLI flag:

  ComposeRuntime          — CI default. Reuses docker/docker-compose.yaml +
                            tests/compose/docker-compose.test.yaml overlay.
  TestcontainersRuntime   — local default. Spins up Postgres/Redis/RabbitMQ/MinIO
                            via testcontainers; backend/prompt/platform/runner
                            are NOT auto-launched today (stub — see class docstring).

A third mode, ``LocalRuntime``, assumes the developer already has services up
(e.g. via ``run-platform.sh``) and only collects their URLs from env. Useful
when iterating quickly.

The driver exposes URLs via ``PlatformEndpoints`` and is consumed by the
``platform`` pytest fixture in ``tests/e2e/conftest.py``.
"""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
import time
from dataclasses import dataclass, field
from typing import ClassVar, Protocol

from tests.rig.groups import REPO_ROOT

log = logging.getLogger(__name__)

COMPOSE_OVERLAY = REPO_ROOT / "tests" / "compose" / "docker-compose.test.yaml"
BASE_COMPOSE = REPO_ROOT / "docker" / "docker-compose.yaml"


@dataclass(frozen=True)
class InfraEndpoints:
    """Named handles for stateful infra started by ``TestcontainersRuntime``.

    For fields that come in host/port pairs (redis, rabbitmq), both must be
    set together — ``__post_init__`` enforces this so a partial spec doesn't
    silently land in downstream config. Postgres collapses host+port+creds
    into a single URL string, and MinIO uses a combined ``host:port``
    endpoint, so no pairing applies to those.
    """

    postgres_url: str | None = None
    redis_host: str | None = None
    redis_port: int | None = None
    rabbitmq_host: str | None = None
    rabbitmq_port: int | None = None
    minio_endpoint: str | None = None

    def __post_init__(self) -> None:
        for host, port, label in (
            (self.redis_host, self.redis_port, "redis"),
            (self.rabbitmq_host, self.rabbitmq_port, "rabbitmq"),
        ):
            if (host is None) != (port is None):
                raise ValueError(
                    f"InfraEndpoints: {label}_host and {label}_port must be "
                    f"set together (got host={host!r}, port={port!r})"
                )


@dataclass(frozen=True)
class PlatformEndpoints:
    backend_url: str
    prompt_service_url: str
    platform_service_url: str
    runner_url: str
    x2text_url: str
    admin_user: str = "unstract"
    admin_password: str = "unstract"
    infra: InfraEndpoints = field(default_factory=InfraEndpoints)

    @classmethod
    def from_env(cls, *, infra: InfraEndpoints | None = None) -> PlatformEndpoints:
        """Build a ``PlatformEndpoints`` from ``UNSTRACT_*`` env vars.

        Used by every runtime so the lookup logic stays single-sourced.
        Defaults match the dev compose stack at ``docker/docker-compose.yaml``.
        """
        return cls(
            backend_url=os.environ.get("UNSTRACT_BACKEND_URL", "http://localhost:8000"),
            prompt_service_url=os.environ.get(
                "UNSTRACT_PROMPT_SERVICE_URL", "http://localhost:3003"
            ),
            platform_service_url=os.environ.get(
                "UNSTRACT_PLATFORM_SERVICE_URL", "http://localhost:3001"
            ),
            runner_url=os.environ.get("UNSTRACT_RUNNER_URL", "http://localhost:5002"),
            x2text_url=os.environ.get("UNSTRACT_X2TEXT_URL", "http://localhost:3004"),
            admin_user=os.environ.get("UNSTRACT_ADMIN_USER", "unstract"),
            admin_password=os.environ.get("UNSTRACT_ADMIN_PASSWORD", "unstract"),
            infra=infra or InfraEndpoints(),
        )


class PlatformRuntime(Protocol):
    name: ClassVar[str]

    def up(self) -> PlatformEndpoints: ...
    def down(self) -> None: ...


class LocalRuntime:
    """Assume a developer-managed stack; just collect endpoints from env."""

    name: ClassVar[str] = "local"

    def up(self) -> PlatformEndpoints:
        return PlatformEndpoints.from_env()

    def down(self) -> None:
        return None


class ComposeRuntime:
    """Bring the platform up via docker compose with a test overlay."""

    name: ClassVar[str] = "compose"

    def __init__(self, *, project_name: str = "unstract-test") -> None:
        self.project_name = project_name

    def up(self) -> PlatformEndpoints:
        if shutil.which("docker") is None:
            raise RuntimeError("ComposeRuntime requires the `docker` CLI on PATH")
        files = ["-f", str(BASE_COMPOSE)]
        if COMPOSE_OVERLAY.exists():
            files += ["-f", str(COMPOSE_OVERLAY)]
        _run(["docker", "compose", "-p", self.project_name, *files, "up", "-d", "--wait"])
        endpoints = PlatformEndpoints.from_env()
        _wait_ready(endpoints)
        return endpoints

    def down(self) -> None:
        if shutil.which("docker") is None:
            return
        files = ["-f", str(BASE_COMPOSE)]
        if COMPOSE_OVERLAY.exists():
            files += ["-f", str(COMPOSE_OVERLAY)]
        _run(
            [
                "docker",
                "compose",
                "-p",
                self.project_name,
                *files,
                "down",
                "-v",
                "--remove-orphans",
            ],
            check=False,
        )


class TestcontainersRuntime:
    """Spin up stateful infra via testcontainers; services run locally.

    This is a stub today: it stands up Postgres/Redis/RabbitMQ/MinIO so that
    ``unit-backend`` and ``integration-*`` groups can run, but does NOT
    auto-launch backend/prompt-service/etc. as subprocesses yet — that is
    layered on once each service has a tested test-mode entrypoint.

    For full platform e2e against testcontainers, use ``ComposeRuntime`` for now
    or set ``UNSTRACT_E2E_RUNTIME=local`` after running ``run-platform.sh``.
    """

    name: ClassVar[str] = "testcontainers"

    def __init__(self) -> None:
        self._stack: list[object] = []  # container handles for teardown

    def up(self) -> PlatformEndpoints:
        # Lazy import — list-groups/expand/validate don't need testcontainers.
        from testcontainers.minio import MinioContainer
        from testcontainers.postgres import PostgresContainer
        from testcontainers.rabbitmq import RabbitMqContainer
        from testcontainers.redis import RedisContainer

        # Construct InfraEndpoints + return inside the same try so the
        # __post_init__ invariant (host without port) is self-cleaning;
        # otherwise a partial spec leaks the four containers we just started.
        try:
            pg = PostgresContainer("pgvector/pgvector:pg15")
            pg.start()
            self._stack.append(pg)
            redis = RedisContainer("redis:7.2.3").start()
            self._stack.append(redis)
            rabbit = RabbitMqContainer("rabbitmq:3.13-management").start()
            self._stack.append(rabbit)
            minio = MinioContainer("minio/minio:latest").start()
            self._stack.append(minio)

            return PlatformEndpoints.from_env(
                infra=InfraEndpoints(
                    postgres_url=pg.get_connection_url(),
                    redis_host=redis.get_container_host_ip(),
                    redis_port=redis.get_exposed_port(6379),
                    rabbitmq_host=rabbit.get_container_host_ip(),
                    rabbitmq_port=rabbit.get_exposed_port(5672),
                    minio_endpoint=(
                        f"{minio.get_container_host_ip()}:{minio.get_exposed_port(9000)}"
                    ),
                ),
            )
        except Exception:
            self.down()
            raise

    def down(self) -> None:
        while self._stack:
            container = self._stack.pop()
            stop = getattr(container, "stop", None)
            if not callable(stop):
                continue
            try:
                stop()
            except Exception as exc:
                # Best-effort teardown. We still log because leaked containers
                # block the next run with port conflicts and the failure cause
                # is otherwise invisible.
                log.warning("testcontainers stop() failed for %r: %s", container, exc)


def pick_runtime(name: str | None) -> PlatformRuntime:
    """Resolve a runtime by name, falling back to env then default."""
    chosen = (
        name or os.environ.get("UNSTRACT_E2E_RUNTIME") or _default_runtime_name()
    ).lower()
    if chosen == "compose":
        return ComposeRuntime()
    if chosen == "testcontainers":
        return TestcontainersRuntime()
    if chosen == "local":
        return LocalRuntime()
    raise ValueError(
        f"unknown runtime: {chosen!r} (expected compose|testcontainers|local)"
    )


def _default_runtime_name() -> str:
    return "compose" if os.environ.get("CI") else "testcontainers"


def _run(cmd: list[str], *, check: bool = True) -> None:
    try:
        subprocess.run(cmd, check=check, cwd=REPO_ROOT)
    except subprocess.CalledProcessError as exc:
        # Re-raise with the command tail so CI logs name what failed.
        raise RuntimeError(
            f"command failed (exit {exc.returncode}): {' '.join(cmd)}"
        ) from exc


def _wait_ready(endpoints: PlatformEndpoints, *, timeout_seconds: int = 300) -> None:
    """Poll each service's /health endpoint until all respond or timeout.

    If ``requests`` isn't importable (e.g. running the rig on a bare interpreter
    just to list groups), readiness probing is skipped. That's safe because the
    only caller, ``ComposeRuntime.up``, is on the e2e path where requests is in
    the rig's deps; getting here without requests installed implies a broken
    install and the developer will surface it shortly.
    """
    try:
        import requests
    except ImportError:
        log.warning("`requests` not installed; skipping platform readiness probe")
        return

    targets = [
        endpoints.backend_url.rstrip("/") + "/health/",
        endpoints.prompt_service_url.rstrip("/") + "/health",
        endpoints.platform_service_url.rstrip("/") + "/health",
        endpoints.runner_url.rstrip("/") + "/health",
    ]
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        if all(_responds(t, requests) for t in targets):
            return
        time.sleep(2)
    raise TimeoutError(f"services not ready within {timeout_seconds}s: {targets}")


def _responds(url: str, requests_mod) -> bool:
    try:
        resp = requests_mod.get(url, timeout=2)
        return resp.status_code < 500
    except requests_mod.RequestException:
        return False
