"""Load and validate the ``tests/groups.yaml`` manifest.

The manifest is the single source of truth for what a group is, how to run it,
and what it depends on. Cycles fail at load time. Path existence is checked
unless the group is marked ``optional: true`` (which is how we declare
"placeholder for future tests" without breaking the rig today).
"""

from __future__ import annotations

import graphlib
import os
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from types import MappingProxyType
from typing import Any, Literal, get_args

import yaml

Tier = Literal["unit", "integration", "e2e"]
Runner = Literal["pytest", "hurl"]

TIERS: tuple[Tier, ...] = get_args(Tier)
RUNNERS: tuple[Runner, ...] = get_args(Runner)

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_MANIFEST = REPO_ROOT / "tests" / "groups.yaml"

# os.pathsep-separated overlay manifests, so a downstream repo can contribute
# groups without editing the base manifest.
EXTRA_MANIFESTS_ENV = "UNSTRACT_RIG_EXTRA_MANIFESTS"


@dataclass(frozen=True)
class MigrateSpec:
    """A ``manage.py migrate`` run against the rig-provisioned database.

    Schema belongs to the database, not to any one group, so this is declared
    once per manifest and applied when the rig provisions Postgres. Applying the
    real migrations (rather than hand-written DDL in a fixture) keeps the
    throwaway schema identical to the one the models generate, so tests that
    assert on constraints stay meaningful.
    """

    workdir: str
    apps: tuple[str, ...] = ()
    env: Mapping[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not isinstance(self.env, MappingProxyType):
            object.__setattr__(self, "env", MappingProxyType(dict(self.env)))

    def absolute_workdir(self) -> Path:
        return (REPO_ROOT / self.workdir).resolve()


@dataclass(frozen=True)
class GroupDefinition:
    name: str
    tier: Tier
    paths: tuple[str, ...]
    runner: Runner = "pytest"
    workdir: str = "."
    markers: str | None = None
    pytest_extra: tuple[str, ...] = ()
    env: Mapping[str, str] = field(default_factory=dict)
    uv_sync_group: str | None = None
    pip_install: tuple[str, ...] = ()
    install_editable: bool = False
    requires_services: tuple[str, ...] = ()
    requires_platform: bool = False
    depends_on: tuple[str, ...] = ()
    critical: bool = False
    coverage_source: str | None = None
    timeout_seconds: int = 600
    parallel: bool = True
    optional: bool = False

    def __post_init__(self) -> None:
        # Freeze env: a frozen dataclass with a mutable dict still lets callers
        # scribble onto the shared manifest record (group.env[k] = v). Coerce
        # to a read-only proxy so the record is genuinely immutable.
        if not isinstance(self.env, MappingProxyType):
            object.__setattr__(self, "env", MappingProxyType(dict(self.env)))

    def absolute_workdir(self) -> Path:
        return (REPO_ROOT / self.workdir).resolve()

    def absolute_paths(self) -> list[Path]:
        return [(self.absolute_workdir() / p).resolve() for p in self.paths]


@dataclass(frozen=True)
class GroupManifest:
    groups: dict[str, GroupDefinition]
    # Applied once, when the rig provisions Postgres — see `postgres_migrate`
    # in the manifest defaults.
    postgres_migrate: MigrateSpec | None = None

    def get(self, name: str) -> GroupDefinition:
        if name not in self.groups:
            raise KeyError(
                f"Unknown test group: {name!r}. "
                "Run `python -m tests.rig list-groups` to see options."
            )
        return self.groups[name]

    def names(self) -> list[str]:
        return sorted(self.groups)

    def names_by_tier(self, tier: Tier) -> list[str]:
        return sorted(n for n, g in self.groups.items() if g.tier == tier)

    def transitive_deps(self, name: str) -> set[str]:
        """Return every group ``name`` depends on, directly or otherwise."""
        self.get(name)  # raises on unknown
        deps: set[str] = set()
        frontier = [name]
        while frontier:
            for dep in self.get(frontier.pop()).depends_on:
                if dep not in deps:
                    deps.add(dep)
                    frontier.append(dep)
        return deps

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
    raw = _load_manifest_dict(manifest_path)

    defaults = raw.get("defaults") or {}
    groups: dict[str, GroupDefinition] = {}
    for name, spec in (raw["groups"] or {}).items():
        groups[name] = _build_group(name, spec, defaults)

    # Merge before validation so cross-manifest `depends_on` and the platform
    # gate are checked over the union. Keyed on `path` being omitted rather than
    # on its value: an explicit path means "load exactly this", however spelled.
    if path is None:
        for extra in _extra_manifest_paths():
            defaults = _merge_manifest(groups, extra, defaults)

    _validate_no_cycles(groups)
    _validate_dep_targets_exist(groups)
    _validate_paths(groups)
    smoke_gate = defaults.get("platform_gate_group", "e2e-smoke")
    _validate_platform_groups_depend_on_gate(groups, gate=smoke_gate)
    return GroupManifest(
        groups=groups,
        postgres_migrate=_build_postgres_migrate(defaults.get("postgres_migrate")),
    )


def _extra_manifest_paths() -> list[Path]:
    """Overlay manifest paths from ``UNSTRACT_RIG_EXTRA_MANIFESTS``.

    Relative paths resolve against ``REPO_ROOT`` so a downstream repo can point
    at a manifest it copied into this tree (e.g. ``tests/groups.cloud.yaml``).
    """
    raw = os.environ.get(EXTRA_MANIFESTS_ENV, "").strip()
    if not raw:
        return []
    paths: list[Path] = []
    for entry in filter(None, (e.strip() for e in raw.split(os.pathsep))):
        p = Path(entry)
        p = p if p.is_absolute() else REPO_ROOT / p
        # Name the env var — a bare FileNotFoundError won't say where the path
        # came from.
        if not p.is_file():
            raise ValueError(
                f"{EXTRA_MANIFESTS_ENV}: {entry!r} is not a file (resolved to {p})"
            )
        paths.append(p)
    return paths


def _load_manifest_dict(manifest_path: Path) -> dict[str, Any]:
    """Parse a manifest YAML, rejecting anything that is not a ``groups:`` mapping."""
    if not manifest_path.is_file():
        raise ValueError(f"{manifest_path}: manifest file not found")
    raw = yaml.safe_load(manifest_path.read_text())
    if not isinstance(raw, dict) or not isinstance(raw.get("groups"), dict):
        raise ValueError(f"{manifest_path}: expected top-level `groups:` mapping")
    return raw


def _merge_manifest(
    groups: dict[str, GroupDefinition], manifest_path: Path, base_defaults: dict[str, Any]
) -> dict[str, Any]:
    """Merge an overlay manifest into ``groups`` in place and return the merged
    defaults, so an overlay can also rename the platform gate. Overlay groups
    inherit the base ``defaults`` unless they declare their own; a name collision
    is an error rather than a silent override.
    """
    raw = _load_manifest_dict(manifest_path)
    defaults = {**base_defaults, **(raw.get("defaults") or {})}
    for name, spec in (raw["groups"] or {}).items():
        if name in groups:
            raise ValueError(
                f"{manifest_path}: group {name!r} already defined in a prior manifest"
            )
        groups[name] = _build_group(name, spec, defaults)
    return defaults


def _build_group(
    name: str, spec: dict[str, Any], defaults: dict[str, Any]
) -> GroupDefinition:
    tier = spec.get("tier")
    if tier not in TIERS:
        raise ValueError(f"group {name!r}: `tier` must be one of {TIERS} (got {tier!r})")
    runner = spec.get("runner", defaults.get("runner", "pytest"))
    if runner not in RUNNERS:
        raise ValueError(
            f"group {name!r}: `runner` must be one of {RUNNERS} (got {runner!r})"
        )
    paths = spec.get("paths") or []
    if not paths:
        raise ValueError(f"group {name!r}: at least one `paths` entry is required")
    try:
        timeout = int(spec.get("timeout_seconds", defaults.get("timeout_seconds", 600)))
    except (TypeError, ValueError) as exc:
        raise ValueError(
            f"group {name!r}: `timeout_seconds` must be an integer "
            f"(got {spec.get('timeout_seconds')!r})"
        ) from exc

    return GroupDefinition(
        name=name,
        tier=tier,
        paths=tuple(paths),
        runner=runner,
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
        coverage_source=spec.get("coverage_source"),
        timeout_seconds=timeout,
        parallel=bool(spec.get("parallel", defaults.get("parallel", True))),
        optional=bool(spec.get("optional", False)),
    )


def _build_postgres_migrate(spec: Any) -> MigrateSpec | None:
    """Parse and validate ``defaults.postgres_migrate``.

    A bad spec is a silent no-show at runtime — every DB-backed test skips on a
    missing table — so both the shape and the ``manage.py`` are checked at load.
    """
    if spec is None:
        return None
    if not isinstance(spec, dict) or not spec.get("workdir"):
        raise ValueError(
            f"`defaults.postgres_migrate` must be a mapping with a `workdir` "
            f"(got {spec!r})"
        )
    migrate = MigrateSpec(
        workdir=spec["workdir"],
        apps=tuple(spec.get("apps") or ()),
        env=dict(spec.get("env") or {}),
    )
    manage_py = migrate.absolute_workdir() / "manage.py"
    if not manage_py.is_file():
        raise ValueError(
            f"`defaults.postgres_migrate.workdir` has no manage.py: {manage_py}"
        )
    return migrate


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
        # Optional groups may be placeholders whose paths don't exist yet.
        # The rig skips them at runtime; don't fail validation here.
        if g.optional:
            continue
        wd = g.absolute_workdir()
        if not wd.exists():
            raise ValueError(f"group {name!r}: workdir does not exist: {wd}")
        for p in g.absolute_paths():
            if not p.exists():
                raise ValueError(f"group {name!r}: test path does not exist: {p}")


def _validate_platform_groups_depend_on_gate(
    groups: dict[str, GroupDefinition], *, gate: str
) -> None:
    """Every non-gate ``requires_platform`` group must transitively depend on
    the named gate group. This is a *structural* invariant on the dependency
    graph: it guarantees the manifest can never ship a platform test that
    bypasses the smoke gate, and that the gate runs first in topological order.

    Runtime skip-on-gate-failure is enforced separately: ``cmd_run`` tracks
    failed groups and skips (blocks) any dependent whose transitive deps
    include one, so a red gate stops its dependents from running against a
    half-up stack. This structural check guarantees the graph such tracking
    relies on is actually wired.

    If the manifest declares ``requires_platform`` groups but doesn't actually
    define the gate, that's a manifest error — silently disabling the check
    would defeat the invariant. The gate name is overridable via
    ``defaults.platform_gate_group`` in ``groups.yaml`` for forks that rename it.
    """
    platform_groups = [n for n, g in groups.items() if g.requires_platform and n != gate]
    if not platform_groups:
        return  # No platform-dependent groups; nothing to enforce.
    if gate not in groups:
        raise ValueError(
            f"`requires_platform` groups present ({sorted(platform_groups)}) "
            f"but the platform gate {gate!r} is not defined. Either define it, "
            f"or set `defaults.platform_gate_group` in groups.yaml."
        )
    for name in platform_groups:
        if not _transitively_depends_on(name, gate, groups):
            raise ValueError(
                f"group {name!r} requires_platform but does not (transitively) "
                f"depend on {gate!r}; add it to depends_on so smoke gates this group"
            )


def _transitively_depends_on(
    name: str, target: str, groups: dict[str, GroupDefinition]
) -> bool:
    seen: set[str] = set()
    frontier = [name]
    while frontier:
        current = frontier.pop()
        if current in seen:
            continue
        seen.add(current)
        for dep in groups[current].depends_on:
            if dep == target:
                return True
            frontier.append(dep)
    return False
