"""Self-tests for runtime types.

Covers the small but load-bearing invariants on ``InfraEndpoints`` /
``PlatformEndpoints`` — the runtime drivers themselves (compose, testcontainers)
need a real Docker daemon to exercise and live outside this unit-rig group.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

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


# ── Injection seams: extra compose overlays + pluggable login provider ───────

from tests.e2e.conftest import _load_login_provider, _oss_form_login  # noqa: E402
from tests.rig.runtime import EXTRA_COMPOSE_ENV, _extra_compose_files  # noqa: E402


def test_extra_compose_files_empty_when_unset(monkeypatch) -> None:
    monkeypatch.delenv(EXTRA_COMPOSE_ENV, raising=False)
    assert _extra_compose_files() == []


def test_extra_compose_files_reads_existing_paths(monkeypatch, tmp_path) -> None:
    a, b = tmp_path / "a.yaml", tmp_path / "b.yaml"
    a.write_text("services: {}")
    b.write_text("services: {}")
    import os as _os

    monkeypatch.setenv(EXTRA_COMPOSE_ENV, _os.pathsep.join([str(a), str(b)]))
    assert _extra_compose_files() == [a, b]


def test_extra_compose_files_rejects_missing(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv(EXTRA_COMPOSE_ENV, str(tmp_path / "nope.yaml"))
    with pytest.raises(ValueError, match=EXTRA_COMPOSE_ENV):
        _extra_compose_files()


_OVERLAY_YAML = "services:\n  mock:\n    image: mock:latest\n"


def _up_then_delete_overlay(monkeypatch, tmp_path, *, snapshot_ok: bool):
    """up() with an extra overlay, then delete it — the mid-run removal case.

    Returns (runtime_module, docker_commands, subprocess_calls).
    """
    from tests.rig import runtime as rt

    extra = tmp_path / "extra.yaml"
    extra.write_text(_OVERLAY_YAML)
    monkeypatch.setenv(EXTRA_COMPOSE_ENV, str(extra))
    monkeypatch.setattr(rt.shutil, "which", lambda _: "/usr/bin/docker")
    monkeypatch.setattr(rt, "_wait_ready", lambda *_a, **_k: None)

    commands: list[list[str]] = []
    monkeypatch.setattr(rt, "_run", lambda cmd, **_k: commands.append(cmd))

    # Stands in for `docker compose config` (and, after down, `docker volume`).
    calls: list[list[str]] = []

    def fake_run(cmd, *_a, **_k):
        calls.append(cmd)
        return subprocess.CompletedProcess(
            cmd,
            0 if snapshot_ok else 1,
            stdout=_OVERLAY_YAML if snapshot_ok else "",
            stderr="" if snapshot_ok else "boom",
        )

    monkeypatch.setattr(rt.subprocess, "run", fake_run)

    compose = rt.ComposeRuntime()
    compose.up()
    assert str(extra) in commands[0]

    extra.unlink()
    monkeypatch.setattr(compose, "_dump_logs", lambda _files: None)
    compose.down()
    return rt, extra, commands, calls


def test_down_uses_config_snapshot_after_overlay_removed(monkeypatch, tmp_path) -> None:
    """The snapshot keeps the removed overlay's resources in scope for down -v."""
    _rt, _extra, commands, _calls = _up_then_delete_overlay(
        monkeypatch, tmp_path, snapshot_ok=True
    )

    down_cmd = commands[-1]
    assert down_cmd[-3:] == ["down", "-v", "--remove-orphans"]
    snapshot = Path(down_cmd[down_cmd.index("-f") + 1])
    assert snapshot.is_file()
    assert "mock:latest" in snapshot.read_text()


def test_down_sweeps_volumes_when_snapshot_failed(monkeypatch, tmp_path) -> None:
    """Without a snapshot the file is dropped, so volumes go by project label."""
    rt, extra, commands, calls = _up_then_delete_overlay(
        monkeypatch, tmp_path, snapshot_ok=False
    )

    down_cmd = commands[-1]
    assert down_cmd[-3:] == ["down", "-v", "--remove-orphans"]
    assert str(extra) not in down_cmd
    assert str(rt.BASE_COMPOSE) in down_cmd
    # Teardown can no longer see what the overlay declared, so it falls back to
    # the label every compose-created volume carries.
    assert any(
        c[:3] == ["docker", "volume", "ls"]
        and any("com.docker.compose.project=" in part for part in c)
        for c in calls
    ), calls


def test_login_provider_defaults_to_oss(monkeypatch) -> None:
    monkeypatch.delenv("UNSTRACT_E2E_LOGIN_PROVIDER", raising=False)
    assert _load_login_provider() is _oss_form_login


def test_login_provider_resolves_dotted_path(monkeypatch) -> None:
    monkeypatch.setenv("UNSTRACT_E2E_LOGIN_PROVIDER", "json.loads")
    import json

    assert _load_login_provider() is json.loads


def test_login_provider_rejects_bare_name(monkeypatch) -> None:
    monkeypatch.setenv("UNSTRACT_E2E_LOGIN_PROVIDER", "loads")
    with pytest.raises(ValueError, match=r"module\.func"):
        _load_login_provider()


def test_login_provider_rejects_trailing_dot(monkeypatch) -> None:
    monkeypatch.setenv("UNSTRACT_E2E_LOGIN_PROVIDER", "json.")
    with pytest.raises(ValueError, match=r"module\.func"):
        _load_login_provider()


def test_login_provider_rejects_non_callable(monkeypatch) -> None:
    monkeypatch.setenv("UNSTRACT_E2E_LOGIN_PROVIDER", "json.__name__")
    with pytest.raises(ValueError, match="callable"):
        _load_login_provider()
