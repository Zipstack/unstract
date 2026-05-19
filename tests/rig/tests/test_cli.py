"""Self-tests for the CLI's run-time wiring (scope_groups, teardown safety).

The bulk of the rig is tested via the manifest + evaluate + reporting helpers.
These tests exist for the parts of ``cmd_run`` that are hard to exercise from
pure unit tests — specifically, how it passes ``scope_groups`` through to
``evaluate`` and how it shields the in-flight exception from a teardown failure.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from tests.rig.runtime import PlatformEndpoints


def test_cmd_run_passes_scope_to_evaluate(tmp_path: Path, monkeypatch) -> None:
    """``cmd_run`` must pass the dep-expanded selection (not just runnable
    groups, not just groups_run_green) as ``scope_groups``. Without this
    plumbing the N2 fix has no effect — a future refactor that drops the
    kwarg, or swaps it for ``runnable``, would silently reintroduce
    cross-tier regression false positives.
    """
    manifest_yaml = (
        "version: 1\n"
        "groups:\n"
        "  unit-x:\n"
        "    tier: unit\n"
        "    paths: [x]\n"
        "    optional: true\n"
    )
    cp_yaml = "version: 1\npaths: []\n"
    (tmp_path / "groups.yaml").write_text(manifest_yaml)
    (tmp_path / "critical_paths.yaml").write_text(cp_yaml)

    # Redirect the rig's manifest paths to the tmp_path fixtures.
    import tests.rig.cli as cli_mod
    import tests.rig.critical_paths as cp_mod
    import tests.rig.groups as groups_mod

    monkeypatch.setattr(groups_mod, "DEFAULT_MANIFEST", tmp_path / "groups.yaml")
    monkeypatch.setattr(
        cp_mod, "DEFAULT_REGISTRY", tmp_path / "critical_paths.yaml"
    )

    # Spy on evaluate to capture scope_groups.
    captured: dict[str, Any] = {}
    real_evaluate = cp_mod.evaluate

    def spy_evaluate(*args, **kwargs):
        captured["scope_groups"] = kwargs.get("scope_groups")
        return real_evaluate(*args, **kwargs)

    monkeypatch.setattr(cli_mod.cp, "evaluate", spy_evaluate)

    # --dry-run avoids spawning subprocesses; the scope wiring runs regardless.
    args = cli_mod._build_parser().parse_args(
        [
            "run",
            "unit-x",
            "--dry-run",
            "--no-coverage",
            "--no-parallel",
            "--reports-dir",
            str(tmp_path / "reports"),
            "--baseline",
            str(tmp_path / "reports" / "previous-summary.json"),
        ]
    )
    exit_code = cli_mod.cmd_run(args)
    assert exit_code == 0
    assert captured["scope_groups"] == {"unit-x"}, (
        "cmd_run must pass the full dep-expanded selection as scope_groups; "
        f"got {captured.get('scope_groups')}"
    )


def test_cmd_run_teardown_failure_does_not_mask_up_failure(
    tmp_path: Path, monkeypatch
) -> None:
    """If a runtime's ``up()`` raises and ``down()`` ALSO raises in the
    finally, the rig must surface the original up() exception rather than
    swap it for the teardown error.
    """
    # The smoke group's paths/workdir must exist on disk because the validator
    # only skips path checks for `optional: true` groups, and an optional
    # group also gets filtered out by `_is_missing_placeholder` so the
    # runtime never gets called. Point it at this test file's directory.
    test_dir = Path(__file__).parent
    manifest_yaml = (
        "version: 1\n"
        "groups:\n"
        "  e2e-smoke:\n"
        "    tier: e2e\n"
        f"    workdir: {test_dir}\n"
        "    paths: [.]\n"
        "    requires_platform: true\n"
    )
    (tmp_path / "groups.yaml").write_text(manifest_yaml)
    (tmp_path / "critical_paths.yaml").write_text("version: 1\npaths: []\n")

    import tests.rig.cli as cli_mod
    import tests.rig.critical_paths as cp_mod
    import tests.rig.groups as groups_mod

    monkeypatch.setattr(groups_mod, "DEFAULT_MANIFEST", tmp_path / "groups.yaml")
    monkeypatch.setattr(
        cp_mod, "DEFAULT_REGISTRY", tmp_path / "critical_paths.yaml"
    )

    class BrokenRuntime:
        name = "broken"

        def up(self) -> PlatformEndpoints:
            raise RuntimeError("backend OOM during up")

        def down(self) -> None:
            raise RuntimeError("teardown bug")

    monkeypatch.setattr(cli_mod, "pick_runtime", lambda _: BrokenRuntime())

    args = cli_mod._build_parser().parse_args(
        [
            "run",
            "e2e-smoke",
            "--no-coverage",
            "--no-parallel",
            "--reports-dir",
            str(tmp_path / "reports"),
            "--baseline",
            str(tmp_path / "reports" / "previous-summary.json"),
        ]
    )
    # The original up() error must reach the test runner, not the down() one.
    with pytest.raises(RuntimeError, match="backend OOM during up"):
        cli_mod.cmd_run(args)


def test_cmd_run_writes_summary_even_on_corrupt_baseline(
    tmp_path: Path, monkeypatch
) -> None:
    """A corrupt baseline must not skip ``write_summary`` — the per-group
    reporting still needs to land on disk so the developer can see what
    passed/failed. Otherwise the rig silently swallows results on the build
    that needs them most.
    """
    manifest_yaml = (
        "version: 1\n"
        "groups:\n"
        "  unit-x:\n"
        "    tier: unit\n"
        "    paths: [x]\n"
        "    optional: true\n"
    )
    (tmp_path / "groups.yaml").write_text(manifest_yaml)
    (tmp_path / "critical_paths.yaml").write_text("version: 1\npaths: []\n")
    reports_dir = tmp_path / "reports"
    reports_dir.mkdir()
    baseline = reports_dir / "previous-summary.json"
    baseline.write_text("{not valid json")  # corrupt

    import tests.rig.cli as cli_mod
    import tests.rig.critical_paths as cp_mod
    import tests.rig.groups as groups_mod

    monkeypatch.setattr(groups_mod, "DEFAULT_MANIFEST", tmp_path / "groups.yaml")
    monkeypatch.setattr(
        cp_mod, "DEFAULT_REGISTRY", tmp_path / "critical_paths.yaml"
    )

    args = cli_mod._build_parser().parse_args(
        [
            "run",
            "unit-x",
            "--dry-run",
            "--no-coverage",
            "--no-parallel",
            "--reports-dir",
            str(reports_dir),
            "--baseline",
            str(baseline),
        ]
    )
    exit_code = cli_mod.cmd_run(args)
    # Build is red because baseline is corrupt, but summary.md must exist.
    assert exit_code != 0
    assert (reports_dir / "summary.md").exists(), (
        "write_summary must run even when load_baseline raises; otherwise "
        "developers lose all per-group visibility on the build that hit a "
        "corrupt cache."
    )
