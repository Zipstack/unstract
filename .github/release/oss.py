"""OSS release lines, driven by git from the cloud release workflows. Cloud release/X.Y pins OSS release/X.Y (same
minor): `unstract-platform-version` in pyproject.toml names one OSS tag, ee-vX.Y.Z-rc.N or ee-vX.Y.Z.

Usage (OSS_REPO: a clone of the OSS repo with full history, tags and origin/release/* heads, that can push):
  oss.py cut --line X.Y [--slack-url URL]               cut OSS release/X.Y from OSS main; prints ee-vX.Y.0-rc.1
  oss.py rc --branch release/X.Y [--slack-url URL]      the tag to pin for the next RC of a cloud line: the tag on
                                                        its OSS line's tip, after a new OSS RC when the tip has none
  oss.py promote --rc vX.Y.Z-rc.N [--force --reason R] [--stabilized]
                                                        promote the OSS RC the cloud RC pins; prints the stable tag.
                                                        --stabilized (the promote that leaves every enabled cloud
                                                        target GA) also tags the OSS line stabilized/X.Y once
retire(): called by cloud Retire for each cloud line it retires.

cut, rc and promote print one OSS tag on stdout. Every write is re-runnable: a tag already on the same commit is
skipped, a tag on another commit fails. A branch and its new tag go in one atomic push.
"""

import argparse
import os
import re
import subprocess
import sys

import backport as bp
import relmgr as rm
import relstate as rs

OSS = rs.PINS or "Zipstack/unstract"  # the OSS repo the cloud lines pin
PREFIX = rs.REPOS[OSS.split("/")[1].lower()][4]
VER = rs.ver_re(PREFIX)
PIN_RE = re.compile(r'^unstract-platform-version = "([^"]*)"$', re.M)
HERE = os.path.dirname(os.path.abspath(__file__))


def pin(repo, ref):
    """The OSS tag that ref's pyproject.toml pins."""
    m = PIN_RE.search(rm.git(repo, "show", f"{ref}:pyproject.toml"))
    if not m:
        raise RuntimeError(f"no unstract-platform-version pin in {ref}:pyproject.toml")
    return m[1]


def line_of(tag):
    m = VER.fullmatch(tag)
    if not m:
        raise RuntimeError(
            f"OSS pin {tag!r} is not a {PREFIX}vX.Y.Z or {PREFIX}vX.Y.Z-rc.N tag"
        )
    return f"release/{m[1]}.{m[2]}"


def tip(oss, branch):
    r = rm.git(
        oss,
        "rev-parse",
        "-q",
        "--verify",
        f"refs/remotes/origin/{branch}^{{commit}}",
        check=False,
    )
    return r.stdout.strip() if r.returncode == 0 else None


def tags_on(oss, sha, branch):
    """Version tags of branch's minor on commit sha."""
    line = branch.removeprefix("release/")
    return [
        t
        for t in rm.git(
            oss, "tag", "--points-at", sha, "-l", f"{PREFIX}v{line}.*"
        ).split()
        if (m := VER.fullmatch(t)) and f"{m[1]}.{m[2]}" == line
    ]


def choose(tags):
    """The tag to pin from one commit's tags: its stable tag, else its newest RC, else None."""
    stable = [t for t in tags if "-rc." not in t]
    return max(stable or tags, key=rs._vkey) if tags else None


def _bot(oss, *args):
    return rm.git(
        oss, "-c", "user.name=releases-bot", "-c", f"user.email={rm.BOT_EMAIL}", *args
    )


def _tag(oss, name, sha, *msgs):
    """Create tag name on sha locally (annotated when msgs); False when it is already there, an error when it is on
    another commit.
    """
    have = rs._tag_commit(oss, name)
    if have and have != sha:
        raise RuntimeError(f"OSS tag {name} is on {have[:12]}, not on {sha[:12]}")
    if have:
        return False
    _bot(
        oss,
        "tag",
        *(["-a", name, *(x for m in msgs for x in ("-m", m))] if msgs else [name]),
        sha,
    )
    return True


def _push(oss, *refspecs):
    rm.git(oss, "push", "-q", "--atomic", "origin", *refspecs)


def _tag_push(oss, name, sha, msgs, *refspecs):
    """Tag sha as name (_tag) and push refspecs. A failed push drops the tag when this call made it, so a re-run in
    this clone does not take a tag origin never got as already done.
    """
    new = _tag(oss, name, sha, *msgs)
    try:
        _push(oss, *refspecs)
    except RuntimeError:
        if new:
            rm.git(oss, "tag", "-d", name)
        raise


def _bump(oss, branch, base, tag, slack_url, old):
    """One empty bot commit `release: <tag>` on base, tagged, pushed as branch's new tip with its tag. The commit gives
    the RC its own commit, so a line never shares a tag's commit with main or another line. The push is leased on
    old, the branch tip it read: for rc, a branch deleted or moved since then fails it instead of being re-created or
    overwritten; for cut, old is "" (no branch), so a branch created since then fails it.
    """
    sha = _bot(
        oss,
        "commit-tree",
        f"{base}^{{tree}}",
        "-p",
        base,
        "-m",
        f"release: {tag.removeprefix('v')}",
    )
    _tag_push(
        oss,
        tag,
        sha,
        [f"Slack: {slack_url}"] if slack_url else [],
        f"--force-with-lease=refs/heads/{branch}:{old}",
        f"{sha}:refs/heads/{branch}",
        f"refs/tags/{tag}",
    )
    rm.git(oss, "update-ref", f"refs/remotes/origin/{branch}", sha)
    return sha


def gate(oss, branch, ref, annotate):
    """The OSS-line convergence gate of branch at tag ref, run on the OSS clone as the OSS repo: 0 pass, 2 block,
    1 error. Its checks table goes to the step summary. argparse also exits 2, on a usage error: that is an error,
    never a block a force could override.
    """
    if summary := os.environ.get("GITHUB_STEP_SUMMARY"):
        with open(summary, "a") as f:
            f.write(f"#### OSS line `{branch}` at `{ref}`\n\n")
    env = {
        **os.environ,
        "GITHUB_REPOSITORY": OSS,
        "GH_TOKEN": os.environ.get("OSS_TOKEN") or os.environ.get("GH_TOKEN", ""),
    }
    r = subprocess.run(
        [
            sys.executable,
            os.path.join(HERE, "convgate.py"),
            "--repo",
            oss,
            "--branch",
            branch,
            "--target",
            "oss",
            "--promote-ref",
            ref,
            "--annotate",
            annotate,
        ],
        env=env,
        stdout=2,
        stderr=subprocess.PIPE,
        text=True,
    )  # stdout is the tag the workflow captures
    sys.stderr.write(r.stderr)
    if (
        r.returncode not in (0, 2)
        or r.returncode == 2
        and re.search(r"^usage: ", r.stderr, re.M)
    ):
        return 1
    return r.returncode


# Known limit: line is not checked to be X.Y.
def cut(oss, line, slack_url=""):
    """Cut OSS release/<line> from OSS main's tip plus its first RC. Refused when the OSS line exists, unless it is
    this cut's own result from an earlier run (its tip the bot bump carrying ee-v<line>.0-rc.1), or when the minor
    has OSS tags left (a retired line that shipped).
    """
    branch, tag = f"release/{line}", f"{PREFIX}v{line}.0-rc.1"
    if have := tip(oss, branch):
        if rs._tag_commit(oss, tag) == have and rm.already_bumped(
            oss, f"refs/remotes/origin/{branch}", tag
        ):
            print(
                f"OSS {branch} already cut at {tag} ({have[:12]}): re-run of the same cut",
                file=sys.stderr,
            )
            return tag
        raise RuntimeError(f"OSS {branch} already exists: a cut never reuses an OSS line")
    if used := [
        t
        for t in rm.git(oss, "tag", "-l", f"{PREFIX}v{line}.*").split()
        if VER.fullmatch(t)
    ]:
        raise RuntimeError(
            f"OSS minor {line} already has tags ({', '.join(sorted(used, key=rs._vkey))})"
        )
    _bump(
        oss,
        branch,
        rm.git(oss, "rev-parse", "refs/remotes/origin/main"),
        tag,
        slack_url,
        "",
    )
    return tag


def rc(oss, branch, slack_url=""):
    """The OSS tag for the next RC of cloud branch: its OSS line's tip tag, after a new OSS RC on an untagged tip.
    Previews the OSS-line gate (never blocks).
    """
    sha = tip(oss, branch)
    if not sha:
        raise RuntimeError(f"OSS {branch} does not exist: cloud Cut makes it")
    if not (tag := choose(tags_on(oss, sha, branch))):
        tag = rm.rc_version(oss, f"refs/remotes/origin/{branch}", PREFIX)
        _bump(oss, branch, sha, tag, slack_url, sha)
        print(f"OSS {branch}: new RC {tag}", file=sys.stderr)
    if "-rc." in tag and gate(oss, branch, tag, "warning") == 1:
        print(
            f"::warning::OSS convergence gate for {branch} did not run (see the log)",
            file=sys.stderr,
        )
    return tag


# Known limit: force accepts an empty reason.
def promote(repo, oss, cloud_rc, force=False, reason="", stabilized=False):
    """The stable OSS tag of the OSS RC cloud_rc pins (_promote). stabilized: this promote leaves every enabled
    target of the cloud line GA, so the OSS line's stabilized/X.Y tag goes on that stable tag's commit when the line
    has none (a later promote keeps it).
    Known limit: the tag marks the promote, not the retag or chart push after it; if those fail, the OSS line is
    stabilized before its cloud line is GA.
    """
    stable = _promote(repo, oss, cloud_rc, force, reason)
    mark = rs.STABILIZED + line_of(stable).split("/", 1)[1]
    if stabilized and not rs._tag_commit(oss, mark):
        sha = rs._tag_commit(oss, stable)
        if not sha:
            raise RuntimeError(f"no OSS tag {stable}")
        _tag_push(
            oss,
            mark,
            sha,
            [f"stabilized: {stable} (cloud {cloud_rc})"],
            f"refs/tags/{mark}",
        )
    return stable


def _promote(repo, oss, cloud_rc, force, reason):
    """The stable OSS tag of the OSS RC cloud_rc pins, tagging it when it has none yet. Open backport conflict PRs on
    the OSS line (or a failed listing of them) and its gate block first unless force; the other cloud product finds
    the tag and skips both.
    """
    pinned = pin(repo, cloud_rc)
    branch = line_of(pinned)
    if "-rc." not in pinned:
        return pinned
    sha = rs._tag_commit(oss, pinned)
    if not sha:
        raise RuntimeError(f"no OSS tag {pinned}")
    try:
        stable = rm.promote_version(oss, pinned)
    except ValueError as e:  # downgrade
        raise RuntimeError(f"OSS {e}") from None
    if rs._tag_commit(oss, stable) == sha:
        return stable  # promoted earlier, e.g. by the other cloud product
    try:
        prs, unchecked = (
            [
                f"#{p['number']}"
                for p in bp.conflict_prs(OSS, branch, os.environ.get("OSS_TOKEN"))
            ],
            [],
        )
    except RuntimeError as e:
        if not force:
            raise
        print(
            f"::warning::Could not list open backport conflict PRs on OSS {branch} (forced on): {e}",
            file=sys.stderr,
        )
        prs, unchecked = [], ["conflict PRs unchecked: listing failed"]
    if prs and not force:
        raise RuntimeError(
            f"OSS {branch} has open backport conflict PRs {', '.join(prs)}: resolve and merge or close "
            "them, or force with a reason"
        )
    code = gate(oss, branch, pinned, "error")
    if code == 1 or code == 2 and not force:
        raise RuntimeError(
            f"OSS convergence gate for {branch} at {pinned} "
            + (
                "did not run (see the log)"
                if code == 1
                else "blocks: MISSING picks (summary above); force with a reason"
            )
        )
    forced = (
        ([f"forced: {reason}"] if code == 2 or prs or unchecked else [])
        + unchecked
        + ([f"open conflict PRs: {', '.join(prs)}"] if prs else [])
    )
    _tag_push(
        oss,
        stable,
        sha,
        [f"promote: {pinned} -> {stable} (cloud {cloud_rc})", *forced],
        f"refs/tags/{stable}",
    )
    return stable


def retire(oss, branch, reason, dry_run=True):
    """Retire OSS release/X.Y with its cloud line, in one atomic push: archive tag retired/X.Y-<tip sha7>, delete
    (no OSS GA) its RC tags and the branch. With a GA its tags stay, stabilized/X.Y with them, and the minor is never
    reused; without one it is. Summary lines.
    """
    line = branch.removeprefix("release/")
    sha = tip(oss, branch)
    if not sha:
        done = rm.git(oss, "tag", "-l", f"retired/{line}-*").split()
        return [
            f"- OSS `{branch}`: no branch"
            + (f" (archived as `{done[-1]}`)" if done else "")
        ]
    archive = f"retired/{line}-{sha[:7]}"
    if moved := rs.moved_archive(oss, line, sha):
        raise RuntimeError(
            f"OSS {branch} moved to {sha[:12]} after {moved} archived it; check the new commits, then "
            f"delete {moved} to retire it again"
        )
    stable, _ = rm._tags(oss, *line.split("."), PREFIX)
    rcs = (
        []
        if stable
        else sorted(
            (
                t
                for t in rm.git(oss, "tag", "-l", f"{PREFIX}v{line}.*-rc.*").split()
                if VER.fullmatch(t)
            ),
            key=rs._vkey,
        )
    )
    out = [
        f"- OSS `{branch}` (tip `{sha[:12]}`; "
        + ("has GA, tags kept)" if stable else "no GA, RC tags deleted)"),
        *(f"- OSS git tag `{t}`" for t in rcs),
        f"- OSS tag `{archive}`: {reason}",
    ]
    if dry_run:
        return out
    # One atomic push leased on the tip read above: a commit pushed since then fails the whole retire, so on origin
    # the branch, its RC tags and the archive tag all stay as they were. The archive tag is always sent (a no-op when
    # origin has it), so a re-run in this clone archives the tip too.
    _tag_push(
        oss,
        archive,
        sha,
        [f"retired {branch}: {reason}"],
        f"--force-with-lease=refs/heads/{branch}:{sha}",
        f"refs/tags/{archive}",
        *(f":refs/tags/{t}" for t in rcs),
        f":refs/heads/{branch}",
    )
    return out


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument(
        "--oss-repo",
        default=os.environ.get("OSS_REPO"),
        help="the OSS clone; default: $OSS_REPO",
    )
    sub = p.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("cut")
    c.add_argument("--line", required=True)
    c.add_argument("--slack-url", default="")
    r = sub.add_parser("rc")
    r.add_argument("--branch", required=True)
    r.add_argument("--slack-url", default="")
    m = sub.add_parser("promote")
    m.add_argument("--rc", required=True)
    m.add_argument("--force", action="store_true")
    m.add_argument("--reason", default="")
    m.add_argument("--stabilized", action="store_true")
    a = p.parse_args(argv)
    try:
        if not a.oss_repo:
            raise RuntimeError("--oss-repo (or OSS_REPO) is required")
        tag = (
            cut(a.oss_repo, a.line, a.slack_url)
            if a.cmd == "cut"
            else rc(a.oss_repo, a.branch, a.slack_url)
            if a.cmd == "rc"
            else promote(".", a.oss_repo, a.rc, a.force, a.reason, a.stabilized)
        )
    except RuntimeError as e:
        print(f"::error::{e}", file=sys.stderr)  # stdout is the tag the workflow captures
        return 1
    print(tag)
    return 0


if __name__ == "__main__":
    sys.exit(main())
