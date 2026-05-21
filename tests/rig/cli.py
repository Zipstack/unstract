"""Rig CLI — the single entry point for tox, pre-commit, and CI.

Subcommands:
  run                 Execute selected groups (with dep-expansion).
  list-groups         Print known groups, tiers, and dep edges.
  list-critical-paths Print critical-path coverage status (best-effort).
  expand              Print the topo-sorted set of groups that ``run`` would execute.
  validate            Validate manifests; non-zero on schema errors.
  platform            ``up | down | status`` the e2e platform stack.
  report              ``combine`` — re-aggregate reports/ after the fact.
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import time
import uuid
from functools import lru_cache
from pathlib import Path
from xml.sax import saxutils

from tests.rig import critical_paths as cp
from tests.rig.coverage import combine_and_report, coverage_env
from tests.rig.groups import (
    REPO_ROOT,
    TIERS,
    GroupDefinition,
    load_groups,
)
from tests.rig.reporting import GroupResult, parse_junit, write_summary
from tests.rig.runtime import PlatformEndpoints, PlatformRuntime, pick_runtime
from tests.rig.selection import resolve

# Pytest exit codes that the rig treats as non-failure for aggregation:
#   0 — all tests passed
#   5 — no tests collected (optional placeholders, empty hurl group, etc.)
_NON_FAILING_PYTEST_EXIT_CODES = (0, 5)


@lru_cache(maxsize=1)
def _rig_session_id() -> str:
    """Stable per-invocation sentinel, computed once.

    Stamped into ``UNSTRACT_RIG_SESSION_ID`` for every group's pytest env so
    e2e tests can prove the rig ran. URL ownership is intentionally cooperative
    — the rig sets ``UNSTRACT_*_URL`` via ``setdefault``, so a developer's
    pre-set value wins (see tests/README.md). The session id is the rig's
    signature, not a claim that the rig owns the URLs.
    """
    return uuid.uuid4().hex


def _subprocess_env() -> dict[str, str]:
    """Base environment for every group's ``uv``/pytest subprocess.

    Drops ``VIRTUAL_ENV`` so ``uv run`` does clean per-group project discovery
    (each group runs against its own workdir's ``.venv``). When the rig runs
    under tox, tox exports ``VIRTUAL_ENV=.tox/<env>``, which doesn't match any
    group's project and makes ``uv`` emit a "does not match the project
    environment path" warning before ignoring it anyway. Stripping it removes
    the noise and the ambiguity. ``UV_PROJECT_ENVIRONMENT`` is dropped for the
    same reason.
    """
    env = os.environ.copy()
    env.pop("VIRTUAL_ENV", None)
    env.pop("UV_PROJECT_ENVIRONMENT", None)
    return env


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="tests.rig", description="Unstract unified test rig")
    sub = p.add_subparsers(dest="command", required=True)

    pr = sub.add_parser("run", help="Run selected groups")
    pr.add_argument("groups", nargs="*", help="Group names, or 'all'.")
    pr.add_argument("--from-file", type=Path, help="File with one group name per line.")
    pr.add_argument("--tier", choices=TIERS)
    pr.add_argument("--marker", help="Pytest -m marker expression to forward.")
    pr.add_argument(
        "--paths", help="Comma-separated pytest paths/nodeids (overrides group paths)."
    )
    pr.add_argument("--runtime", choices=["compose", "testcontainers", "local"])
    pr.add_argument("--coverage", dest="coverage", action="store_true", default=True)
    pr.add_argument("--no-coverage", dest="coverage", action="store_false")
    pr.add_argument("--parallel", dest="parallel", action="store_true", default=True)
    pr.add_argument("--no-parallel", dest="parallel", action="store_false")
    pr.add_argument(
        "--workers",
        default="auto",
        help="pytest-xdist worker count (default: auto).",
    )
    pr.add_argument("--timeout", type=int, help="Per-group timeout override in seconds.")
    pr.add_argument("--reports-dir", type=Path, default=REPO_ROOT / "reports")
    pr.add_argument(
        "--fail-on-critical-gap",
        action="store_true",
        help="Treat uncovered critical paths as a build failure.",
    )
    pr.add_argument(
        "--changed-only",
        action="store_true",
        help="Auto-select groups overlapping `git diff origin/main...HEAD`.",
    )
    pr.add_argument("--changed-base", default="origin/main")
    pr.add_argument(
        "--baseline",
        type=Path,
        default=REPO_ROOT / "reports" / "previous-summary.json",
    )
    pr.add_argument(
        "--update-baseline",
        action="store_true",
        help=(
            "On green main builds, merge this build's covered paths into the "
            "baseline. Merging (not overwriting) preserves coverage recorded by "
            "earlier tier invocations in the same workflow."
        ),
    )
    pr.add_argument("--dry-run", action="store_true", help="Plan only; do not execute.")
    pr.set_defaults(func=cmd_run)

    pl = sub.add_parser("list-groups", help="List all defined groups.")
    pl.set_defaults(func=cmd_list_groups)

    pc = sub.add_parser("list-critical-paths", help="Print critical-path status table.")
    pc.add_argument(
        "--baseline",
        type=Path,
        default=REPO_ROOT / "reports" / "previous-summary.json",
    )
    pc.set_defaults(func=cmd_list_critical)

    pe = sub.add_parser("expand", help="Show what `run` would execute, in topo order.")
    pe.add_argument("groups", nargs="*")
    pe.add_argument("--from-file", type=Path)
    pe.add_argument("--tier", choices=TIERS)
    pe.add_argument("--changed-only", action="store_true")
    pe.add_argument("--changed-base", default="origin/main")
    pe.set_defaults(func=cmd_expand)

    pv = sub.add_parser("validate", help="Validate manifests.")
    pv.set_defaults(func=cmd_validate)

    pp = sub.add_parser("platform", help="Manage the e2e platform stack.")
    pp.add_argument("action", choices=["up", "down", "status"])
    pp.add_argument("--runtime", choices=["compose", "testcontainers", "local"])
    pp.set_defaults(func=cmd_platform)

    pre = sub.add_parser("report", help="Re-aggregate existing reports/.")
    pre.add_argument("action", choices=["combine"])
    pre.add_argument("--reports-dir", type=Path, default=REPO_ROOT / "reports")
    pre.set_defaults(func=cmd_report)

    return p


# ── subcommands ───────────────────────────────────────────────────────────────


def cmd_list_groups(_args: argparse.Namespace) -> int:
    manifest = load_groups()
    for name in manifest.names():
        g = manifest.get(name)
        deps = ", ".join(g.depends_on) or "—"
        flags: list[str] = []
        if g.critical:
            flags.append("critical")
        if g.requires_platform:
            flags.append("platform")
        if g.optional:
            flags.append("optional")
        if g.requires_services:
            flags.append("svc:" + "+".join(g.requires_services))
        print(
            f"  {name:<32} tier={g.tier:<11} runner={g.runner:<7} "
            f"deps=[{deps}]  {' '.join(flags)}"
        )
    return 0


def cmd_list_critical(args: argparse.Namespace) -> int:
    manifest = load_groups()
    registry = cp.load_critical_paths()
    errors = cp.validate_registry_against_manifest(registry, manifest)
    for err in errors:
        print(f"ERROR: {err}", file=sys.stderr)
    try:
        baseline = cp.load_baseline(args.baseline)
    except cp.BaselineCorruptError as exc:
        print(f"[rig] {exc}", file=sys.stderr)
        baseline = None
    statuses = cp.evaluate(registry, groups_run_green=set(), baseline=baseline)
    icons = {"covered": "✅", "gap": "⚠️", "regression": "❌"}
    for s in statuses:
        cov = ", ".join(s.path.covered_by) or "—"
        print(f"  {icons[s.state]} {s.path.id:<28} declared coverage: {cov}")
    return 1 if errors else 0


def cmd_expand(args: argparse.Namespace) -> int:
    manifest = load_groups()
    ordered = resolve(
        manifest,
        positional=args.groups or [],
        from_file=args.from_file,
        tier=args.tier,
        changed_only=args.changed_only,
        changed_base=args.changed_base,
    )
    if not ordered:
        print("(no groups selected)", file=sys.stderr)
        return 1
    for name in ordered:
        g = manifest.get(name)
        print(f"  {name}  (tier={g.tier}, runner={g.runner})")
    return 0


def cmd_validate(_args: argparse.Namespace) -> int:
    """Validate both manifests. Schema/path/cycle errors come from
    ``load_groups`` (raised); cross-manifest errors come from
    ``validate_registry_against_manifest``.
    """
    try:
        manifest = load_groups()
    except (ValueError, FileNotFoundError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    try:
        registry = cp.load_critical_paths()
    except (ValueError, FileNotFoundError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    errors = cp.validate_registry_against_manifest(registry, manifest)
    for err in errors:
        print(f"ERROR: {err}", file=sys.stderr)
    if errors:
        return 1
    print(f"OK — {len(manifest.names())} groups, {len(registry.paths)} critical paths")
    return 0


def cmd_platform(args: argparse.Namespace) -> int:
    runtime = pick_runtime(args.runtime)
    if args.action == "up":
        try:
            endpoints = runtime.up()
        except Exception:
            # If up() raised mid-way (e.g. one testcontainer started, the next
            # failed), down() cleans up the partial stack.
            runtime.down()
            raise
        print(f"Platform up via runtime={runtime.name}:")
        print(f"  backend         : {endpoints.backend_url}")
        print(f"  prompt-service  : {endpoints.prompt_service_url}")
        print(f"  platform-service: {endpoints.platform_service_url}")
        print(f"  runner          : {endpoints.runner_url}")
        return 0
    if args.action == "down":
        runtime.down()
        return 0
    if args.action == "status":
        print(
            f"runtime={runtime.name} (status check is best-effort; "
            f"see `docker compose ps` for compose)"
        )
        return 0
    return 2


def cmd_report(args: argparse.Namespace) -> int:
    reports_dir: Path = args.reports_dir
    combine_and_report(reports_dir)
    manifest = load_groups()
    registry = cp.load_critical_paths()
    group_results: list[GroupResult] = []
    for name in manifest.names():
        tier = manifest.get(name).tier
        result = parse_junit(name, tier, reports_dir)
        if result is not None:
            group_results.append(result)
    green = _green_group_names(group_results)
    baseline_corrupt = False
    try:
        baseline = cp.load_baseline(reports_dir / "previous-summary.json")
    except cp.BaselineCorruptError as exc:
        print(f"[rig] {exc}", file=sys.stderr)
        baseline = None
        baseline_corrupt = True
    statuses = cp.evaluate(registry, groups_run_green=green, baseline=baseline)
    write_summary(
        reports_dir=reports_dir,
        group_results=group_results,
        critical_statuses=statuses,
        baseline_corrupt=baseline_corrupt,
    )
    print(f"Wrote {reports_dir / 'summary.md'}")
    return 0


def cmd_run(args: argparse.Namespace) -> int:
    manifest = load_groups()
    registry = cp.load_critical_paths()
    errs = cp.validate_registry_against_manifest(registry, manifest)
    for err in errs:
        print(f"ERROR: {err}", file=sys.stderr)
    if errs:
        return 2

    ordered = resolve(
        manifest,
        positional=args.groups or [],
        from_file=args.from_file,
        tier=args.tier,
        changed_only=args.changed_only,
        changed_base=args.changed_base,
    )
    if not ordered:
        print(
            "ERROR: no groups selected. Pass group names, `all`, --tier, or --from-file.",
            file=sys.stderr,
        )
        return 2

    runnable = [n for n in ordered if not _is_missing_placeholder(manifest.get(n))]
    skipped = [n for n in ordered if n not in runnable]
    for n in skipped:
        print(f"SKIP {n} (optional + workdir/paths absent)")
    # Scope of this invocation = every group we will actually run AFTER
    # dep-expansion (includes dependencies the user didn't ask for directly).
    # Skipped optional placeholders are excluded: their critical paths were
    # never going to be exercised here, so they must classify as gap, not
    # regression. evaluate() uses this to distinguish "this path's group ran
    # red" (regression) from "this path belongs to a tier we weren't running
    # this time" (gap).
    scope_groups = set(runnable)

    reports_dir: Path = args.reports_dir
    reports_dir.mkdir(parents=True, exist_ok=True)

    needs_platform = any(manifest.get(n).requires_platform for n in runnable)
    runtime: PlatformRuntime | None = None
    endpoints: PlatformEndpoints | None = None
    group_results: list[GroupResult] = []
    overall_exit = 0

    try:
        if needs_platform and not args.dry_run:
            runtime = pick_runtime(args.runtime)
            print(f"[rig] bringing platform up via runtime={runtime.name}")
            # `up()` is inside the try so a failure here still triggers `down()`
            # in the finally, cleaning up any partial stack.
            endpoints = runtime.up()

        for name in runnable:
            group = manifest.get(name)
            print(
                f"\n[rig] running group: {name} "
                f"(tier={group.tier}, runner={group.runner})"
            )
            if args.dry_run:
                continue
            result, exit_code = _execute_group(
                group,
                reports_dir=reports_dir,
                marker=args.marker,
                paths_override=args.paths,
                coverage=args.coverage,
                parallel=args.parallel and group.parallel,
                workers=args.workers,
                timeout=args.timeout or group.timeout_seconds,
                endpoints=endpoints,
            )
            if result is not None:
                group_results.append(result)
            # `optional: true` groups run and surface their result in the
            # summary, but never gate the overall exit. This honors the
            # developer intent for groups that need infra we don't provision in
            # CI (live-DB connector tests) or that are pluggable/cloud-only:
            # red shows in the report, merge isn't blocked. Both exit-folds
            # below are gated on `not group.optional` so the skip is consistent
            # whether the failure came via exit code or junit attestation.
            #
            # Always fold the exit code into overall_exit, even when junit.xml
            # was never written (segfault/OOM/missing binary). Otherwise the
            # rig silently returns 0 for catastrophic group failures.
            if (
                exit_code not in _NON_FAILING_PYTEST_EXIT_CODES
                and not group.optional
                and overall_exit == 0
            ):
                overall_exit = exit_code
            # Belt-and-braces: if the junit attests to errors/failures the exit
            # code didn't (truncated junit → errors=1 with exit 0), the report
            # shows ❌ but exit would otherwise stay 0. Keep them in sync.
            if (
                result is not None
                and (result.errors or result.failed)
                and not group.optional
                and overall_exit == 0
            ):
                overall_exit = 1
    finally:
        if runtime is not None and not args.dry_run:
            print(f"[rig] tearing platform down (runtime={runtime.name})")
            # Don't let a teardown failure mask the in-flight exception.
            # Python re-raises whatever exception we caught here if down()
            # raises during a `finally`, hiding the real cause upstream.
            try:
                runtime.down()
            except Exception as exc:
                print(
                    f"[rig] teardown failed (runtime={runtime.name}): {exc}",
                    file=sys.stderr,
                )

    if args.coverage and not args.dry_run:
        combine_and_report(reports_dir)

    green = _green_group_names(group_results)
    # A corrupt baseline can't be silently treated as empty (that would turn
    # the next build into a regression festival once a one-tier baseline gets
    # written back). But we must still write the per-group summary so the
    # developer can see what passed/failed — otherwise the reporting path
    # silently fails on top of the baseline error.
    baseline_corrupt = False
    try:
        baseline = cp.load_baseline(args.baseline)
    except cp.BaselineCorruptError as exc:
        print(f"[rig] ❌ {exc}", file=sys.stderr)
        baseline = None
        baseline_corrupt = True

    statuses = cp.evaluate(
        registry,
        groups_run_green=green,
        baseline=baseline,
        scope_groups=scope_groups,
    )
    write_summary(
        reports_dir=reports_dir,
        group_results=group_results,
        critical_statuses=statuses,
        baseline_corrupt=baseline_corrupt,
    )

    # Surface baseline corruption regardless of whether the build was
    # otherwise green or red. A red-then-fixed cycle without this flip would
    # silently swallow the corrupt cache and disable regression detection on
    # the next N builds.
    if baseline_corrupt and overall_exit == 0:
        overall_exit = 1

    # In a dry run no groups executed, so every covered path looks like a
    # gap/regression. A dry run is plan-only: report but never fail (and never
    # write a baseline) on the back of results that didn't happen.
    if args.dry_run:
        return overall_exit

    regressions = [s for s in statuses if s.state == "regression"]
    if regressions:
        print(
            f"\n[rig] ❌ {len(regressions)} critical-path regression(s) detected",
            file=sys.stderr,
        )
        if overall_exit == 0:
            overall_exit = 1

    gaps = [s for s in statuses if s.state == "gap"]
    if gaps and args.fail_on_critical_gap:
        print(
            f"\n[rig] ⚠️  {len(gaps)} critical-path gap(s) detected "
            f"(fail-on-critical-gap)",
            file=sys.stderr,
        )
        if overall_exit == 0:
            overall_exit = 1

    if args.update_baseline and overall_exit == 0:
        try:
            cp.merge_into_baseline(statuses, args.baseline)
            print(f"[rig] merged into baseline: {args.baseline}")
        except cp.BaselineCorruptError as exc:
            print(f"[rig] ❌ baseline write skipped: {exc}", file=sys.stderr)
            overall_exit = 1

    return overall_exit


# ── execution helpers ─────────────────────────────────────────────────────────


def _green_group_names(results: list[GroupResult]) -> set[str]:
    return {r.name for r in results if r.status in ("pass", "empty")}


def _is_missing_placeholder(group: GroupDefinition) -> bool:
    if not group.optional:
        return False
    wd = group.absolute_workdir()
    if not wd.exists():
        return True
    return not all(p.exists() for p in group.absolute_paths())


def _execute_group(
    group: GroupDefinition,
    *,
    reports_dir: Path,
    marker: str | None,
    paths_override: str | None,
    coverage: bool,
    parallel: bool,
    workers: str,
    timeout: int,
    endpoints: PlatformEndpoints | None,
) -> tuple[GroupResult | None, int]:
    group_reports = reports_dir / group.name
    group_reports.mkdir(parents=True, exist_ok=True)
    junit = group_reports / "junit.xml"
    md_report = group_reports / "report.md"

    env = _subprocess_env()
    env.update(group.env)
    if endpoints is not None:
        env.setdefault("UNSTRACT_BACKEND_URL", endpoints.backend_url)
        env.setdefault("UNSTRACT_PROMPT_SERVICE_URL", endpoints.prompt_service_url)
        env.setdefault("UNSTRACT_PLATFORM_SERVICE_URL", endpoints.platform_service_url)
        env.setdefault("UNSTRACT_RUNNER_URL", endpoints.runner_url)
        env.setdefault("UNSTRACT_X2TEXT_URL", endpoints.x2text_url)
        # Stamp the run with a per-invocation sentinel so e2e tests can
        # distinguish "rig brought the platform up" from "stale shell env
        # leaked in". `setdefault` would let a leaked sentinel win, which
        # defeats the purpose — set unconditionally.
        env["UNSTRACT_RIG_SESSION_ID"] = _rig_session_id()
    if coverage and group.coverage_source:
        env.update(coverage_env(group.name, reports_dir))

    # Best-effort dep prep. Each `uv` call uses check=False so a transient
    # install failure (e.g. network blip during `uv pip install`) doesn't kill
    # the whole rig; pytest will surface a real missing-module error if so.
    # If you're debugging "ModuleNotFoundError" in a group, scroll up for the
    # uv warnings — they're the smoking gun.
    _prepare_group_env(group, env=env)

    workdir = group.absolute_workdir()

    if group.runner == "hurl":
        cmd = _hurl_command(group, workdir)
        exit_code = _spawn(cmd, env=env, cwd=workdir, timeout=timeout)
        # Match the exit.txt write's defensive handling: a read-only reports
        # dir or full disk shouldn't abort the whole run and orphan completed
        # groups before the summary renders.
        try:
            _write_synthetic_junit(junit, group.name, exit_code)
        except OSError as err:
            print(
                f"[rig] could not write synthetic junit for {group.name}: {err}",
                file=sys.stderr,
            )
    else:
        cmd = _pytest_command(
            group,
            workdir=workdir,
            junit=junit,
            md_report=md_report,
            marker=marker,
            paths_override=paths_override,
            coverage=coverage,
            parallel=parallel,
            workers=workers,
            timeout=timeout,
        )
        exit_code = _spawn(cmd, env=env, cwd=workdir, timeout=timeout)

    try:
        (group_reports / "exit.txt").write_text(str(exit_code))
    except OSError as err:
        print(
            f"[rig] could not write exit.txt for {group.name}: {err}",
            file=sys.stderr,
        )

    return parse_junit(group.name, group.tier, reports_dir), exit_code


RIG_PYTEST_PLUGINS = (
    "pytest>=8.0.1",
    "pytest-md-report>=0.6.2",
    "pytest-timeout>=2.3.1",
    "pytest-xdist>=3.5.0",
    "pytest-cov>=4.1.0",
    "pytest-mock>=3.12.0",
)


def _prepare_group_env(group: GroupDefinition, *, env: dict[str, str]) -> None:
    """Sync deps for a group. Mirrors what the old per-service tox envs did,
    and ensures the rig's pytest plugins are present in the group's venv.
    """
    workdir = group.absolute_workdir()
    if not shutil.which("uv"):
        return
    if group.uv_sync_group:
        subprocess.run(
            ["uv", "sync", "--group", group.uv_sync_group],
            cwd=workdir,
            env=env,
            check=False,
        )
    if group.install_editable:
        subprocess.run(
            ["uv", "pip", "install", "-e", "."],
            cwd=workdir,
            env=env,
            check=False,
        )
    if group.pip_install:
        subprocess.run(
            ["uv", "pip", "install", *group.pip_install],
            cwd=workdir,
            env=env,
            check=False,
        )
    # NOTE: rig pytest plugins (pytest-timeout, pytest-md-report, etc.) are
    # injected via `uv run --with ...` in _pytest_command, not installed here.
    # That avoids losing them on the next `uv run` (which re-syncs the venv).


def _pytest_command(
    group: GroupDefinition,
    *,
    workdir: Path,
    junit: Path,
    md_report: Path,
    marker: str | None,
    paths_override: str | None,
    coverage: bool,
    parallel: bool,
    workers: str,
    timeout: int,
) -> list[str]:
    use_uv = shutil.which("uv") is not None
    if use_uv:
        # `uv run` re-syncs the project's venv each call, which would wipe any
        # plugins added via `uv pip install`. `--with` injects them into the
        # ephemeral run environment, surviving the sync.
        with_args: list[str] = []
        for spec in RIG_PYTEST_PLUGINS:
            with_args += ["--with", spec]
        base: list[str] = ["uv", "run", *with_args, "pytest"]
    else:
        base = [sys.executable, "-m", "pytest"]

    cmd = [
        *base,
        "-v",
        f"--junitxml={junit}",
        f"--timeout={timeout}",
    ]
    # pytest-md-report does not aggregate worker output reliably under xdist.
    # Emit markdown only on serial runs; junit + reporting.py's _render_markdown
    # cover the parallel case.
    if not parallel:
        cmd += [
            "--md-report",
            "--md-report-flavor=gfm",
            f"--md-report-output={md_report}",
        ]
    if coverage and group.coverage_source:
        cmd += [
            f"--cov={group.coverage_source}",
            "--cov-report=",
        ]
    if parallel:
        cmd += ["-n", workers]
    effective_marker = marker or group.markers
    if effective_marker:
        cmd += ["-m", effective_marker]
    cmd += list(group.pytest_extra)

    if paths_override:
        cmd += [p.strip() for p in paths_override.split(",") if p.strip()]
    else:
        # Paths are relative to workdir so pytest runs as `cd workdir && pytest <path>`.
        for p in group.paths:
            cmd.append(p)
    return cmd


def _hurl_command(group: GroupDefinition, workdir: Path) -> list[str]:
    files: list[str] = []
    for p in group.paths:
        target = workdir / p
        if target.is_dir():
            files.extend(sorted(str(f) for f in target.rglob("*.hurl")))
        elif target.is_file():
            files.append(str(target))
    if not files:
        # Surface as exit 5 ("no tests collected") for consistency with pytest.
        return ["sh", "-c", "exit 5"]
    return ["hurl", "--test", *files]


def _write_synthetic_junit(path: Path, group_name: str, exit_code: int) -> None:
    """Synthesise a JUnit XML for hurl runs.

    Exit 5 ("no tests collected") must produce failures=0; otherwise an empty
    hurl group would show ⚪ via :class:`GroupResult` while also being counted
    as a failure in totals + critical-path evaluation.

    ``group_name`` is XML-escaped: a group key containing ``"``/``&``/``<``
    would otherwise produce malformed XML, which ``parse_junit`` then reads as
    a phantom error on a green hurl run.
    """
    is_failure = exit_code != 0 and exit_code != 5
    failures = 1 if is_failure else 0
    failure_tag = f'<failure message="hurl exit {exit_code}"/>' if is_failure else ""
    name = saxutils.escape(group_name, {'"': "&quot;"})
    path.write_text(
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        f'<testsuite name="{name}" tests="1" failures="{failures}" '
        f'errors="0" skipped="0" time="0">\n'
        f'  <testcase classname="{name}" name="hurl-suite">{failure_tag}'
        f"</testcase>\n"
        f"</testsuite>\n"
    )


def _spawn(cmd: list[str], *, env: dict[str, str], cwd: Path, timeout: int) -> int:
    start = time.monotonic()
    try:
        result = subprocess.run(cmd, cwd=cwd, env=env, timeout=timeout + 30)
        return result.returncode
    except subprocess.TimeoutExpired:
        print(
            f"[rig] TIMEOUT after {time.monotonic() - start:.0f}s: {' '.join(cmd)}",
            file=sys.stderr,
        )
        return 124
    except FileNotFoundError as exc:
        print(f"[rig] command not found: {exc}", file=sys.stderr)
        return 127
