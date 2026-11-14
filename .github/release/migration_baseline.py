"""Is the migration baseline as new as the newest release branch?

The backend's migration guard (backend/backend/tests/test_migration_compat.py) checks
every migration that the baseline does not list, and exempts tables that only those
migrations created. A baseline left behind after a release cut therefore treats the
tables of the last release as new, and the guard passes changes that break it. Nothing
on main names the newest release line, so the test cannot see that. Lint PR can.

Usage (Lint PR, for a PR into main): migration_baseline.py
  with GITHUB_REPOSITORY, PR and a gh token in the environment.
Exit 0 when the PR changes no migration or the baseline is current, 1 otherwise.
"""

import os
import re
import subprocess
import sys

BASELINE = "backend/backend/tests/migration_baseline.txt"
ADVANCE = (
    "python backend/backend/tests/update_migration_baseline.py --ref origin/{newest}"
)
# The legacy release/v* names do not match.
RELEASE = re.compile(r"^release/(\d+)\.(\d+)$")
HEADER = re.compile(r"^# released-through:\s*(?:origin/)?(release/\d+\.\d+)\b", re.M)
MIGRATION = re.compile(r"^backend/.*/migrations/[^/]+\.py$")


def newest_release(branches):
    found = [(int(m[1]), int(m[2]), b) for b in branches if (m := RELEASE.match(b))]
    return max(found)[2] if found else None


def touches_migrations(paths):
    return any(MIGRATION.match(p) for p in paths)


def stale_error(baseline_text, branches, path=BASELINE):
    """None when the baseline names the newest release branch, or when there is none yet."""
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
        return None
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
        error = stale_error(_baseline_at_head(slug, pr, gh), branches)
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
