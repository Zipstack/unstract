"""Self-tests for coverage combining across sequential tier invocations.

The rig runs each tier as a separate process (``tox -e unit`` then
``tox -e integration``), and each invocation calls ``combine_and_report``.
Because ``coverage combine`` consumes its inputs, a naive fresh combine of
only the current tier's ``.coverage.*`` files would discard the prior tier's
merged data — see ``combine_and_report``'s docstring. These tests lock in the
union-across-tiers behavior so a future refactor can't silently reintroduce
the loss.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from tests.rig.coverage import combine_and_report

# `coverage` is a rig dependency, but skip cleanly if a bare interpreter is
# running just these tests without it installed.
coverage = pytest.importorskip("coverage")


def _write_coverage_file(path: Path, line_data: dict[str, list[int]]) -> None:
    """Construct a ``.coverage`` data file with known line coverage.

    Uses the ``CoverageData`` API directly (faster and less flaky than
    spawning pytest --cov against a stub module). ``relative_files`` mirrors
    the project's ``[tool.coverage.run]`` setting so the merged paths line up.
    """
    data = coverage.CoverageData(basename=str(path))
    data.add_lines(line_data)
    data.write()


def _measured_lines(coverage_file: Path) -> dict[str, set[int]]:
    """Read a ``.coverage`` file back into ``{filename: {lines}}``."""
    data = coverage.CoverageData(basename=str(coverage_file))
    data.read()
    return {f: set(data.lines(f) or []) for f in data.measured_files()}


@pytest.mark.skipif(shutil.which("uv") is None, reason="needs uv or coverage on PATH")
def test_combine_preserves_prior_tier_data(tmp_path: Path) -> None:
    """Two sequential ``combine_and_report`` calls (tier 1 then tier 2) must
    yield a ``.coverage`` reflecting the UNION of both tiers' line data, not
    just the last tier's. This is the exact regression Greptile flagged: tier
    1's merged ``.coverage`` was being unlinked before tier 2's combine.
    """
    reports = tmp_path / "reports"
    reports.mkdir()

    # Tier 1: one group covering mod_a lines 1-3.
    _write_coverage_file(reports / ".coverage.unit-x", {"mod_a.py": [1, 2, 3]})
    combine_and_report(reports)

    combined_after_t1 = _measured_lines(reports / ".coverage")
    assert combined_after_t1.get("mod_a.py") == {1, 2, 3}

    # Tier 2: a fresh process, a different group covering mod_b lines 10-11.
    # Its `.coverage.*` is new; the prior `.coverage` from tier 1 is on disk.
    _write_coverage_file(reports / ".coverage.integration-y", {"mod_b.py": [10, 11]})
    combine_and_report(reports)

    combined_after_t2 = _measured_lines(reports / ".coverage")
    assert combined_after_t2.get("mod_a.py") == {1, 2, 3}, (
        f"tier 1 coverage must survive tier 2's combine; got {combined_after_t2}"
    )
    assert combined_after_t2.get("mod_b.py") == {10, 11}, (
        f"tier 2 coverage must be present; got {combined_after_t2}"
    )


@pytest.mark.skipif(shutil.which("uv") is None, reason="needs uv or coverage on PATH")
def test_combine_unions_same_file_across_tiers(tmp_path: Path) -> None:
    """When two tiers cover DIFFERENT lines of the SAME file, the merged result
    must be the union of the line sets (coverage's own merge semantics), not a
    last-writer-wins overwrite.
    """
    reports = tmp_path / "reports"
    reports.mkdir()

    _write_coverage_file(reports / ".coverage.unit-x", {"mod.py": [1, 2]})
    combine_and_report(reports)
    _write_coverage_file(reports / ".coverage.integration-y", {"mod.py": [3, 4]})
    combine_and_report(reports)

    merged = _measured_lines(reports / ".coverage")
    assert merged.get("mod.py") == {1, 2, 3, 4}, f"expected union; got {merged}"


def test_combine_no_files_is_noop(tmp_path: Path) -> None:
    """No ``.coverage.*`` and no prior ``.coverage`` → nothing to do, no error,
    no file created.
    """
    reports = tmp_path / "reports"
    reports.mkdir()
    combine_and_report(reports)
    assert not (reports / ".coverage").exists()
    assert not (reports / "coverage.xml").exists()


@pytest.mark.skipif(shutil.which("uv") is None, reason="needs uv or coverage on PATH")
def test_combine_idempotent_with_only_prior_data(tmp_path: Path) -> None:
    """The CI flow combines once per tier in ``cmd_run`` and then once more in
    ``cmd_report`` (``tox -e rig -- report combine``). By that final call all
    per-group ``.coverage.*`` files have been consumed, so the only input is
    the carried-forward ``.coverage``. Re-combining must be a stable no-op on
    the data — not wipe it.
    """
    reports = tmp_path / "reports"
    reports.mkdir()

    _write_coverage_file(reports / ".coverage.unit-x", {"mod_a.py": [1, 2, 3]})
    combine_and_report(reports)
    # No new tier files; second call sees only the prior `.coverage`.
    combine_and_report(reports)

    merged = _measured_lines(reports / ".coverage")
    assert merged.get("mod_a.py") == {1, 2, 3}, (
        f"re-combine with only prior data must preserve it; got {merged}"
    )
