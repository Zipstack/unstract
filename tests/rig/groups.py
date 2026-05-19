"""Load and validate the ``tests/groups.yaml`` manifest.

The manifest is the single source of truth for what a group is, how to run it,
and what it depends on. Cycles fail at load time. Path existence is checked
unless the group is marked ``optional: true`` (which is how we declare
"placeholder for future tests" without breaking the rig today).
"""

from __future__ import annotations

import graphlib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_MANIFEST = REPO_ROOT / "tests" / "groups.yaml"


@dataclass(frozen=True)
class GroupDefinition:
    name: str
    tier: str  # "unit" | "integration" | "e2e"
    paths: tuple[str, ...]
    runner: str = "pytest"  # "pytest" | "hurl"
    workdir: str = "."
    markers: str | None = None
    pytest_extra: tuple[str, ...] = ()
    env: dict[str, str] = field(default_factory=dict)
    uv_sync_group: str | None = None
    pip_install: tuple[str, ...] = ()
    install_editable: bool = False
    requires_services: tuple[str, ...] = ()
    requires_platform: bool = False
    depends_on: tuple[str, ...] = ()
    critical: bool = False
    timeout_seconds: int = 600
    parallel: bool = True
    optional: bool = False

    def absolute_workdir(self) -> Path:
        return (REPO_ROOT / self.workdir).resolve()

    def absolute_paths(self) -> list[Path]:
        return [(self.absolute_workdir() / p).resolve() for p in self.paths]


@dataclass(frozen=True)
class GroupManifest:
    groups: dict[str, GroupDefinition]

    def get(self, name: str) -> GroupDefinition:
        if name not in self.groups:
            raise KeyError(f"Unknown test group: {name!r}. Run `python -m tests.rig list-groups` to see options.")
        return self.groups[name]

    def names(self) -> list[str]:
        return sorted(self.groups)

    def names_by_tier(self, tier: str) -> list[str]:
        return sorted(n for n, g in self.groups.items() if g.tier == tier)

    def expand(self, selected: list[str]) -> list[str]:
        """Return ``selected`` plus the transitive closure of their ``depends_on``,
        in topological order (dependencies before dependents).
        """
        for name in selected:
            self.get(name)  # raises on unknown
        sorter: graphlib.TopologicalSorter[str] = graphlib.TopologicalSorter()
        seen: set[str] = set()
        frontier = list(selected)
        while frontier:
            name = frontier.pop()
            if name in seen:
                continue
            seen.add(name)
            group = self.get(name)
            sorter.add(name, *group.depends_on)
            for dep in group.depends_on:
                if dep not in seen:
                    frontier.append(dep)
        return list(sorter.static_order())


def load_groups(path: Path | None = None) -> GroupManifest:
    """Parse the YAML manifest and validate it."""
    manifest_path = path or DEFAULT_MANIFEST
    raw = yaml.safe_load(manifest_path.read_text())
    if not isinstance(raw, dict) or "groups" not in raw:
        raise ValueError(f"{manifest_path}: expected top-level `groups:` mapping")

    defaults = raw.get("defaults") or {}
    groups: dict[str, GroupDefinition] = {}
    for name, spec in (raw["groups"] or {}).items():
        groups[name] = _build_group(name, spec, defaults)

    _validate_no_cycles(groups)
    _validate_dep_targets_exist(groups)
    _validate_paths(groups)
    return GroupManifest(groups=groups)


def _build_group(name: str, spec: dict[str, Any], defaults: dict[str, Any]) -> GroupDefinition:
    tier = spec.get("tier")
    if tier not in {"unit", "integration", "e2e"}:
        raise ValueError(f"group {name!r}: `tier` must be unit|integration|e2e (got {tier!r})")
    paths = spec.get("paths") or []
    if not paths:
        raise ValueError(f"group {name!r}: at least one `paths` entry is required")

    return GroupDefinition(
        name=name,
        tier=tier,
        paths=tuple(paths),
        runner=spec.get("runner", defaults.get("runner", "pytest")),
        workdir=spec.get("workdir", "."),
        markers=spec.get("markers"),
        pytest_extra=tuple(spec.get("pytest_extra") or ()),
        env=dict(spec.get("env") or {}),
        uv_sync_group=spec.get("uv_sync_group"),
        pip_install=tuple(spec.get("pip_install") or ()),
        install_editable=bool(spec.get("install_editable", False)),
        requires_services=tuple(spec.get("requires_services") or ()),
        requires_platform=bool(spec.get("requires_platform", False)),
        depends_on=tuple(spec.get("depends_on") or ()),
        critical=bool(spec.get("critical", False)),
        timeout_seconds=int(spec.get("timeout_seconds", defaults.get("timeout_seconds", 600))),
        parallel=bool(spec.get("parallel", defaults.get("parallel", True))),
        optional=bool(spec.get("optional", False)),
    )


def _validate_no_cycles(groups: dict[str, GroupDefinition]) -> None:
    sorter: graphlib.TopologicalSorter[str] = graphlib.TopologicalSorter()
    for name, g in groups.items():
        sorter.add(name, *g.depends_on)
    try:
        sorter.prepare()
    except graphlib.CycleError as exc:
        raise ValueError(f"dependency cycle in groups.yaml: {exc.args[1]}") from exc


def _validate_dep_targets_exist(groups: dict[str, GroupDefinition]) -> None:
    for name, g in groups.items():
        for dep in g.depends_on:
            if dep not in groups:
                raise ValueError(f"group {name!r} depends_on unknown group {dep!r}")


def _validate_paths(groups: dict[str, GroupDefinition]) -> None:
    for name, g in groups.items():
        # The workdir of an optional group may not exist yet (e.g. a placeholder
        # for tests/integration/...). Skip validation but the rig will skip the
        # group at runtime too.
        if g.optional:
            continue
        wd = g.absolute_workdir()
        if not wd.exists():
            raise ValueError(f"group {name!r}: workdir does not exist: {wd}")
        for p in g.absolute_paths():
            # Path may be a directory or a file; just verify it resolves under repo root.
            if not p.exists():
                raise ValueError(f"group {name!r}: test path does not exist: {p}")
