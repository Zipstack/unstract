"""Coverage helpers.

Each group runs with its own ``COVERAGE_FILE`` so parallel pytest invocations
don't trample each other. After all groups complete, ``combine_and_report``
merges them into a single ``.coverage`` and emits XML/HTML.
"""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
import sys
from pathlib import Path

from tests.rig.groups import REPO_ROOT

log = logging.getLogger(__name__)

# Cap each coverage subprocess. Runs after the per-group loop, so per-group
# timeouts don't apply; without this a slow `uv run --with` resolve could hang
# the job to the CI ceiling.
_COVERAGE_TIMEOUT_SECONDS = 300


def _clean_env() -> dict[str, str]:
    """Env for ``uv run`` that drops a leaked ``VIRTUAL_ENV`` (e.g. tox's
    ``.tox/<env>``) so uv resolves the project venv without a mismatch warning.
    """
    env = os.environ.copy()
    env.pop("VIRTUAL_ENV", None)
    env.pop("UV_PROJECT_ENVIRONMENT", None)
    return env


def coverage_env(group_name: str, reports_dir: Path) -> dict[str, str]:
    """Env vars to scope a group's coverage file under ``reports_dir``."""
    cov_file = reports_dir / f".coverage.{group_name}"
    cov_file.parent.mkdir(parents=True, exist_ok=True)
    return {"COVERAGE_FILE": str(cov_file)}


def _coverage_base() -> list[str]:
    """Pick a runner for ``coverage`` that has the package available.

    Prefers ``uv run --with coverage`` so the same dependency-resolution
    strategy as the test runs is used, and ``coverage`` doesn't need to be
    installed in the parent interpreter. Falls back to ``python -m coverage``
    if uv isn't around.
    """
    if shutil.which("uv"):
        return ["uv", "run", "--with", "coverage[toml]", "coverage"]
    return [sys.executable, "-m", "coverage"]


def combine_and_report(reports_dir: Path) -> None:
    """Combine all per-group ``.coverage.<group>`` files and emit xml + html.

    Combine runs in ``reports_dir`` so the .coverage files are colocated; xml
    and html run from ``REPO_ROOT`` so coverage can resolve the original source
    file paths (stored as repo-relative in ``COVERAGE_FILE`` thanks to
    ``[tool.coverage.run].relative_files = true``).

    Errors are logged (not raised) because a coverage failure shouldn't drop
    the test run's exit code.
    """
    files = sorted(reports_dir.glob(".coverage.*"))
    if not files:
        return

    target = reports_dir / ".coverage"
    if target.exists():
        target.unlink()

    base = _coverage_base()
    clean_env = _clean_env()
    if not _run_coverage(
        [*base, "combine", *[str(p) for p in files]],
        cwd=reports_dir,
        env=clean_env,
    ):
        return

    combined = reports_dir / ".coverage"
    xml_cmd = [
        *base,
        "xml",
        "--data-file",
        str(combined),
        "-o",
        str(reports_dir / "coverage.xml"),
    ]
    html_cmd = [
        *base,
        "html",
        "--data-file",
        str(combined),
        "-d",
        str(reports_dir / "htmlcov"),
    ]
    for cmd in (xml_cmd, html_cmd):
        _run_coverage(cmd, cwd=REPO_ROOT, env=clean_env)


def _run_coverage(cmd: list[str], *, cwd: Path, env: dict[str, str]) -> bool:
    """Run a coverage subprocess with a timeout. Returns True on success.

    A timeout is essential: ``uv run --with coverage[toml]`` can resolve over a
    slow index, and this runs AFTER the per-group loop so the rig's per-group
    timeouts don't apply — without a cap it could hang the job to the CI limit.
    Failures are logged, not raised (coverage is best-effort reporting).
    """
    try:
        result = subprocess.run(
            cmd,
            cwd=cwd,
            capture_output=True,
            text=True,
            env=env,
            timeout=_COVERAGE_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired:
        log.warning(
            "coverage step timed out after %ds: %s",
            _COVERAGE_TIMEOUT_SECONDS,
            " ".join(cmd),
        )
        return False
    if result.returncode != 0:
        log.warning(
            "%s failed (exit %d): %s",
            " ".join(cmd),
            result.returncode,
            (result.stderr or result.stdout).strip(),
        )
        return False
    return True
