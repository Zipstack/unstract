"""Self-tests for the CLI's run-time wiring (scope_groups, teardown safety).

The bulk of the rig is tested via the manifest + evaluate + reporting helpers.
These tests exist for the parts of ``cmd_run`` that are hard to exercise from
pure unit tests — specifically, how it passes ``scope_groups`` through to
``evaluate`` and how it shields the in-flight exception from a teardown failure.

These tests monkeypatch module-level constants (``DEFAULT_MANIFEST``,
``DEFAULT_REGISTRY``) because ``cmd_run`` reads them at call time. Safe today
because the read is synchronous; if manifest loading ever becomes async (or
the CLI starts caching a parsed manifest at import time), prefer passing the
path explicitly through CLI args rather than expanding this patching pattern.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from tests.rig.runtime import PlatformEndpoints


def test_cmd_run_passes_scope_to_evaluate(tmp_path: Path, monkeypatch) -> None:
    """``cmd_run`` must pass the runnable dep-expanded selection (not just
    groups_run_green) as ``scope_groups``. Without this plumbing, scope-aware
    regression filtering has no effect — a future refactor that drops the
    kwarg would silently reintroduce cross-tier regression false positives
    where the unit-tier baseline lights up the e2e-tier paths as regressed.

    ``unit-x`` is given a real workdir/path so it survives the
    ``_is_missing_placeholder`` filter and lands in ``scope_groups``; the
    companion test ``test_cmd_run_excludes_missing_placeholders_from_scope``
    covers the opposite case.
    """
    test_dir = Path(__file__).parent
    manifest_yaml = (
        "version: 1\n"
        "groups:\n"
        "  unit-x:\n"
        "    tier: unit\n"
        f"    workdir: {test_dir}\n"
        "    paths: [.]\n"
    )
    cp_yaml = "version: 1\npaths: []\n"
    (tmp_path / "groups.yaml").write_text(manifest_yaml)
    (tmp_path / "critical_paths.yaml").write_text(cp_yaml)

    # Redirect the rig's manifest paths to the tmp_path fixtures.
    import tests.rig.cli as cli_mod
    import tests.rig.critical_paths as cp_mod
    import tests.rig.groups as groups_mod

    monkeypatch.setattr(groups_mod, "DEFAULT_MANIFEST", tmp_path / "groups.yaml")
    monkeypatch.setattr(cp_mod, "DEFAULT_REGISTRY", tmp_path / "critical_paths.yaml")

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


def test_cmd_run_excludes_missing_placeholders_from_scope(
    tmp_path: Path, monkeypatch
) -> None:
    """An ``optional: true`` group whose paths/workdir are absent is skipped
    and must NOT appear in ``scope_groups``. If it leaked into scope, its
    critical paths would classify as ``regression`` (in scope, not green)
    instead of ``gap`` — exactly the cross-tier false positive Fix 2 prevents.
    """
    manifest_yaml = (
        "version: 1\n"
        "groups:\n"
        "  unit-absent:\n"
        "    tier: unit\n"
        "    paths: [definitely-not-on-disk]\n"
        "    optional: true\n"
    )
    (tmp_path / "groups.yaml").write_text(manifest_yaml)
    (tmp_path / "critical_paths.yaml").write_text("version: 1\npaths: []\n")

    import tests.rig.cli as cli_mod
    import tests.rig.critical_paths as cp_mod
    import tests.rig.groups as groups_mod

    monkeypatch.setattr(groups_mod, "DEFAULT_MANIFEST", tmp_path / "groups.yaml")
    monkeypatch.setattr(cp_mod, "DEFAULT_REGISTRY", tmp_path / "critical_paths.yaml")

    captured: dict[str, Any] = {}
    real_evaluate = cp_mod.evaluate

    def spy_evaluate(*args, **kwargs):
        captured["scope_groups"] = kwargs.get("scope_groups")
        return real_evaluate(*args, **kwargs)

    monkeypatch.setattr(cli_mod.cp, "evaluate", spy_evaluate)

    args = cli_mod._build_parser().parse_args(
        [
            "run",
            "unit-absent",
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
    assert captured["scope_groups"] == set(), (
        "skipped optional placeholders must be excluded from scope_groups; "
        f"got {captured.get('scope_groups')}"
    )


def test_optional_group_failure_does_not_block_overall_exit(
    tmp_path: Path, monkeypatch
) -> None:
    """A failing ``optional: true`` group surfaces its red result in the
    summary but must NOT gate the overall exit code. This honors the developer
    intent for groups that need infra we don't provision in CI (live-DB
    connector tests) or that are pluggable/cloud-only — red shows in the
    report, merge isn't blocked.
    """
    from tests.rig.reporting import GroupResult

    test_dir = Path(__file__).parent
    manifest_yaml = (
        "version: 1\n"
        "groups:\n"
        "  unit-opt:\n"
        "    tier: unit\n"
        f"    workdir: {test_dir}\n"
        "    paths: [.]\n"
        "    optional: true\n"
        "  unit-req:\n"
        "    tier: unit\n"
        f"    workdir: {test_dir}\n"
        "    paths: [.]\n"
    )
    (tmp_path / "groups.yaml").write_text(manifest_yaml)
    (tmp_path / "critical_paths.yaml").write_text("version: 1\npaths: []\n")

    import tests.rig.cli as cli_mod
    import tests.rig.critical_paths as cp_mod
    import tests.rig.groups as groups_mod

    monkeypatch.setattr(groups_mod, "DEFAULT_MANIFEST", tmp_path / "groups.yaml")
    monkeypatch.setattr(cp_mod, "DEFAULT_REGISTRY", tmp_path / "critical_paths.yaml")

    def fake_execute_group(group, **kwargs):
        # The optional group fails; the required one passes.
        failed = 1 if group.optional else 0
        exit_code = 1 if group.optional else 0
        result = GroupResult(
            name=group.name,
            tier=group.tier,
            exit_code=exit_code,
            passed=0 if group.optional else 1,
            failed=failed,
            errors=0,
            skipped=0,
            duration_seconds=0.01,
        )
        return result, exit_code

    monkeypatch.setattr(cli_mod, "_execute_group", fake_execute_group)

    args = cli_mod._build_parser().parse_args(
        [
            "run",
            "unit-opt",
            "unit-req",
            "--no-coverage",
            "--no-parallel",
            "--reports-dir",
            str(tmp_path / "reports"),
            "--baseline",
            str(tmp_path / "reports" / "previous-summary.json"),
        ]
    )
    exit_code = cli_mod.cmd_run(args)
    assert exit_code == 0, (
        "a failing optional group must not gate the overall exit; "
        f"got exit_code={exit_code}"
    )


def _run_gap_scenario(
    tmp_path: Path, monkeypatch, *, covered_by: str, fail_on_gap: bool
) -> int:
    """Drive cmd_run with a single optional group ``unit-cov`` that runs RED and
    one critical path covered by ``covered_by`` (a YAML list literal like
    ``[unit-cov]`` or ``[]``). The group is optional so its own red exit never
    gates — isolating the critical-gap logic. Returns the overall exit code.
    """
    from tests.rig.reporting import GroupResult

    test_dir = Path(__file__).parent
    manifest_yaml = (
        "version: 1\n"
        "groups:\n"
        "  unit-cov:\n"
        "    tier: unit\n"
        f"    workdir: {test_dir}\n"
        "    paths: [.]\n"
        "    optional: true\n"
    )
    cp_yaml = (
        "version: 1\n"
        "paths:\n"
        "  - id: p1\n"
        "    description: ''\n"
        "    entry: ''\n"
        f"    covered_by: {covered_by}\n"
    )
    (tmp_path / "groups.yaml").write_text(manifest_yaml)
    (tmp_path / "critical_paths.yaml").write_text(cp_yaml)

    import tests.rig.cli as cli_mod
    import tests.rig.critical_paths as cp_mod
    import tests.rig.groups as groups_mod

    monkeypatch.setattr(groups_mod, "DEFAULT_MANIFEST", tmp_path / "groups.yaml")
    monkeypatch.setattr(cp_mod, "DEFAULT_REGISTRY", tmp_path / "critical_paths.yaml")

    def fake_execute_group(group, **kwargs):
        # The covering group runs red, so it never counts as green coverage.
        result = GroupResult(
            name=group.name,
            tier=group.tier,
            exit_code=1,
            passed=0,
            failed=1,
            errors=0,
            skipped=0,
            duration_seconds=0.01,
        )
        return result, 1

    monkeypatch.setattr(cli_mod, "_execute_group", fake_execute_group)

    argv = [
        "run",
        "unit-cov",
        "--no-coverage",
        "--no-parallel",
        "--reports-dir",
        str(tmp_path / "reports"),
        "--baseline",
        str(tmp_path / "reports" / "previous-summary.json"),
    ]
    if fail_on_gap:
        argv.append("--fail-on-critical-gap")
    args = cli_mod._build_parser().parse_args(argv)
    return cli_mod.cmd_run(args)


def test_fail_on_critical_gap_gates_on_in_scope_gap(tmp_path: Path, monkeypatch) -> None:
    """A critical path covered by an in-tier group that ran red is an IN-SCOPE
    gap: --fail-on-critical-gap must fail the build on it (real coverage is
    gone). Without the flag, it's reported but doesn't gate.
    """
    assert (
        _run_gap_scenario(
            tmp_path, monkeypatch, covered_by="[unit-cov]", fail_on_gap=True
        )
        == 1
    )
    assert (
        _run_gap_scenario(
            tmp_path, monkeypatch, covered_by="[unit-cov]", fail_on_gap=False
        )
        == 0
    )


def test_fail_on_critical_gap_ignores_out_of_scope_gap(
    tmp_path: Path, monkeypatch
) -> None:
    """A path with no declared coverage (or coverage only in another tier) is an
    OUT-OF-SCOPE gap: --fail-on-critical-gap must NOT fail this tier on it.
    This is the fix for the perma-red `main`: e2e-only and not-yet-covered paths
    can't fail the unit/integration tiers.
    """
    assert (
        _run_gap_scenario(tmp_path, monkeypatch, covered_by="[]", fail_on_gap=True)
        == 0
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
    monkeypatch.setattr(cp_mod, "DEFAULT_REGISTRY", tmp_path / "critical_paths.yaml")

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
    monkeypatch.setattr(cp_mod, "DEFAULT_REGISTRY", tmp_path / "critical_paths.yaml")

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
    summary_md = reports_dir / "summary.md"
    assert summary_md.exists(), (
        "write_summary must run even when load_baseline raises; otherwise "
        "developers lose all per-group visibility on the build that hit a "
        "corrupt cache."
    )
    # And the durable artifact must SAY the baseline was corrupt so reviewers
    # don't read its "gap" entries as first-time gaps when they're actually
    # regressions hidden by the cache failure.
    content = summary_md.read_text()
    assert "Baseline cache was corrupt" in content, (
        "summary.md must surface baseline corruption so reviewers reading "
        "the sticky PR comment know regression detection was disabled. "
        f"Got:\n{content}"
    )


def test_cmd_run_does_not_update_baseline_on_red_build(
    tmp_path: Path, monkeypatch
) -> None:
    """``--update-baseline`` must skip the write when the build is red.
    Otherwise red-build state bakes into the cache and masks the next real
    regression. A refactor dropping the ``overall_exit == 0`` guard would
    silently reintroduce that footgun.
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
    baseline.write_text("{not valid json")  # corrupt → red build

    import tests.rig.cli as cli_mod
    import tests.rig.critical_paths as cp_mod
    import tests.rig.groups as groups_mod

    monkeypatch.setattr(groups_mod, "DEFAULT_MANIFEST", tmp_path / "groups.yaml")
    monkeypatch.setattr(cp_mod, "DEFAULT_REGISTRY", tmp_path / "critical_paths.yaml")
    merge_calls: list[Any] = []
    monkeypatch.setattr(
        cli_mod.cp,
        "merge_into_baseline",
        lambda statuses, dest: merge_calls.append((statuses, dest)),
    )

    args = cli_mod._build_parser().parse_args(
        [
            "run",
            "unit-x",
            "--dry-run",
            "--update-baseline",
            "--no-coverage",
            "--no-parallel",
            "--reports-dir",
            str(reports_dir),
            "--baseline",
            str(baseline),
        ]
    )
    exit_code = cli_mod.cmd_run(args)
    assert exit_code != 0
    assert merge_calls == [], (
        "merge_into_baseline must NOT be called when overall_exit != 0; "
        "writing red-build state to the baseline cache hides regressions "
        f"on the next build. Got calls: {merge_calls}"
    )


def test_synthetic_junit_escapes_group_name(tmp_path: Path) -> None:
    """A group key containing XML metacharacters must not break the synthetic
    junit — otherwise parse_junit reads malformed XML as a phantom error on a
    green hurl run.
    """
    import xml.etree.ElementTree as ET

    import tests.rig.cli as cli_mod

    junit = tmp_path / "junit.xml"
    cli_mod._write_synthetic_junit(junit, 'hurl-api & docs <"x">', exit_code=0)
    # Must parse without raising and round-trip the name intact.
    root = ET.parse(junit).getroot()
    assert root.attrib["name"] == 'hurl-api & docs <"x">'


def test_synthetic_junit_exit_5_is_not_a_failure(tmp_path: Path) -> None:
    import xml.etree.ElementTree as ET

    import tests.rig.cli as cli_mod

    junit = tmp_path / "junit.xml"
    cli_mod._write_synthetic_junit(junit, "g", exit_code=5)
    root = ET.parse(junit).getroot()
    assert root.attrib["failures"] == "0"


def test_cmd_report_re_aggregates_existing_junit(tmp_path: Path, monkeypatch) -> None:
    """`report combine` re-parses each group's junit + writes all three summary
    artifacts. It's the CI-retry / manual entrypoint and was previously
    untested.
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
    (reports_dir / "unit-x").mkdir(parents=True)
    (reports_dir / "unit-x" / "junit.xml").write_text(
        '<?xml version="1.0"?>'
        '<testsuite name="unit-x" tests="2" failures="0" errors="0" '
        'skipped="0" time="0.5"/>'
    )
    (reports_dir / "unit-x" / "exit.txt").write_text("0")

    import tests.rig.cli as cli_mod
    import tests.rig.critical_paths as cp_mod
    import tests.rig.groups as groups_mod

    monkeypatch.setattr(groups_mod, "DEFAULT_MANIFEST", tmp_path / "groups.yaml")
    monkeypatch.setattr(cp_mod, "DEFAULT_REGISTRY", tmp_path / "critical_paths.yaml")
    # Skip the coverage subprocess; we only care about report aggregation here.
    monkeypatch.setattr(cli_mod, "combine_and_report", lambda _d: None)

    args = cli_mod._build_parser().parse_args(
        ["report", "combine", "--reports-dir", str(reports_dir)]
    )
    exit_code = cli_mod.cmd_report(args)
    assert exit_code == 0
    for artifact in ("summary.md", "summary.json", "combined-test-report.md"):
        assert (reports_dir / artifact).exists(), f"missing {artifact}"
    assert "unit-x" in (reports_dir / "summary.md").read_text()
