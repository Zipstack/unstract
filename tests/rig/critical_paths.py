"""Load ``tests/critical_paths.yaml`` and compute gaps + regressions."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from tests.rig.groups import REPO_ROOT, GroupManifest

DEFAULT_REGISTRY = REPO_ROOT / "tests" / "critical_paths.yaml"


@dataclass(frozen=True)
class CriticalPath:
    id: str
    description: str
    entry: str
    covered_by: tuple[str, ...]


@dataclass(frozen=True)
class CriticalPathRegistry:
    paths: tuple[CriticalPath, ...]

    def by_id(self, path_id: str) -> CriticalPath:
        for p in self.paths:
            if p.id == path_id:
                return p
        raise KeyError(path_id)


@dataclass(frozen=True)
class CriticalPathStatus:
    path: CriticalPath
    state: str  # "covered" | "gap" | "regression"
    covering_groups_run: tuple[str, ...]
    notes: str = ""


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
                errors.append(f"critical path {path.id!r}: covered_by references unknown group {g!r}")
    return errors


def evaluate(
    registry: CriticalPathRegistry,
    *,
    groups_run_green: set[str],
    baseline: dict[str, Any] | None,
) -> list[CriticalPathStatus]:
    """Compute the status for each critical path against this build's results.

    Args:
        registry: parsed critical-paths registry.
        groups_run_green: names of groups that ran AND passed in this build.
        baseline: parsed previous-summary.json from the main-branch cache, or None.
                  Expected shape: ``{"covered_paths": ["auth-login", ...]}``.

    Returns:
        Statuses in the original registry order.
    """
    previously_covered: set[str] = set(
        (baseline or {}).get("covered_paths", []) if baseline else []
    )
    statuses: list[CriticalPathStatus] = []
    for path in registry.paths:
        covering = tuple(g for g in path.covered_by if g in groups_run_green)
        if covering:
            state = "covered"
            note = ""
        elif path.id in previously_covered:
            state = "regression"
            note = "Was covered on the cached main baseline; not covered in this build."
        else:
            state = "gap"
            note = "No group covering this path ran green in this build."
        statuses.append(
            CriticalPathStatus(
                path=path,
                state=state,
                covering_groups_run=covering,
                notes=note,
            )
        )
    return statuses


def emit_baseline(statuses: list[CriticalPathStatus], destination: Path) -> None:
    """Persist the green critical paths so the next build can detect regressions."""
    payload = {
        "covered_paths": [s.path.id for s in statuses if s.state == "covered"],
    }
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(payload, indent=2))


def load_baseline(source: Path) -> dict[str, Any] | None:
    if not source.exists():
        return None
    try:
        return json.loads(source.read_text())
    except (json.JSONDecodeError, OSError):
        return None
