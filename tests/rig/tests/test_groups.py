"""Self-tests for the rig's manifest loader and dep-graph expansion."""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.rig.groups import GroupDefinition, load_groups


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


def test_transitive_deps_reaches_indirect_dependencies(tmp_path: Path) -> None:
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
    loaded = load_groups(manifest)
    # Indirect deps count: a red `leaf` must be able to block `root`.
    assert loaded.transitive_deps("root") == {"mid", "leaf"}
    assert loaded.transitive_deps("leaf") == set()


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


def test_group_env_is_frozen() -> None:
    """A frozen GroupDefinition with a mutable env dict still lets callers
    scribble onto the shared record. __post_init__ coerces to a read-only
    proxy so that's no longer possible.
    """
    group = GroupDefinition(
        name="g", tier="unit", paths=("x",), env={"A": "1"}
    )
    assert group.env["A"] == "1"
    with pytest.raises(TypeError):
        group.env["B"] = "2"  # type: ignore[index]


def _base_manifest(tmp_path: Path) -> Path:
    return _write_manifest(
        tmp_path,
        """
        version: 1
        groups:
          unit-base:
            tier: unit
            paths: [x]
            optional: true
        """,
    )


def _overlay_env(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, body: str
) -> Path:
    """Point the loader's default manifest at a fixture and register an overlay.

    Overlays only apply to the default manifest, so the tests drive that path
    rather than passing an explicit one.
    """
    base = _base_manifest(tmp_path)
    overlay = tmp_path / "groups.cloud.yaml"
    overlay.write_text(body)
    monkeypatch.setattr("tests.rig.groups.DEFAULT_MANIFEST", base)
    monkeypatch.setenv("UNSTRACT_RIG_EXTRA_MANIFESTS", str(overlay))
    return base


def test_extra_manifest_merged(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _overlay_env(
        tmp_path,
        monkeypatch,
        """
        version: 1
        groups:
          unit-cloud:
            tier: unit
            paths: [y]
            depends_on: [unit-base]
            optional: true
        """,
    )
    manifest = load_groups()
    assert "unit-cloud" in manifest.names()
    # Cross-manifest depends_on resolves against the merged set.
    assert "unit-base" in manifest.expand(["unit-cloud"])


def test_extra_manifest_name_collision_rejected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _overlay_env(
        tmp_path,
        monkeypatch,
        """
        version: 1
        groups:
          unit-base:
            tier: unit
            paths: [y]
            optional: true
        """,
    )
    with pytest.raises(ValueError, match="already defined"):
        load_groups()


def test_explicit_manifest_ignores_overlays(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An ad-hoc manifest must not absorb a downstream repo's overlay."""
    base = _base_manifest(tmp_path)
    overlay = tmp_path / "groups.cloud.yaml"
    overlay.write_text(
        """
        version: 1
        groups:
          unit-cloud:
            tier: unit
            paths: [y]
            optional: true
        """
    )
    monkeypatch.setenv("UNSTRACT_RIG_EXTRA_MANIFESTS", str(overlay))
    # `base` is deliberately not the default manifest here.
    assert "unit-cloud" not in load_groups(base).names()


def test_extra_manifest_defaults_applied(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An overlay's own `defaults` reach its groups instead of being dropped."""
    _overlay_env(
        tmp_path,
        monkeypatch,
        """
        version: 1
        defaults:
          parallel: false
          timeout_seconds: 42
        groups:
          unit-cloud:
            tier: unit
            paths: [y]
            optional: true
        """,
    )
    group = load_groups().get("unit-cloud")
    assert group.parallel is False
    assert group.timeout_seconds == 42


def test_extra_manifest_malformed_rejected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _overlay_env(tmp_path, monkeypatch, "- not: a-mapping\n")
    with pytest.raises(ValueError, match="expected top-level `groups:` mapping"):
        load_groups()


def test_extra_manifest_missing_path_names_env_var(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    base = _base_manifest(tmp_path)
    monkeypatch.setattr("tests.rig.groups.DEFAULT_MANIFEST", base)
    monkeypatch.setenv("UNSTRACT_RIG_EXTRA_MANIFESTS", str(tmp_path / "nope.yaml"))
    with pytest.raises(ValueError, match="UNSTRACT_RIG_EXTRA_MANIFESTS"):
        load_groups()
