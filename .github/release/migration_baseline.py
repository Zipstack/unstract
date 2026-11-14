"""Is the migration baseline as new as the newest release branch?

The backend's migration guard (backend/backend/tests/test_migration_compat.py) checks
every migration that the baseline does not list, and exempts tables that only those
migrations created. A baseline left behind after a release cut therefore treats the
tables of the last release as new, and the guard passes changes that break it. Nothing
on main names the newest release line, so the test cannot see that. Lint PR can.

Usage (Lint PR, for a PR into main): migration_baseline.py
  with GITHUB_REPOSITORY, PR and a gh token in the environment.
Exit 0 when the PR changes no migration or the baseline is current, 1 otherwise.

A repository that adds its own migrations to this backend keeps a copy of this file.
Keep the two identical apart from BASELINE, ADVANCE (with the comments above it) and
this docstring: each repository checks its own baseline.
"""

import os
import re
import subprocess
import sys

BASELINE = "backend/backend/tests/migration_baseline.txt"
# Accepted: the generator pins each file as the working tree has it, so regenerating on a
# branch that also edits a released migration pins that edit. For a file already listed
# the baseline diff shows a changed hash for its CODEOWNERS review; for a newly listed one
# only the generator's "differs from" note on stderr says so.
ADVANCE = (
    "python backend/backend/tests/update_migration_baseline.py --ref origin/{newest}"
)
# The legacy release/v* names do not match.
RELEASE = re.compile(r"^release/(\d+)\.(\d+)$")
HEADER = re.compile(r"^# released-through:\s*(?:origin/)?(release/\d+\.\d+)\b", re.M)
MIGRATION = re.compile(r"^backend/.*/migrations/[^/]+\.py$")
# update_migration_baseline.py's MIGRATION. The generator lists the files of the release
# branch that match it and that its working tree also has; it leaves the others out.
RELEASED = re.compile(r"^backend/(.+/migrations/(?!__init__\.py$)[^/]+\.py)$")


def newest_release(branches):
    found = [(int(m[1]), int(m[2]), b) for b in branches if (m := RELEASE.match(b))]
    return max(found)[2] if found else None


def touches_migrations(paths):
    return any(MIGRATION.match(p) for p in paths)


def unlisted(baseline_text, released):
    """The migration files of a release branch (repository paths) that the baseline does not list."""
    # "third-party  app.0001_x" lines name no path, so they never match one.
    listed = {
        line.split("  ", 1)[1]
        for line in baseline_text.splitlines()
        if "  " in line and not line.startswith("#")
    }
    return sorted(
        m[0] for p in released if (m := RELEASED.match(p)) and m[1] not in listed
    )


def stale_error(baseline_text, branches, path=BASELINE, released=None):
    """None when the baseline names the newest release branch and lists its migrations, or
    when there is no release branch yet.

    released: called with the newest branch, returns the repository paths on it that the
    PR's head also has. A migration picked onto that branch after the baseline was
    generated ships in the release, yet the guard would treat its tables as new. A file
    the head lacks is not required: the generator, run on the head, cannot list it. That
    covers a squash, and also a head branched before the file reached main, which
    therefore passes; the first migration PR from a main that has the file catches it.
    None skips this.
    """
    newest = newest_release(branches)
    if newest is None:
        return None
    if not baseline_text:
        # A branch cut before the baseline existed. Advancing is not the way out.
        return (
            f"{path} is not in this PR's branch, so nothing says which migrations are released. "
            "Merge main into this branch: main has the file."
        )
    m = HEADER.search(baseline_text)
    have = m[1] if m else None
    if have == newest:
        missing = unlisted(baseline_text, released(newest)) if released else []
        if not missing:
            return None
        return (
            f"{path} is at {newest}, but does not list {len(missing)} migration(s) that {newest} and this "
            f"branch have: {', '.join(missing[:5])}{' ...' if len(missing) > 5 else ''}. Their tables are "
            "still treated as new, so the migration guard would pass changes that break them. Regenerate "
            f"the baseline: {ADVANCE.format(newest=newest)}"
        )
    return (
        f"{path} says released-through {have or 'nothing'}, but the newest release branch is {newest}. "
        f"Tables created in {newest} are still treated as new, so the migration guard would pass "
        f"changes that break it. Advance the baseline first: {ADVANCE.format(newest=newest)} "
        "(if main already has the advanced baseline, merge main into this branch instead)"
    )


def _gh(*args):
    r = subprocess.run(["gh", *args], capture_output=True, text=True)
    if r.returncode:
        raise RuntimeError(
            f"gh {' '.join(args[:2])} (exit {r.returncode}): {r.stderr.strip()}"
        )
    return r.stdout


def _tree(slug, ref, gh):
    """Every path at ref."""
    return gh(
        "api",
        f"repos/{slug}/git/trees/{ref}?recursive=1",
        "--jq",
        # A truncated tree would hide migrations: fail rather than pass on part of it.
        'if .truncated then error("the tree is truncated") else .tree[].path end',
    ).split("\n")


def _baseline_at_head(slug, pr, gh):
    """The baseline as the PR's head has it; empty when the head has no such file."""
    try:
        return gh(
            "api",
            "-H",
            "Accept: application/vnd.github.raw",
            f"repos/{slug}/contents/{BASELINE}?ref=refs/pull/{pr}/head",
        )
    except RuntimeError as e:
        if "HTTP 404" in str(e):
            return ""
        raise


def main(gh=_gh):
    slug, pr = os.environ["GITHUB_REPOSITORY"], os.environ["PR"]
    try:
        paths = gh(
            "api",
            "--paginate",
            f"repos/{slug}/pulls/{pr}/files?per_page=100",
            "--jq",
            ".[].filename",
        ).split("\n")
        if not touches_migrations(paths):
            print("No migration in this PR: the baseline is not checked.")
            return 0
        branches = gh(
            "api", "--paginate", f"repos/{slug}/branches?per_page=100", "--jq", ".[].name"
        ).split()
        # Accepted: the head is read as refs/pull/<n>/head, not the SHA the run reports on. If
        # that ref ever lagged the push, an older commit would be checked and its result,
        # pass or fail, reported on the newer one.
        error = stale_error(
            _baseline_at_head(slug, pr, gh),
            branches,
            released=lambda ref: sorted(
                set(_tree(slug, ref, gh)) & set(_tree(slug, f"refs/pull/{pr}/head", gh))
            ),
        )
    except RuntimeError as e:
        print(
            f"::error title=Lint PR::could not check the migration baseline; re-run the job ({e})"
        )
        return 1
    if error is None:
        print(f"{BASELINE} is current.")
        return 0
    print(f"::error title=Lint PR::{error}")
    if summary := os.environ.get("GITHUB_STEP_SUMMARY"):
        with open(summary, "a") as f:
            f.write(f"### Lint PR: migration baseline is stale\n\n{error}\n")
    return 1


if __name__ == "__main__":
    sys.exit(main())
