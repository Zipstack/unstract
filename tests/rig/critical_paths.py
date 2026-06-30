"""Load ``tests/critical_paths.yaml`` and compute gaps + regressions."""

from __future__ import annotations

import json
import logging
from collections.abc import Collection
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

import yaml

from tests.rig.groups import REPO_ROOT, GroupManifest

log = logging.getLogger(__name__)

CriticalPathState = Literal["covered", "gap", "regression"]

DEFAULT_REGISTRY = REPO_ROOT / "tests" / "critical_paths.yaml"


class BaselineCorruptError(RuntimeError):
    """Raised when the baseline file exists but cannot be parsed.

    The rig refuses to silently treat a corrupt baseline as empty because that
    would (a) demote real regressions to gaps and (b) wipe the other tier's
    coverage on the next merge. The CI workflow should delete the cache and
    retry, surfacing the corruption explicitly.
    """


@dataclass(frozen=True)
class CriticalPath:
    id: str
    description: str
    entry: str
    covered_by: tuple[str, ...]


@dataclass(frozen=True)
class CriticalPathRegistry:
    paths: tuple[CriticalPath, ...]
    _by_id: dict[str, CriticalPath] = field(default_factory=dict, init=False, repr=False)

    def __post_init__(self) -> None:
        # Duplicate ids would silently last-wins in the lookup while both rows
        # still render — fail loudly at load time instead.
        seen: set[str] = set()
        dupes = sorted({p.id for p in self.paths if p.id in seen or seen.add(p.id)})
        if dupes:
            raise ValueError(f"duplicate critical-path ids: {dupes}")
        # `frozen=True` blocks direct assignment; route through object.__setattr__.
        object.__setattr__(self, "_by_id", {p.id: p for p in self.paths})

    def by_id(self, path_id: str) -> CriticalPath:
        if path_id not in self._by_id:
            raise KeyError(path_id)
        return self._by_id[path_id]


@dataclass(frozen=True)
class CriticalPathStatus:
    path: CriticalPath
    state: CriticalPathState
    covering_groups_run: tuple[str, ...]
    notes: str = ""
    # True when a declared covering group belongs to the tier(s) this run
    # covered. An out-of-scope gap (coverage only in an unrun tier, or none
    # declared) must not gate under --fail-on-critical-gap. Defaults False so a
    # regression that forgets to pass it can only under-gate (spurious warning),
    # never over-gate (spurious build block).
    in_scope: bool = False

    def __post_init__(self) -> None:
        # Make the contradictory states unrepresentable rather than relying on
        # evaluate()'s discipline: covered ⇒ at least one covering group ran;
        # gap/regression ⇒ none did.
        if self.state == "covered" and not self.covering_groups_run:
            raise ValueError("state='covered' requires a non-empty covering_groups_run")
        if self.state in ("gap", "regression") and self.covering_groups_run:
            raise ValueError(f"state={self.state!r} must have empty covering_groups_run")


def load_critical_paths(path: Path | None = None) -> CriticalPathRegistry:
    raw = yaml.safe_load((path or DEFAULT_REGISTRY).read_text())
    if not isinstance(raw, dict) or "paths" not in raw:
        raise ValueError(f"{path or DEFAULT_REGISTRY}: expected top-level `paths:` list")
    return CriticalPathRegistry(
        paths=tuple(
            CriticalPath(
                id=str(p["id"]),
                description=str(p.get("description", "")),
                entry=str(p.get("entry", "")),
                covered_by=tuple(p.get("covered_by") or ()),
            )
            for p in raw["paths"]
        )
    )


def validate_registry_against_manifest(
    registry: CriticalPathRegistry, manifest: GroupManifest
) -> list[str]:
    """Return human-readable errors for unknown groups referenced in ``covered_by``."""
    errors: list[str] = []
    known = set(manifest.names())
    for path in registry.paths:
        for g in path.covered_by:
            if g not in known:
                errors.append(
                    f"critical path {path.id!r}: "
                    f"covered_by references unknown group {g!r}"
                )
    return errors


def evaluate(
    registry: CriticalPathRegistry,
    *,
    groups_run_green: Collection[str],
    baseline: dict[str, Any] | None,
    scope_groups: Collection[str] | None = None,
) -> list[CriticalPathStatus]:
    """Compute the status for each critical path against this build's results.

    Args:
        registry: parsed critical-paths registry.
        groups_run_green: names of groups that ran AND passed in this build.
        baseline: parsed previous-summary.json from the main-branch cache, or None.
                  Expected shape: ``{"covered_paths": ["auth-login", ...]}``.
        scope_groups: collection of every group the caller considered running
                  this invocation (including dep-expanded deps and skipped
                  optional placeholders). When a critical path's ``covered_by``
                  is fully outside ``scope_groups``, the path is classified as
                  ``gap`` rather than ``regression`` — running only the unit
                  tier shouldn't flag e2e-tier paths as regressed. If ``None``,
                  no scoping is applied (back-compat).

    Returns:
        Statuses in the original registry order.
    """
    previously_covered: set[str] = set((baseline or {}).get("covered_paths") or [])
    # Convert to sets internally so per-path membership checks stay O(1) even
    # when callers pass lists/tuples; the public signature accepts Collection
    # to leave that choice to them.
    green = set(groups_run_green)
    scope = None if scope_groups is None else set(scope_groups)
    statuses: list[CriticalPathStatus] = []
    for path in registry.paths:
        covering = tuple(g for g in path.covered_by if g in green)
        in_scope = scope is None or any(g in scope for g in path.covered_by)
        state: CriticalPathState
        if covering:
            state = "covered"
            note = ""
        elif path.id in previously_covered and in_scope:
            state = "regression"
            note = "Was covered on the cached baseline; not covered in this build."
        else:
            state = "gap"
            note = (
                "Out of scope for this invocation."
                if not in_scope
                else "No group covering this path ran green in this build."
            )
        statuses.append(
            CriticalPathStatus(
                path=path,
                state=state,
                covering_groups_run=covering,
                notes=note,
                in_scope=in_scope,
            )
        )
    return statuses


def merge_into_baseline(statuses: list[CriticalPathStatus], destination: Path) -> None:
    """Merge this build's green critical paths into the cached baseline.

    Two tiers run in separate processes (unit, then integration; then e2e in a
    separate workflow). Each invocation only knows about the paths covered by
    *its* groups. A naive overwrite would erase the other tier's coverage, so
    we union with whatever's already on disk.

    A corrupt baseline raises :class:`BaselineCorruptError` rather than being
    treated as empty: silently dropping previously-covered paths would erase
    the other tier's contribution and turn the next build into a regression
    festival. CI should delete the cache and retry on this exception.
    """
    existing: set[str] = set()
    if destination.exists():
        try:
            parsed = json.loads(destination.read_text())
            existing = set(parsed.get("covered_paths") or [])
        except (json.JSONDecodeError, OSError) as exc:
            raise BaselineCorruptError(
                f"refusing to merge into corrupt baseline {destination}: {exc}. "
                "Delete the cache entry and re-run."
            ) from exc
    fresh = {s.path.id for s in statuses if s.state == "covered"}
    payload = {"covered_paths": sorted(existing | fresh)}
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(payload, indent=2))


def load_baseline(source: Path) -> dict[str, Any] | None:
    """Load the cached baseline.

    Returns None if the file doesn't exist (first build / fresh cache).
    Raises :class:`BaselineCorruptError` if the file exists but is unreadable
    or unparseable — see :func:`merge_into_baseline` for the rationale.
    """
    if not source.exists():
        return None
    try:
        return json.loads(source.read_text())
    except (json.JSONDecodeError, OSError) as exc:
        raise BaselineCorruptError(
            f"baseline at {source} is unreadable: {exc}. "
            "Delete the cache entry and re-run."
        ) from exc
