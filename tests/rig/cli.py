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
from pathlib import Path

from tests.rig import critical_paths as cp
from tests.rig.coverage import combine_and_report, coverage_env
from tests.rig.groups import REPO_ROOT, GroupDefinition, GroupManifest, load_groups
from tests.rig.reporting import GroupResult, parse_junit, write_summary
from tests.rig.runtime import PlatformEndpoints, PlatformRuntime, pick_runtime
from tests.rig.selection import resolve


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
    pr.add_argument("--tier", choices=["unit", "integration", "e2e"])
    pr.add_argument("--marker", help="Pytest -m marker expression to forward.")
    pr.add_argument("--paths", help="Comma-separated pytest paths/nodeids (overrides group paths).")
    pr.add_argument("--runtime", choices=["compose", "testcontainers", "local"])
    pr.add_argument("--coverage", dest="coverage", action="store_true", default=True)
    pr.add_argument("--no-coverage", dest="coverage", action="store_false")
    pr.add_argument("--parallel", dest="parallel", action="store_true", default=True)
    pr.add_argument("--no-parallel", dest="parallel", action="store_false")
    pr.add_argument("--workers", default="auto", help="pytest-xdist worker count (default: auto).")
    pr.add_argument("--timeout", type=int, help="Per-group timeout override in seconds.")
    pr.add_argument("--reports-dir", type=Path, default=REPO_ROOT / "reports")
    pr.add_argument("--fail-on-critical-gap", action="store_true",
                    help="Treat uncovered critical paths as a build failure.")
    pr.add_argument("--changed-only", action="store_true",
                    help="Auto-select groups overlapping `git diff origin/main...HEAD`.")
    pr.add_argument("--changed-base", default="origin/main")
    pr.add_argument("--baseline", type=Path, default=REPO_ROOT / "reports" / "previous-summary.json")
    pr.add_argument("--update-baseline", action="store_true",
                    help="On green main builds, write this build's covered paths as the new baseline.")
    pr.add_argument("--dry-run", action="store_true", help="Plan only; do not execute.")
    pr.set_defaults(func=cmd_run)

    pl = sub.add_parser("list-groups", help="List all defined groups.")
    pl.set_defaults(func=cmd_list_groups)

    pc = sub.add_parser("list-critical-paths", help="Print critical-path status table.")
    pc.add_argument("--baseline", type=Path, default=REPO_ROOT / "reports" / "previous-summary.json")
    pc.set_defaults(func=cmd_list_critical)

    pe = sub.add_parser("expand", help="Show what `run` would execute, in topo order.")
    pe.add_argument("groups", nargs="*")
    pe.add_argument("--from-file", type=Path)
    pe.add_argument("--tier", choices=["unit", "integration", "e2e"])
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


# ── subcommands ────────────────────────────────────────────────────────────────


def cmd_list_groups(_args: argparse.Namespace) -> int:
    manifest = load_groups()
    for name in manifest.names():
        g = manifest.get(name)
        deps = ", ".join(g.depends_on) or "—"
        flags = []
        if g.critical:
            flags.append("critical")
        if g.requires_platform:
            flags.append("platform")
        if g.optional:
            flags.append("optional")
        if g.requires_services:
            flags.append("svc:" + "+".join(g.requires_services))
        print(f"  {name:<32} tier={g.tier:<11} runner={g.runner:<7} deps=[{deps}]  {' '.join(flags)}")
    return 0


def cmd_list_critical(args: argparse.Namespace) -> int:
    manifest = load_groups()
    registry = cp.load_critical_paths()
    errors = cp.validate_registry_against_manifest(registry, manifest)
    for err in errors:
        print(f"ERROR: {err}", file=sys.stderr)
    baseline = cp.load_baseline(args.baseline)
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
    manifest = load_groups()
    registry = cp.load_critical_paths()
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
        endpoints = runtime.up()
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
        print(f"runtime={runtime.name} (status check is best-effort; see `docker compose ps` for compose)")
        return 0
    return 2


def cmd_report(args: argparse.Namespace) -> int:
    reports_dir: Path = args.reports_dir
    combine_and_report(reports_dir)
    # Best-effort re-aggregation using whatever junit.xml files we find.
    manifest = load_groups()
    registry = cp.load_critical_paths()
    group_results: list[GroupResult] = []
    for name in manifest.names():
        tier = manifest.get(name).tier
        result = parse_junit(name, tier, reports_dir)
        if result is not None:
            group_results.append(result)
    green = {r.name for r in group_results if r.failed == 0 and r.errors == 0 and r.exit_code in (0, 5)}
    baseline = cp.load_baseline(reports_dir / "previous-summary.json")
    statuses = cp.evaluate(registry, groups_run_green=green, baseline=baseline)
    write_summary(
        reports_dir=reports_dir,
        group_results=group_results,
        critical_statuses=statuses,
    )
    print(f"Wrote {reports_dir/'summary.md'}")
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
        print("ERROR: no groups selected. Pass group names, `all`, --tier, or --from-file.", file=sys.stderr)
        return 2

    # Filter out optional groups whose workdir doesn't exist (placeholders).
    runnable = [n for n in ordered if not _is_missing_placeholder(manifest.get(n))]
    skipped = [n for n in ordered if n not in runnable]
    for n in skipped:
        print(f"SKIP {n} (optional + workdir/paths absent)")

    reports_dir: Path = args.reports_dir
    reports_dir.mkdir(parents=True, exist_ok=True)

    # Bring up the platform once if any selected group needs it.
    runtime: PlatformRuntime | None = None
    endpoints: PlatformEndpoints | None = None
    if any(manifest.get(n).requires_platform for n in runnable):
        runtime = pick_runtime(args.runtime)
        if not args.dry_run:
            print(f"[rig] bringing platform up via runtime={runtime.name}")
            endpoints = runtime.up()

    group_results: list[GroupResult] = []
    overall_exit = 0
    try:
        for name in runnable:
            group = manifest.get(name)
            print(f"\n[rig] running group: {name} (tier={group.tier}, runner={group.runner})")
            if args.dry_run:
                continue
            result = _execute_group(
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
                if result.exit_code not in (0, 5):
                    overall_exit = overall_exit or result.exit_code
    finally:
        if runtime is not None and not args.dry_run:
            print(f"[rig] tearing platform down (runtime={runtime.name})")
            runtime.down()

    if args.coverage and not args.dry_run:
        combine_and_report(reports_dir)

    green = {r.name for r in group_results if r.failed == 0 and r.errors == 0 and r.exit_code in (0, 5)}
    baseline = cp.load_baseline(args.baseline)
    statuses = cp.evaluate(registry, groups_run_green=green, baseline=baseline)
    write_summary(reports_dir=reports_dir, group_results=group_results, critical_statuses=statuses)

    regressions = [s for s in statuses if s.state == "regression"]
    if regressions:
        print(f"\n[rig] ❌ {len(regressions)} critical-path regression(s) detected", file=sys.stderr)
        overall_exit = overall_exit or 1

    gaps = [s for s in statuses if s.state == "gap"]
    if gaps and args.fail_on_critical_gap:
        print(f"\n[rig] ⚠️  {len(gaps)} critical-path gap(s) detected (fail-on-critical-gap)", file=sys.stderr)
        overall_exit = overall_exit or 1

    if args.update_baseline and overall_exit == 0:
        cp.emit_baseline(statuses, args.baseline)
        print(f"[rig] updated baseline: {args.baseline}")

    return overall_exit


# ── execution helpers ─────────────────────────────────────────────────────────


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
) -> GroupResult | None:
    group_reports = reports_dir / group.name
    group_reports.mkdir(parents=True, exist_ok=True)
    junit = group_reports / "junit.xml"
    md_report = group_reports / "report.md"

    env = os.environ.copy()
    env.update(group.env)
    if endpoints is not None:
        env.setdefault("UNSTRACT_BACKEND_URL", endpoints.backend_url)
        env.setdefault("UNSTRACT_PROMPT_SERVICE_URL", endpoints.prompt_service_url)
        env.setdefault("UNSTRACT_PLATFORM_SERVICE_URL", endpoints.platform_service_url)
        env.setdefault("UNSTRACT_RUNNER_URL", endpoints.runner_url)
    if coverage:
        env.update(coverage_env(group.name, reports_dir))

    # Prepare deps (best-effort — failures don't necessarily fail the group;
    # pytest will surface the real error).
    _prepare_group_env(group, env=env)

    workdir = group.absolute_workdir()

    if group.runner == "hurl":
        cmd = _hurl_command(group, workdir)
        exit_code = _spawn(cmd, env=env, cwd=workdir, timeout=timeout)
        # No JUnit from hurl by default — synthesize a minimal one.
        _write_synthetic_junit(junit, group.name, exit_code)
    else:
        cmd = _pytest_command(
            group,
            workdir=workdir,
            junit=junit,
            md_report=md_report,
            marker=marker,
            paths_override=paths_override,
            parallel=parallel,
            workers=workers,
            timeout=timeout,
        )
        exit_code = _spawn(cmd, env=env, cwd=workdir, timeout=timeout)

    (group_reports / "exit.txt").write_text(str(exit_code))
    return parse_junit(group.name, group.tier, reports_dir)


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
        subprocess.run(["uv", "pip", "install", "-e", "."], cwd=workdir, env=env, check=False)
    if group.pip_install:
        subprocess.run(
            ["uv", "pip", "install", *group.pip_install],
            cwd=workdir,
            env=env,
            check=False,
        )
    # Inject the rig's required pytest plugins. Idempotent; uv pip install is
    # a no-op when versions already satisfy.
    subprocess.run(
        ["uv", "pip", "install", *RIG_PYTEST_PLUGINS],
        cwd=workdir,
        env=env,
        check=False,
    )


def _pytest_command(
    group: GroupDefinition,
    *,
    workdir: Path,
    junit: Path,
    md_report: Path,
    marker: str | None,
    paths_override: str | None,
    parallel: bool,
    workers: str,
    timeout: int,
) -> list[str]:
    use_uv = shutil.which("uv") is not None
    base: list[str] = ["uv", "run", "pytest"] if use_uv else [sys.executable, "-m", "pytest"]

    cmd = [
        *base,
        "-v",
        f"--junitxml={junit}",
        "--md-report",
        "--md-report-flavor=gfm",
        f"--md-report-output={md_report}",
        f"--timeout={timeout}",
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
        # Make paths relative to workdir so pytest works the same as `cd workdir && pytest path`.
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
    failed = 1 if exit_code != 0 else 0
    failure_tag = f'<failure message="hurl exit {exit_code}"/>' if failed else ""
    path.write_text(
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        f'<testsuite name="{group_name}" tests="1" failures="{failed}" errors="0" skipped="0" time="0">\n'
        f'  <testcase classname="{group_name}" name="hurl-suite">{failure_tag}</testcase>\n'
        f'</testsuite>\n'
    )


def _spawn(cmd: list[str], *, env: dict[str, str], cwd: Path, timeout: int) -> int:
    start = time.monotonic()
    try:
        result = subprocess.run(cmd, cwd=cwd, env=env, timeout=timeout + 30)
        return result.returncode
    except subprocess.TimeoutExpired:
        print(f"[rig] TIMEOUT after {time.monotonic() - start:.0f}s: {' '.join(cmd)}", file=sys.stderr)
        return 124
    except FileNotFoundError as exc:
        print(f"[rig] command not found: {exc}", file=sys.stderr)
        return 127
