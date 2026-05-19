"""Self-tests for the rig's manifest loader and dep-graph expansion."""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.rig.groups import load_groups


def _write_manifest(tmp_path: Path, body: str) -> Path:
    p = tmp_path / "groups.yaml"
    p.write_text(body)
    return p


def test_cycle_detection(tmp_path: Path) -> None:
    manifest = _write_manifest(
        tmp_path,
        """
        version: 1
        groups:
          a:
            tier: unit
            paths: [x]
            depends_on: [b]
            optional: true
          b:
            tier: unit
            paths: [y]
            depends_on: [a]
            optional: true
        """,
    )
    with pytest.raises(ValueError, match="cycle"):
        load_groups(manifest)


def test_unknown_dep_target(tmp_path: Path) -> None:
    manifest = _write_manifest(
        tmp_path,
        """
        version: 1
        groups:
          a:
            tier: unit
            paths: [x]
            depends_on: [does-not-exist]
            optional: true
        """,
    )
    with pytest.raises(ValueError, match="unknown group"):
        load_groups(manifest)


def test_expand_topological_order(tmp_path: Path) -> None:
    manifest = _write_manifest(
        tmp_path,
        """
        version: 1
        groups:
          leaf:
            tier: unit
            paths: [x]
            optional: true
          mid:
            tier: unit
            paths: [x]
            depends_on: [leaf]
            optional: true
          root:
            tier: e2e
            paths: [x]
            depends_on: [mid]
            optional: true
        """,
    )
    expanded = load_groups(manifest).expand(["root"])
    assert expanded == ["leaf", "mid", "root"]


def test_invalid_tier_rejected(tmp_path: Path) -> None:
    manifest = _write_manifest(
        tmp_path,
        """
        version: 1
        groups:
          a:
            tier: bogus
            paths: [x]
            optional: true
        """,
    )
    with pytest.raises(ValueError, match="tier"):
        load_groups(manifest)


def test_invalid_runner_rejected(tmp_path: Path) -> None:
    manifest = _write_manifest(
        tmp_path,
        """
        version: 1
        groups:
          a:
            tier: unit
            runner: cargo-test
            paths: [x]
            optional: true
        """,
    )
    with pytest.raises(ValueError, match="runner"):
        load_groups(manifest)


def test_platform_group_must_depend_on_smoke(tmp_path: Path) -> None:
    manifest = _write_manifest(
        tmp_path,
        """
        version: 1
        groups:
          e2e-smoke:
            tier: e2e
            paths: [x]
            requires_platform: true
            optional: true
          e2e-rogue:
            tier: e2e
            paths: [x]
            requires_platform: true
            optional: true
        """,
    )
    with pytest.raises(ValueError, match="depend on 'e2e-smoke'"):
        load_groups(manifest)


def test_platform_groups_without_gate_definition_fails(tmp_path: Path) -> None:
    """If a manifest declares platform groups but never defines the gate
    (``e2e-smoke`` by default), validation must fail — silently no-oping the
    smoke-gate check would defeat the whole invariant.
    """
    manifest = _write_manifest(
        tmp_path,
        """
        version: 1
        groups:
          e2e-orphan:
            tier: e2e
            paths: [x]
            requires_platform: true
            optional: true
        """,
    )
    with pytest.raises(ValueError, match="platform gate 'e2e-smoke' is not defined"):
        load_groups(manifest)


def test_custom_gate_name_via_defaults(tmp_path: Path) -> None:
    """Forks can rename the gate via defaults.platform_gate_group."""
    manifest = _write_manifest(
        tmp_path,
        """
        version: 1
        defaults:
          platform_gate_group: my-custom-smoke
        groups:
          my-custom-smoke:
            tier: e2e
            paths: [x]
            requires_platform: true
            optional: true
          downstream:
            tier: e2e
            paths: [x]
            requires_platform: true
            depends_on: [my-custom-smoke]
            optional: true
        """,
    )
    # Must not raise.
    assert "downstream" in load_groups(manifest).names()


def test_real_manifest_is_valid() -> None:
    """The committed groups.yaml + critical_paths.yaml must always pass loading."""
    manifest = load_groups()
    assert "e2e-smoke" in manifest.names()
    # Every platform group depends transitively on smoke.
    for name in manifest.names():
        g = manifest.get(name)
        if name != "e2e-smoke" and g.requires_platform:
            assert "e2e-smoke" in manifest.expand([name])
