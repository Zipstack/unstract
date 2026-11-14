"""Rewrite a migration baseline so it lists the migrations on a release branch.

The baseline is the list of *released* migrations: the ones the previous release's
code was written against. ``test_migration_compat.py`` checks every migration that is
not in it, and fails when a listed file changes.

Run it from the repository root after a release branch is cut, and again when a
migration is backported to the newest release branch:

    python backend/backend/tests/update_migration_baseline.py --ref origin/release/0.187

Lint PR checks both, on a PR that changes a migration: it fails when the baseline names
an older release line than the newest release branch, or does not list a migration that
the newest release branch and the PR's branch both have.

A repository that adds its own migrations to this backend keeps its own baseline. Run
this copy of the script against it with ``--repo`` and ``--out``, after this
repository's baseline has been advanced.

Standard library and git only, so release tooling can run it without the backend's
dependencies. Paths come from ``--ref``; hashes come from the working tree, which is
what the guard reads.
"""

from __future__ import annotations

import argparse
import hashlib
import re
import subprocess
import sys
from pathlib import Path

SCRIPT = "backend/backend/tests/update_migration_baseline.py"
TEST = "backend/backend/tests/test_migration_compat.py"
DEFAULT_OUT = "backend/backend/tests/migration_baseline.txt"
# Only a release branch says what is released. Any other ref (HEAD, main) would list
# migrations that no release has, and the guard would stop checking them. The branch
# is read from the remote: a local release/X.Y can be behind it.
RELEASE_REF = re.compile(r"origin/release/(\d+)\.(\d+)")
# Every module in a migrations package: the migrations, and the helper modules they
# import, which change what a released migration does just the same.
MIGRATION = re.compile(r"^backend/(.+/migrations/(?!__init__\.py$)[^/]+\.py)$")
HEADER = """\
# Released migrations: the migration files on the newest release branch.
# {test} checks every migration that is NOT
# listed here, and fails when a listed file changes.
# Regenerate after a release cut:
#   {command}
# A line added by hand exempts that migration from every rule, so it needs a code
# owner's review.
# "third-party" lines are migrations of installed packages that someone has read; the
# test prints the lines to add after a dependency bump.
# released-through: {ref} @ {commit}
"""


def git(repo: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(repo), *args], capture_output=True, text=True
    )
    if result.returncode:
        sys.exit(f"git {' '.join(args)} failed: {result.stderr.strip()}")
    return result.stdout


def newest_release(repo: Path) -> str:
    """The highest origin/release/X.Y this clone knows of (as of its last fetch)."""
    refs = git(
        repo, "for-each-ref", "--format=%(refname:short)", "refs/remotes/origin/release"
    )
    lines = [
        (int(m[1]), int(m[2]), m[0])
        for ref in refs.split()
        if (m := RELEASE_REF.fullmatch(ref))
    ]
    if not lines:
        sys.exit("no origin/release/X.Y branch in this clone; run git fetch origin")
    return max(lines)[2]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--ref", required=True, help="release branch, e.g. origin/release/0.187"
    )
    parser.add_argument("--repo", type=Path, default=Path.cwd(), help="repository root")
    parser.add_argument(
        "--out", default=DEFAULT_OUT, help="baseline file, relative to --repo"
    )
    args = parser.parse_args(argv)
    if not RELEASE_REF.fullmatch(args.ref):
        parser.error(
            "--ref must be a release branch on the remote (origin/release/X.Y), "
            f"not {args.ref!r}"
        )
    repo = args.repo.resolve()
    out = repo / args.out
    newest = newest_release(repo)
    if newest != args.ref:
        # The tables of every release after --ref would count as new, and exempt.
        parser.error(f"--ref {args.ref} is not the newest release branch: {newest} is")

    commit = git(repo, "rev-parse", "--short", f"{args.ref}^{{commit}}").strip()
    lines, notes = [], []
    for entry in git(repo, "ls-tree", "-r", args.ref, "--", "backend").splitlines():
        meta, path = entry.split("\t", 1)
        match = MIGRATION.match(path)
        if not match:
            continue
        local = repo / path
        if not local.is_file():
            notes.append(f"on {args.ref} but not in the working tree, left out: {path}")
            continue
        if git(repo, "hash-object", str(local)).strip() != meta.split()[2]:
            notes.append(
                f"differs from {args.ref}, pinned as it is in the working tree: {path}"
            )
        lines.append(
            f"{hashlib.sha256(local.read_bytes()).hexdigest()}  {match.group(1)}"
        )

    before = out.read_text().splitlines() if out.exists() else []
    third_party = sorted(line for line in before if line.startswith("third-party "))
    body = sorted(lines, key=lambda line: line.split("  ", 1)[1]) + third_party
    command = f"python {SCRIPT} --ref origin/release/X.Y"
    test = TEST
    if args.out != DEFAULT_OUT:  # another repository's baseline, written by this copy
        command = f"python <unstract>/{SCRIPT} --repo . --ref origin/release/X.Y --out {args.out}"
        test = f"<unstract>/{TEST}"
    header = HEADER.format(command=command, test=test, ref=args.ref, commit=commit)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(header + "\n".join(body) + "\n")

    listed = {line for line in before if line and not line.startswith("#")}
    print(
        f"{args.out}: {len(lines)} migrations at {args.ref} @ {commit} "
        f"(+{len(set(body) - listed)} -{len(listed - set(body))} lines)"
    )
    for note in notes:
        print(f"note: {note}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
