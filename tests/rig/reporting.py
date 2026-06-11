"""Aggregate per-group results into a single human + machine summary.

Per group, the rig writes:
  reports/<group>/junit.xml   — pytest --junitxml
  reports/<group>/report.md   — pytest-md-report
  reports/<group>/exit.txt    — single integer pytest exit code

This module aggregates those into:
  reports/summary.json        — machine-readable
  reports/summary.md          — human-readable, PR-comment friendly
  reports/combined-test-report.md — backward-compatible alias for the
                                    existing sticky-comment workflow.
"""

from __future__ import annotations

import logging
import xml.etree.ElementTree as ET
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Literal

from tests.rig.critical_paths import CriticalPathStatus

log = logging.getLogger(__name__)

ResultStatus = Literal["pass", "empty", "fail"]

_STATUS_ICONS: dict[ResultStatus, str] = {
    "pass": "✅",
    "empty": "⚪",
    "fail": "❌",
}


@dataclass(frozen=True)
class GroupResult:
    name: str
    tier: str
    exit_code: int
    passed: int
    failed: int
    errors: int
    skipped: int
    duration_seconds: float

    @property
    def status(self) -> ResultStatus:
        if self.exit_code == 5:  # pytest "no tests collected"
            return "empty"
        if self.exit_code == 0 and self.failed == 0 and self.errors == 0:
            return "pass"
        return "fail"

    @property
    def status_icon(self) -> str:
        return _STATUS_ICONS[self.status]


def parse_junit(group_name: str, tier: str, reports_dir: Path) -> GroupResult | None:
    """Parse a group's junit.xml + exit.txt. Returns ``None`` if junit.xml is
    missing or unparseable, ``GroupResult`` with errors=1 if the XML lacks the
    expected counter attributes (which would otherwise look spuriously green).
    """
    junit_path = reports_dir / group_name / "junit.xml"
    exit_path = reports_dir / group_name / "exit.txt"
    if not junit_path.exists():
        return None

    exit_code = _read_exit_code(exit_path)

    try:
        tree = ET.parse(junit_path)
    except ET.ParseError as exc:
        log.warning("malformed junit.xml for group %r: %s", group_name, exc)
        return GroupResult(
            name=group_name,
            tier=tier,
            exit_code=exit_code or -1,
            passed=0,
            failed=0,
            errors=1,
            skipped=0,
            duration_seconds=0.0,
        )

    root = tree.getroot()
    suites = root.findall("testsuite") if root.tag == "testsuites" else [root]

    passed = failed = errors = skipped = 0
    duration = 0.0
    saw_attributes = False
    for s in suites:
        if "tests" in s.attrib:
            saw_attributes = True
        try:
            total = int(s.attrib.get("tests", "0"))
            f = int(s.attrib.get("failures", "0"))
            e = int(s.attrib.get("errors", "0"))
            sk = int(s.attrib.get("skipped", "0"))
            duration += float(s.attrib.get("time") or 0)
        except (TypeError, ValueError) as exc:
            log.warning(
                "junit.xml for group %r has non-numeric counters: %s", group_name, exc
            )
            return GroupResult(
                name=group_name,
                tier=tier,
                exit_code=exit_code or -1,
                passed=0,
                failed=0,
                errors=1,
                skipped=0,
                duration_seconds=duration,
            )
        failed += f
        errors += e
        skipped += sk
        passed += max(total - f - e - sk, 0)

    if not saw_attributes:
        # Junit that parses but has no counters anywhere is almost certainly a
        # truncated write. Don't count it as green.
        log.warning(
            "junit.xml for group %r has no counter attributes; treating as error",
            group_name,
        )
        errors = max(errors, 1)

    return GroupResult(
        name=group_name,
        tier=tier,
        exit_code=exit_code,
        passed=passed,
        failed=failed,
        errors=errors,
        skipped=skipped,
        duration_seconds=duration,
    )


def _read_exit_code(exit_path: Path) -> int:
    if not exit_path.exists():
        return -1
    try:
        return int(exit_path.read_text().strip())
    except (OSError, ValueError) as exc:
        log.warning("could not read exit code from %s: %s", exit_path, exc)
        return -1


def write_summary(
    *,
    reports_dir: Path,
    group_results: list[GroupResult],
    critical_statuses: list[CriticalPathStatus],
    baseline_corrupt: bool = False,
) -> None:
    """Write the per-build summary in JSON and Markdown.

    ``baseline_corrupt=True`` flags a build where the cached baseline could
    not be parsed. The Markdown summary surfaces a banner so reviewers
    reading the durable artifact (sticky PR comment, CI step summary) know
    that regression detection was disabled and any "gap" entries here might
    actually be regressions.
    """
    summary_json = reports_dir / "summary.json"
    summary_md = reports_dir / "summary.md"
    combined_md = reports_dir / "combined-test-report.md"

    import json

    summary_json.write_text(
        json.dumps(
            {
                "groups": [asdict(r) for r in group_results],
                "critical_paths": [
                    {
                        "id": s.path.id,
                        "state": s.state,
                        "covering_groups_run": list(s.covering_groups_run),
                    }
                    for s in critical_statuses
                ],
                "baseline_corrupt": baseline_corrupt,
            },
            indent=2,
        )
    )

    md = _render_markdown(group_results, critical_statuses, baseline_corrupt)
    summary_md.write_text(md)
    # Backward-compat alias for the existing sticky-comment workflow.
    combined_md.write_text(md)


def _render_markdown(
    group_results: list[GroupResult],
    critical_statuses: list[CriticalPathStatus],
    baseline_corrupt: bool = False,
) -> str:
    lines: list[str] = ["# Unstract test results", ""]
    if baseline_corrupt:
        lines.extend(
            [
                "> ⚠️ **Baseline cache was corrupt; regression detection "
                "disabled this run.** Paths classified below as `gap` may "
                "actually be regressions. Clear the baseline cache and "
                "re-run to re-validate.",
                "",
            ]
        )

    if group_results:
        lines.append("## Per-group results")
        lines.append("")
        lines.append(
            "| Status | Group | Tier | Passed | Failed | Errors | Skipped | Duration (s) |"
        )
        lines.append("|---|---|---|---:|---:|---:|---:|---:|")
        for r in group_results:
            lines.append(
                f"| {r.status_icon} | `{r.name}` | {r.tier} | {r.passed} | {r.failed} "
                f"| {r.errors} | {r.skipped} | {r.duration_seconds:.1f} |"
            )
        totals = _totals(group_results)
        lines.append(
            f"| | **TOTAL** | | **{totals['passed']}** | **{totals['failed']}** "
            f"| **{totals['errors']}** | **{totals['skipped']}** "
            f"| **{totals['duration']:.1f}** |"
        )
        lines.append("")
    else:
        lines.append("_No groups ran in this build._\n")

    if critical_statuses:
        regressions = [s for s in critical_statuses if s.state == "regression"]
        gaps = [s for s in critical_statuses if s.state == "gap"]
        covered = [s for s in critical_statuses if s.state == "covered"]

        lines.append("## Critical paths")
        lines.append("")
        if regressions:
            lines.append("### ❌ Regressions (must be zero)")
            lines.append("")
            for s in regressions:
                lines.append(
                    f"- **{s.path.id}** — {s.path.description} (entry: `{s.path.entry}`)"
                )
            lines.append("")
        if gaps:
            lines.append("### ⚠️ Critical paths not yet covered")
            lines.append("")
            for s in gaps:
                covers = ", ".join(s.path.covered_by) or "_no groups declared_"
                lines.append(
                    f"- **{s.path.id}** — {s.path.description} "
                    f"(entry: `{s.path.entry}`; declared coverage: {covers})"
                )
            lines.append("")
        if covered:
            lines.append("<details><summary>✅ Covered critical paths</summary>")
            lines.append("")
            for s in covered:
                groups_str = ", ".join(s.covering_groups_run)
                lines.append(f"- **{s.path.id}** — covered by {groups_str}")
            lines.append("")
            lines.append("</details>")
            lines.append("")

    return "\n".join(lines)


def _totals(results: list[GroupResult]) -> dict[str, float]:
    return {
        "passed": sum(r.passed for r in results),
        "failed": sum(r.failed for r in results),
        "errors": sum(r.errors for r in results),
        "skipped": sum(r.skipped for r in results),
        "duration": sum(r.duration_seconds for r in results),
    }
