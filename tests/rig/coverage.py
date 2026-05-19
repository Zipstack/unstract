"""Coverage helpers.

Each group runs with its own ``COVERAGE_FILE`` so parallel pytest invocations
don't trample each other. After all groups complete, ``combine_and_report``
merges them into a single ``.coverage`` and emits XML/HTML.
"""

from __future__ import annotations

import subprocess
from pathlib import Path


def coverage_env(group_name: str, reports_dir: Path) -> dict[str, str]:
    """Env vars to scope a group's coverage file under ``reports_dir``."""
    cov_file = reports_dir / f".coverage.{group_name}"
    cov_file.parent.mkdir(parents=True, exist_ok=True)
    return {
        "COVERAGE_FILE": str(cov_file),
    }


def combine_and_report(reports_dir: Path) -> None:
    """Combine all per-group ``.coverage.<group>`` files and emit xml + html."""
    if not any(reports_dir.glob(".coverage.*")):
        return
    target = reports_dir / ".coverage"
    if target.exists():
        target.unlink()
    subprocess.run(
        ["coverage", "combine", *[str(p) for p in reports_dir.glob(".coverage.*")]],
        check=False,
        cwd=reports_dir,
    )
    subprocess.run(["coverage", "xml", "-o", str(reports_dir / "coverage.xml")], check=False, cwd=reports_dir)
    subprocess.run(["coverage", "html", "-d", str(reports_dir / "htmlcov")], check=False, cwd=reports_dir)
