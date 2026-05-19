"""Resolve user-supplied group selections to a concrete, ordered list to run.

Resolution order (de-duped, then dep-expanded, then topo-sorted by the manifest):

  positional GROUPS ∪ ``--from-file`` lines ∪ (``--tier`` filter) ∪ (``--changed-only`` heuristic)

The literal ``all`` expands to every group in the manifest. When the result is
empty, callers should treat that as "do nothing" rather than silently running
everything — the CLI surfaces a clear error.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

from tests.rig.groups import REPO_ROOT, GroupManifest


def resolve(
    manifest: GroupManifest,
    *,
    positional: list[str],
    from_file: Path | None = None,
    tier: str | None = None,
    changed_only: bool = False,
    changed_base: str = "origin/main",
) -> list[str]:
    selected: set[str] = set()

    for name in positional:
        if name == "all":
            selected.update(manifest.names())
        else:
            selected.add(name)

    if from_file is not None:
        for line in from_file.read_text().splitlines():
            entry = line.split("#", 1)[0].strip()
            if not entry:
                continue
            if entry == "all":
                selected.update(manifest.names())
            else:
                selected.add(entry)

    if tier is not None:
        selected.update(manifest.names_by_tier(tier))

    if changed_only:
        selected.update(_groups_for_changed_paths(manifest, base=changed_base))

    return manifest.expand(sorted(selected)) if selected else []


def _groups_for_changed_paths(manifest: GroupManifest, *, base: str) -> set[str]:
    """Pick groups whose ``paths`` overlap any file in ``git diff base...HEAD``."""
    try:
        out = subprocess.run(
            ["git", "diff", "--name-only", f"{base}...HEAD"],
            check=True,
            capture_output=True,
            text=True,
            cwd=REPO_ROOT,
            env={**os.environ, "GIT_OPTIONAL_LOCKS": "0"},
        ).stdout
    except (subprocess.CalledProcessError, FileNotFoundError):
        return set()

    changed = [REPO_ROOT / line.strip() for line in out.splitlines() if line.strip()]
    picked: set[str] = set()
    for name, group in manifest.groups.items():
        if group.optional and not group.absolute_workdir().exists():
            continue
        roots = [group.absolute_workdir()] + group.absolute_paths()
        for f in changed:
            if any(_is_within(f, root) for root in roots):
                picked.add(name)
                break
    return picked


def _is_within(child: Path, parent: Path) -> bool:
    try:
        child.resolve().relative_to(parent.resolve())
        return True
    except ValueError:
        return False
