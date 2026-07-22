"""Self-tests for selection resolution: union vs. intersect, dep expansion."""

from __future__ import annotations

from pathlib import Path

from tests.rig.groups import load_groups
from tests.rig.selection import resolve


def _manifest(tmp_path: Path) -> Path:
    p = tmp_path / "groups.yaml"
    p.write_text(
        """
        version: 1
        groups:
          unit-a:
            tier: unit
            paths: [x]
            optional: true
          unit-b:
            tier: unit
            paths: [x]
            optional: true
          e2e-smoke:
            tier: e2e
            paths: [x]
            requires_platform: true
            optional: true
          e2e-other:
            tier: e2e
            paths: [x]
            requires_platform: true
            depends_on: [e2e-smoke]
            optional: true
        """
    )
    return p


def test_positional_group_expands_deps(tmp_path: Path) -> None:
    manifest = load_groups(_manifest(tmp_path))
    ordered = resolve(manifest, positional=["e2e-other"])
    assert ordered == ["e2e-smoke", "e2e-other"]


def test_empty_selection_returns_empty_list(tmp_path: Path) -> None:
    """No positional, no file, no tier → must NOT default to 'run everything'.
    The CLI relies on this to fail loudly rather than surprise the user.
    """
    manifest = load_groups(_manifest(tmp_path))
    assert resolve(manifest, positional=[]) == []


def test_from_file_merges_with_positional(tmp_path: Path) -> None:
    manifest = load_groups(_manifest(tmp_path))
    selection_file = tmp_path / "selection"
    selection_file.write_text("unit-b\n# a comment line\n\nunit-a\n")
    ordered = resolve(
        manifest, positional=["e2e-smoke"], from_file=selection_file
    )
    assert set(ordered) == {"unit-a", "unit-b", "e2e-smoke"}


def test_all_plus_tier_intersects(tmp_path: Path) -> None:
    """`tox -e e2e -- all` historically expanded `all` to every group and let
    the tier env name lie about the scope. The rig now intersects when both
    are supplied so the env name matches what actually runs.
    """
    manifest = load_groups(_manifest(tmp_path))
    ordered = resolve(manifest, positional=["all"], tier="e2e")
    assert set(ordered) == {"e2e-smoke", "e2e-other"}


def test_tier_only_selects_that_tier_and_deps(tmp_path: Path) -> None:
    manifest = load_groups(_manifest(tmp_path))
    ordered = resolve(manifest, positional=[], tier="unit")
    assert set(ordered) == {"unit-a", "unit-b"}


def _cross_tier_manifest(tmp_path: Path) -> Path:
    p = tmp_path / "groups.yaml"
    p.write_text(
        """
        version: 1
        groups:
          unit-a:
            tier: unit
            paths: [x]
            optional: true
          e2e-smoke:
            tier: e2e
            paths: [x]
            requires_platform: true
            optional: true
          e2e-cross:
            tier: e2e
            paths: [x]
            requires_platform: true
            depends_on: [e2e-smoke, unit-a]
            optional: true
        """
    )
    return p


def test_tier_run_does_not_pull_in_other_tiers(tmp_path: Path) -> None:
    """Each tier is its own CI leg; a cross-tier dep must not re-run there."""
    manifest = load_groups(_cross_tier_manifest(tmp_path))
    ordered = resolve(manifest, positional=[], tier="e2e")
    assert set(ordered) == {"e2e-smoke", "e2e-cross"}
    assert ordered.index("e2e-smoke") < ordered.index("e2e-cross")


def test_explicitly_named_group_survives_tier_filter(tmp_path: Path) -> None:
    """The filter only drops dep-expanded groups, never an explicit request."""
    manifest = load_groups(_cross_tier_manifest(tmp_path))
    ordered = resolve(manifest, positional=["unit-a"], tier="e2e")
    assert set(ordered) == {"unit-a", "e2e-smoke", "e2e-cross"}


def test_cross_tier_dep_still_expands_without_tier_filter(tmp_path: Path) -> None:
    manifest = load_groups(_cross_tier_manifest(tmp_path))
    ordered = resolve(manifest, positional=["e2e-cross"])
    assert set(ordered) == {"unit-a", "e2e-smoke", "e2e-cross"}
