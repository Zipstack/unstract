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

import json
import xml.etree.ElementTree as ET
from dataclasses import asdict, dataclass
from pathlib import Path

from tests.rig.critical_paths import CriticalPathStatus


@dataclass
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
    def status(self) -> str:
        if self.exit_code == 0 and self.failed == 0 and self.errors == 0:
            return "✅"
        if self.exit_code == 5:  # pytest "no tests collected"
            return "⚪"
        return "❌"


def parse_junit(group_name: str, tier: str, reports_dir: Path) -> GroupResult | None:
    junit_path = reports_dir / group_name / "junit.xml"
    exit_path = reports_dir / group_name / "exit.txt"
    if not junit_path.exists():
        return None
    exit_code = int(exit_path.read_text().strip()) if exit_path.exists() else -1

    tree = ET.parse(junit_path)
    root = tree.getroot()
    # JUnit may wrap suites in <testsuites> or be a single <testsuite>.
    suites = root.findall("testsuite") if root.tag == "testsuites" else [root]
    passed = failed = errors = skipped = 0
    duration = 0.0
    for s in suites:
        total = int(s.attrib.get("tests", "0"))
        f = int(s.attrib.get("failures", "0"))
        e = int(s.attrib.get("errors", "0"))
        sk = int(s.attrib.get("skipped", "0"))
        duration += float(s.attrib.get("time", "0") or 0)
        failed += f
        errors += e
        skipped += sk
        passed += max(total - f - e - sk, 0)

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


def write_summary(
    *,
    reports_dir: Path,
    group_results: list[GroupResult],
    critical_statuses: list[CriticalPathStatus],
) -> None:
    summary_json = reports_dir / "summary.json"
    summary_md = reports_dir / "summary.md"
    combined_md = reports_dir / "combined-test-report.md"

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
            },
            indent=2,
        )
    )

    md = _render_markdown(group_results, critical_statuses)
    summary_md.write_text(md)
    # Keep backward compat with the existing ci-test.yaml step that uploads
    # ``combined-test-report.md`` as a sticky PR comment.
    combined_md.write_text(md)


def _render_markdown(
    group_results: list[GroupResult],
    critical_statuses: list[CriticalPathStatus],
) -> str:
    lines: list[str] = ["# Unstract test results", ""]

    if group_results:
        lines.append("## Per-group results")
        lines.append("")
        lines.append("| Status | Group | Tier | Passed | Failed | Errors | Skipped | Duration (s) |")
        lines.append("|---|---|---|---:|---:|---:|---:|---:|")
        for r in group_results:
            lines.append(
                f"| {r.status} | `{r.name}` | {r.tier} | {r.passed} | {r.failed} | {r.errors} | {r.skipped} | {r.duration_seconds:.1f} |"
            )
        totals = _totals(group_results)
        lines.append(
            f"| | **TOTAL** | | **{totals['passed']}** | **{totals['failed']}** | **{totals['errors']}** | **{totals['skipped']}** | **{totals['duration']:.1f}** |"
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
                lines.append(f"- **{s.path.id}** — {s.path.description} (entry: `{s.path.entry}`)")
            lines.append("")
        if gaps:
            lines.append("### ⚠️ Critical paths not yet covered")
            lines.append("")
            for s in gaps:
                covers = ", ".join(s.path.covered_by) or "_no groups declared_"
                lines.append(
                    f"- **{s.path.id}** — {s.path.description} (entry: `{s.path.entry}`; declared coverage: {covers})"
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
