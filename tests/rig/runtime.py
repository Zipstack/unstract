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
from pathlib import Path
from typing import ClassVar, Protocol

from tests.rig.groups import REPO_ROOT

log = logging.getLogger(__name__)

COMPOSE_OVERLAY = REPO_ROOT / "tests" / "compose" / "docker-compose.test.yaml"
BASE_COMPOSE = REPO_ROOT / "docker" / "docker-compose.yaml"

# Extra compose overlays a downstream repo can layer on (e.g. a cloud repo
# adding an auth mock or an LLM proxy it copied into this tree). Same contract
# as UNSTRACT_RIG_EXTRA_MANIFESTS: os.pathsep-separated, relative to REPO_ROOT.
EXTRA_COMPOSE_ENV = "UNSTRACT_RIG_EXTRA_COMPOSE"


def _extra_compose_files() -> list[Path]:
    raw = os.environ.get(EXTRA_COMPOSE_ENV, "").strip()
    if not raw:
        return []
    paths: list[Path] = []
    for entry in filter(None, (e.strip() for e in raw.split(os.pathsep))):
        p = Path(entry)
        p = p if p.is_absolute() else REPO_ROOT / p
        if not p.is_file():
            raise ValueError(
                f"{EXTRA_COMPOSE_ENV}: {entry!r} is not a file (resolved to {p})"
            )
        paths.append(p)
    return paths


def _compose_file_args() -> list[str]:
    """The ``-f`` args for compose: base, the test overlay, then any extras."""
    args = ["-f", str(BASE_COMPOSE)]
    if COMPOSE_OVERLAY.exists():
        args += ["-f", str(COMPOSE_OVERLAY)]
    for extra in _extra_compose_files():
        args += ["-f", str(extra)]
    return args


def _drop_missing_files(args: list[str]) -> list[str]:
    """Keep only the ``-f <path>`` pairs still on disk.

    A path compose can't read makes it refuse the whole command, so a file that
    vanished mid-run would block teardown entirely rather than cost one overlay.
    """
    kept: list[str] = []
    for flag, path in zip(args[::2], args[1::2], strict=True):
        if Path(path).is_file():
            kept += [flag, path]
        else:
            log.warning("compose file %s vanished; excluding it from teardown", path)
    return kept

# Shared by the workers and the tests, so the exact completion is assertable.
LLM_MOCK_RESPONSE_ENV = "UNSTRACT_LLM_MOCK_RESPONSE"
DEFAULT_LLM_MOCK_RESPONSE = "MOCK_LLM_OK"


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
    minio_access_key: str | None = None
    minio_secret_key: str | None = None

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
    # Served on its own origin, not behind the backend: compose publishes the
    # frontend on :3000 and the backend on :8000. Browser-driven groups need
    # this one — pointing them at `backend_url` lands on the API instead.
    frontend_url: str = "http://localhost:3000"
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
            frontend_url=os.environ.get(
                "UNSTRACT_FRONTEND_URL", "http://localhost:3000"
            ),
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
        # Captured at up() so down() tears down the exact same project even if
        # UNSTRACT_RIG_EXTRA_COMPOSE changes or an overlay is removed mid-run.
        self._compose_files: list[str] | None = None

    def up(self) -> PlatformEndpoints:
        if shutil.which("docker") is None:
            raise RuntimeError("ComposeRuntime requires the `docker` CLI on PATH")
        files = _compose_file_args()
        _run(
            ["docker", "compose", "-p", self.project_name, *files, "up", "-d", "--wait"]
        )
        self._compose_files = self._snapshot_config(files) or files
        endpoints = PlatformEndpoints.from_env()
        _wait_ready(endpoints)
        return endpoints

    def down(self) -> None:
        if shutil.which("docker") is None:
            return
        files = self._compose_files
        if files is None:
            # down() without a prior up() (e.g. pre-run cleanup): best-effort,
            # never let a since-removed overlay abort teardown.
            try:
                files = _compose_file_args()
            except ValueError:
                files = ["-f", str(BASE_COMPOSE)]
        # No-op on the snapshot, which is a single file we wrote ourselves; this
        # covers the raw-path cases (snapshot unavailable, or no prior up()).
        readable = _drop_missing_files(files)
        self._dump_logs(readable)
        _run(
            [
                "docker",
                "compose",
                "-p",
                self.project_name,
                *readable,
                "down",
                "-v",
                "--remove-orphans",
            ],
            check=False,
        )
        if len(readable) != len(files):
            # `down -v` only removes volumes it can still see declared, so a
            # dropped file takes its volumes out of scope. The project label is
            # on them regardless of which file declared them.
            self._remove_project_volumes()

    def _remove_project_volumes(self) -> None:
        try:
            listed = subprocess.run(  # noqa: S603
                [
                    "docker",
                    "volume",
                    "ls",
                    "-q",
                    "--filter",
                    f"label=com.docker.compose.project={self.project_name}",
                ],
                capture_output=True,
                text=True,
                check=False,
            )
            names = listed.stdout.split()
            if names:
                subprocess.run(  # noqa: S603
                    ["docker", "volume", "rm", "-f", *names],
                    capture_output=True,
                    check=False,
                )
        except OSError as exc:
            log.warning("Could not remove leftover project volumes: %s", exc)

    def _snapshot_config(self, files: list[str]) -> list[str] | None:
        """Freeze the merged compose config so teardown never rereads the sources.

        The overlay files can move or be cleaned up between up() and down();
        a resolved snapshot keeps every service, network and volume the project
        owns visible to `down -v`, not just the ones still on disk. Returns None
        when the snapshot can't be written, leaving the caller on raw paths.
        """
        target = REPO_ROOT / "reports" / f"compose-config-{self.project_name}.yaml"
        try:
            completed = subprocess.run(  # noqa: S603
                ["docker", "compose", "-p", self.project_name, *files, "config"],
                capture_output=True,
                text=True,
                check=False,
            )
            if completed.returncode != 0 or not completed.stdout.strip():
                log.warning("compose config snapshot failed: %s", completed.stderr)
                return None
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(completed.stdout)
        except OSError as exc:
            log.warning("Could not write compose config snapshot: %s", exc)
            return None
        return ["-f", str(target)]

    def _dump_logs(self, files: list[str]) -> None:
        """Capture service logs while the containers still exist.

        A failing e2e is usually explained by a worker log, and `down -v` is the
        last thing that can read them -- a CI step afterwards gets an empty file.
        """
        target = REPO_ROOT / "reports" / "docker-compose-logs.txt"
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            completed = subprocess.run(  # noqa: S603
                ["docker", "compose", "-p", self.project_name, *files, "logs", "--no-color"],
                capture_output=True,
                text=True,
                check=False,
            )
            target.write_text(completed.stdout)
        except OSError as exc:
            log.warning("Could not capture compose logs: %s", exc)


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
                    # Default testcontainers MinIO root creds; surfaced so the
                    # rig can inject them into connector integration tests.
                    minio_access_key=getattr(minio, "access_key", "minioadmin"),
                    minio_secret_key=getattr(minio, "secret_key", "minioadmin"),
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


def health_targets(endpoints: PlatformEndpoints) -> list[tuple[str, str]]:
    """(service name, health URL) for every HTTP service the e2e tier depends on.

    Single source of truth for the readiness probe and the e2e smoke test.
    Paths are service-specific: x2text mounts health under a blueprint prefix,
    and there is no standalone prompt-service (folded into workers). The runner
    is intentionally absent — container-based execution is being retired in
    favour of in-worker execution, so e2e must not depend on it being up.

    The frontend probes ``/`` rather than a health path: it is nginx serving a
    static SPA, so there is no health endpoint to hit and index.html answering
    200 is exactly the liveness signal. Without it the browser-driven ``ui``
    group would sail past ``_wait_ready`` with nothing serving on :3000 and
    then skip itself, reporting success while never opening the app.
    """
    return [
        ("backend", endpoints.backend_url.rstrip("/") + "/health"),
        ("platform-service", endpoints.platform_service_url.rstrip("/") + "/health"),
        ("x2text-service", endpoints.x2text_url.rstrip("/") + "/api/v1/x2text/health"),
        ("frontend", endpoints.frontend_url.rstrip("/") + "/"),
    ]


def _wait_ready(endpoints: PlatformEndpoints, *, timeout_seconds: int = 300) -> None:
    """Poll each service's health endpoint until all respond or timeout.

    Skips probing if ``requests`` isn't importable — the rig may run on a bare
    interpreter just to list groups. The e2e path always has requests installed.
    """
    try:
        import requests
    except ImportError:
        log.warning("`requests` not installed; skipping platform readiness probe")
        return

    targets = [url for _, url in health_targets(endpoints)]
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
