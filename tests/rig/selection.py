"""Resolve user-supplied group selections to a concrete, ordered list to run.

Resolution order (de-duped, then dep-expanded, then topo-sorted by the manifest):

  positional GROUPS ∪ ``--from-file`` lines ∪ (``--tier`` filter) ∪ (``--changed-only`` heuristic)

The literal ``all`` expands to every group in the manifest. When the result is
empty, callers should treat that as "do nothing" rather than silently running
everything — the CLI surfaces a clear error.

With ``--tier``, dep expansion stays inside that tier: tiers run as separate CI
legs, so a cross-tier ``depends_on`` would re-run the same group in every leg.
"""

from __future__ import annotations

import logging
import os
import subprocess
import sys
from pathlib import Path

from tests.rig.groups import REPO_ROOT, GroupManifest, Tier

log = logging.getLogger(__name__)


def resolve(
    manifest: GroupManifest,
    *,
    positional: list[str],
    from_file: Path | None = None,
    tier: Tier | None = None,
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
        # `all` shouldn't bypass a tier filter: when both are passed, intersect.
        tier_set = set(manifest.names_by_tier(tier))
        if "all" in positional or (
            from_file is not None
            and any(
                ln.split("#", 1)[0].strip() == "all"
                for ln in from_file.read_text().splitlines()
            )
        ):
            selected &= tier_set
        else:
            selected.update(tier_set)

    if changed_only:
        selected.update(_groups_for_changed_paths(manifest, base=changed_base))

    if not selected:
        return []

    requested = sorted(selected)
    expanded = manifest.expand(requested)
    if tier is not None:
        # Only dep-expanded groups are dropped; an explicit request survives.
        keep = set(requested)
        expanded = [n for n in expanded if n in keep or manifest.get(n).tier == tier]
    return expanded


def _groups_for_changed_paths(manifest: GroupManifest, *, base: str) -> set[str]:
    """Pick groups whose ``paths`` overlap any file in ``git diff base...HEAD``.

    ``--changed-only`` is designed for PR branches. On a ``push: main`` event
    the checked-out commit *is* ``origin/main``, so ``base...HEAD`` is empty and
    nothing would be selected. We detect ``HEAD == base`` and fall back to
    ``HEAD~1...HEAD`` (the merge commit's delta) so the heuristic still picks
    something useful on main.
    """
    diff_range = f"{base}...HEAD"
    if _same_commit(base, "HEAD"):
        print(
            f"[rig] --changed-only: HEAD == {base}; falling back to HEAD~1...HEAD "
            "(this selector is intended for PR branches).",
            file=sys.stderr,
        )
        diff_range = "HEAD~1...HEAD"
    try:
        result = subprocess.run(
            ["git", "diff", "--name-only", diff_range],
            check=True,
            capture_output=True,
            text=True,
            cwd=REPO_ROOT,
            env={**os.environ, "GIT_OPTIONAL_LOCKS": "0"},
        )
    except FileNotFoundError:
        print(
            "[rig] --changed-only: `git` not found on PATH; skipping",
            file=sys.stderr,
        )
        return set()
    except subprocess.CalledProcessError as exc:
        # Most likely cause: shallow CI clone or missing remote tracking branch.
        # Surface stderr so the user can act on it.
        stderr = (exc.stderr or "").strip()
        print(
            f"[rig] --changed-only: git diff failed (exit {exc.returncode}); "
            f"no groups will be auto-selected from changed files.\n"
            f"      git stderr: {stderr}",
            file=sys.stderr,
        )
        return set()

    changed = [
        REPO_ROOT / line.strip() for line in result.stdout.splitlines() if line.strip()
    ]
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


def _same_commit(ref_a: str, ref_b: str) -> bool:
    """True if both refs resolve to the same commit. Conservative on error:
    returns False so the caller uses the normal ``base...HEAD`` range.
    """
    try:
        out = subprocess.run(
            ["git", "rev-parse", ref_a, ref_b],
            check=True,
            capture_output=True,
            text=True,
            cwd=REPO_ROOT,
            env={**os.environ, "GIT_OPTIONAL_LOCKS": "0"},
        ).stdout.split()
    except (FileNotFoundError, subprocess.CalledProcessError):
        return False
    return len(out) == 2 and out[0] == out[1]
