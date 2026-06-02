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


def test_duplicate_path_ids_rejected() -> None:
    """Two paths with the same id silently last-wins in the lookup while both
    still render. Fail at construction instead.
    """
    with pytest.raises(ValueError, match="duplicate critical-path ids"):
        _registry(("p1", ("g1",)), ("p1", ("g2",)))


def test_critical_path_status_rejects_contradictions() -> None:
    """Make the contradictory states unrepresentable."""
    from tests.rig.critical_paths import CriticalPath, CriticalPathStatus

    path = CriticalPath(id="p", description="", entry="", covered_by=("g",))
    with pytest.raises(ValueError, match="covered.*non-empty"):
        CriticalPathStatus(path=path, state="covered", covering_groups_run=())
    with pytest.raises(ValueError, match="empty covering_groups_run"):
        CriticalPathStatus(path=path, state="gap", covering_groups_run=("g",))
    # Valid combinations must not raise.
    CriticalPathStatus(path=path, state="covered", covering_groups_run=("g",))
    CriticalPathStatus(path=path, state="gap", covering_groups_run=())


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

    The "straddling" path is the discriminator: ``covered_by=[unit-g, e2e-g]``
    with only ``unit-g`` in scope must still be IN scope (because at least one
    of its declared groups is). A weaker implementation that checks against
    ``groups_run_green`` would mis-classify it.
    """
    registry = _registry(
        ("unit-path", ("unit-g",)),
        ("e2e-path", ("e2e-g",)),
        ("straddle-path", ("unit-g", "e2e-g")),
    )
    statuses = evaluate(
        registry,
        groups_run_green=set(),  # nothing passed
        baseline={
            "covered_paths": ["unit-path", "e2e-path", "straddle-path"]
        },
        scope_groups={"unit-g"},  # only unit groups in scope this run
    )
    by_id = {s.path.id: s for s in statuses}
    assert by_id["unit-path"].state == "regression"  # fully in scope
    assert by_id["e2e-path"].state == "gap"  # fully out of scope
    assert by_id["straddle-path"].state == "regression"  # partially in scope


def test_in_scope_flag_distinguishes_gap_flavours() -> None:
    """The ``in_scope`` flag on a status is what lets --fail-on-critical-gap
    gate only on coverage that this tier was actually responsible for. An
    out-of-scope gap (e2e path during the unit tier, or a path with no declared
    coverage) must report ``in_scope=False``; an in-scope gap (a declared
    in-tier group that didn't run green) must report ``in_scope=True``.
    """
    registry = _registry(
        ("in-scope", ("unit-g",)),  # declared group is in scope, but not green
        ("e2e-only", ("e2e-g",)),  # declared group is out of scope this run
        ("undeclared", ()),  # no declared coverage anywhere
    )
    statuses = evaluate(
        registry,
        groups_run_green=set(),  # nothing passed → all three are gaps
        baseline=None,
        scope_groups={"unit-g"},
    )
    by_id = {s.path.id: s for s in statuses}
    assert all(s.state == "gap" for s in statuses)
    assert by_id["in-scope"].in_scope is True
    assert by_id["e2e-only"].in_scope is False
    assert by_id["undeclared"].in_scope is False


def test_covered_path_is_in_scope() -> None:
    registry = _registry(("p1", ("g1",)))
    statuses = evaluate(
        registry,
        groups_run_green={"g1"},
        baseline=None,
        scope_groups={"g1"},
    )
    assert statuses[0].state == "covered"
    assert statuses[0].in_scope is True


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
