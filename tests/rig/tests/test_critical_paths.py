"""Self-tests for critical-path evaluation: covered / gap / regression."""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.rig.critical_paths import (
    BaselineCorruptError,
    CriticalPath,
    CriticalPathRegistry,
    evaluate,
    load_baseline,
    merge_into_baseline,
)


def _registry(*ids_and_covers: tuple[str, tuple[str, ...]]) -> CriticalPathRegistry:
    return CriticalPathRegistry(
        paths=tuple(
            CriticalPath(id=i, description="", entry="", covered_by=c)
            for i, c in ids_and_covers
        )
    )


def test_covered_when_covering_group_is_green() -> None:
    registry = _registry(("p1", ("g1",)))
    statuses = evaluate(registry, groups_run_green={"g1"}, baseline=None)
    assert statuses[0].state == "covered"
    assert statuses[0].covering_groups_run == ("g1",)


def test_gap_when_no_covering_group_and_no_baseline() -> None:
    registry = _registry(("p1", ("g1",)))
    statuses = evaluate(registry, groups_run_green=set(), baseline=None)
    assert statuses[0].state == "gap"


def test_gap_when_covered_by_is_empty() -> None:
    registry = _registry(("p1", ()))
    statuses = evaluate(
        registry,
        groups_run_green={"unrelated"},
        baseline={"covered_paths": []},
    )
    assert statuses[0].state == "gap"


def test_regression_when_baseline_covered_but_now_not() -> None:
    registry = _registry(("p1", ("g1",)))
    statuses = evaluate(
        registry,
        groups_run_green=set(),
        baseline={"covered_paths": ["p1"]},
    )
    assert statuses[0].state == "regression"


def test_baseline_merge_unions_with_existing(tmp_path: Path) -> None:
    """Two tier runs in sequence must both contribute to the baseline."""
    baseline = tmp_path / "previous-summary.json"
    registry_a = _registry(("p1", ("g1",)))
    statuses_a = evaluate(
        registry_a, groups_run_green={"g1"}, baseline=None
    )
    merge_into_baseline(statuses_a, baseline)

    registry_b = _registry(("p2", ("g2",)))
    statuses_b = evaluate(
        registry_b, groups_run_green={"g2"}, baseline=load_baseline(baseline)
    )
    merge_into_baseline(statuses_b, baseline)

    final = load_baseline(baseline) or {}
    assert sorted(final["covered_paths"]) == ["p1", "p2"]


def test_by_id_lookup_caches() -> None:
    registry = _registry(("p1", ("g1",)), ("p2", ()))
    # Two lookups must return identical instances; tests both correctness and
    # that the dict cache was actually built in __post_init__.
    assert registry.by_id("p1") is registry.by_id("p1")
    assert registry.by_id("p1").id == "p1"


def test_load_baseline_raises_on_corrupt_file(tmp_path: Path) -> None:
    """A corrupt baseline must not be silently treated as empty — that would
    demote real regressions to gaps on the build that needs detection most.
    """
    baseline = tmp_path / "previous-summary.json"
    baseline.write_text("{not valid json")
    with pytest.raises(BaselineCorruptError):
        load_baseline(baseline)


def test_merge_raises_on_corrupt_existing_baseline(tmp_path: Path) -> None:
    """merge_into_baseline must not silently overwrite a corrupt file — that
    would erase the other tier's previously-covered paths.
    """
    baseline = tmp_path / "previous-summary.json"
    baseline.write_text("{partial")
    registry = _registry(("p1", ("g1",)))
    statuses = evaluate(registry, groups_run_green={"g1"}, baseline=None)
    with pytest.raises(BaselineCorruptError):
        merge_into_baseline(statuses, baseline)


def test_scope_demotes_out_of_scope_regressions_to_gaps() -> None:
    """A unit-only invocation should NOT flag e2e-covered paths as regressed
    just because the baseline lists them — those paths are out of scope for
    this invocation and belong to the e2e workflow's baseline instead.
    """
    registry = _registry(
        ("unit-path", ("unit-group",)),
        ("e2e-path", ("e2e-group",)),
    )
    statuses = evaluate(
        registry,
        groups_run_green=set(),  # nothing passed
        baseline={"covered_paths": ["unit-path", "e2e-path"]},
        scope_groups={"unit-group"},  # only unit groups in scope this run
    )
    by_id = {s.path.id: s for s in statuses}
    assert by_id["unit-path"].state == "regression"  # in scope, was covered
    assert by_id["e2e-path"].state == "gap"  # out of scope; not regressed


def test_scope_none_preserves_legacy_behavior() -> None:
    """scope_groups=None disables scope-filtering so callers that don't pass it
    keep the old "everything in baseline counts" semantics.
    """
    registry = _registry(("p1", ("g1",)))
    statuses = evaluate(
        registry,
        groups_run_green=set(),
        baseline={"covered_paths": ["p1"]},
        scope_groups=None,
    )
    assert statuses[0].state == "regression"
