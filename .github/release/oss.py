"""OSS release lines, driven by git from the cloud release workflows. Cloud release/X.Y pins OSS release/X.Y (same
minor): `unstract-platform-version` in pyproject.toml names one OSS tag, ee-vX.Y.Z-rc.N or ee-vX.Y.Z.

Usage (OSS_REPO: a clone of the OSS repo with full history, tags and origin/release/* heads, that can push):
  oss.py cut --line X.Y [--slack-url URL]               cut OSS release/X.Y from OSS main; prints ee-vX.Y.0-rc.1
  oss.py rc --branch release/X.Y [--slack-url URL] [--force --reason R --notes FILE]
                                                        the tag to pin for the next RC of a cloud line: the tag on
                                                        its OSS line's tip, after a new OSS RC when the tip has none
  oss.py promote --rc vX.Y.Z-rc.N [--force --reason R]
                                                        promote the OSS RC the cloud RC pins; prints the stable tag.
                                                        The line's first stable tag also makes it stabilized

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

OSS = rs.PINS or "Zipstack/unstract"
PREFIX = rs.REPOS[OSS.split("/")[1].lower()][4]
VER = rs.ver_re(PREFIX)
PIN_RE = re.compile(r'^unstract-platform-version = "([^"]*)"$', re.M)
RELEASE = "release/"
HERE = os.path.dirname(os.path.abspath(__file__))


def pin(repo, ref):
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
    return rm.resolve(oss, f"refs/remotes/origin/{branch}")


def tags_on(oss, sha, branch):
    return rs.line_tags(
        oss, branch.removeprefix(RELEASE), "--points-at", sha, prefix=PREFIX
    )


def choose(tags):
    stable = [t for t in tags if "-rc." not in t]
    return max(stable or tags, key=rs._vkey) if tags else None


def _bot(oss, *args):
    return rm.git(
        oss, "-c", "user.name=releases-bot", "-c", f"user.email={rm.BOT_EMAIL}", *args
    )


def _tag(oss, name, sha, *msgs):
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
    """A failed push drops the tag this call made, so a re-run does not take a tag origin never got as done."""
    new = _tag(oss, name, sha, *msgs)
    try:
        _push(oss, *refspecs)
    except RuntimeError:
        if new:
            rm.git(oss, "tag", "-d", name)
        raise


def _bump(oss, branch, base, tag, slack_url, old):
    """Leased on old (the tip read; "" for a cut), so a concurrent change fails the push."""
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
    """Run convgate on the OSS clone: 0 pass, 2 block, 1 error (an argparse usage exit 2 counts as an error)."""
    if summary := os.environ.get("GITHUB_STEP_SUMMARY"):
        with open(summary, "a") as f:
            f.write(
                f"#### OSS line {rm.branch_link(branch, OSS)} at {rm.tag_link(ref, OSS)}\n\n"
            )
    oss, branch, ref = rm.local_path(oss), rm.option_free(branch), rm.option_free(ref)
    env = {
        **os.environ,
        "GITHUB_REPOSITORY": OSS,
        "GH_TOKEN": os.environ.get("OSS_TOKEN") or os.environ.get("GH_TOKEN", ""),
    }
    # convgate stdout -> our stderr: our stdout is the tag the workflow reads.
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
    )
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
    """A cut never reuses an OSS line, nor a minor with tags left (a retired line that shipped); a re-run of the same
    cut returns its tag.
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


def rc(oss, branch, slack_url="", force=False, reason="", notes=None):
    """The OSS-line gate blocks on MISSING picks unless forced; notes: the RC notes file the override goes into."""
    sha = tip(oss, branch)
    if not sha:
        raise RuntimeError(f"OSS {branch} does not exist: cloud Cut makes it")
    if not (tag := choose(tags_on(oss, sha, branch))):
        tag = rm.rc_version(oss, f"refs/remotes/origin/{branch}", PREFIX)
        _bump(oss, branch, sha, tag, slack_url, sha)
        print(f"OSS {branch}: new RC {tag}", file=sys.stderr)
    if "-rc." not in tag:
        return tag
    code = gate(oss, branch, tag, "warning" if force else "error")
    if code == 1 or code == 2 and not force:
        raise RuntimeError(
            f"OSS convergence gate for {branch} at {tag} "
            + (
                "did not run (see the log)"
                if code == 1
                else "blocks: MISSING picks (summary above); to override, rerun with force and a reason"
            )
        )
    if code == 2:
        msg = f"Forced past the OSS convergence gate for {branch} at {tag} (MISSING picks): {reason}"
        print(f"::warning::{msg}", file=sys.stderr)
        if notes:
            with open(rm.local_path(notes), "a") as f:
                f.write(msg + "\n\n")
    return tag


def _conflicts(branch, force):
    unchecked = []
    try:
        prs = [
            f"#{p['number']}"
            for p in bp.conflict_prs(OSS, branch, os.environ.get("OSS_TOKEN"))
        ]
    except RuntimeError as e:
        if not force:
            raise
        # Only under force: the override and its reason are recorded on the tag.
        print(
            f"::warning::Could not list open backport conflict PRs on OSS {branch} (forced on): {e}",
            file=sys.stderr,
        )
        prs, unchecked = [], ["conflict PRs unchecked: listing failed"]
    return prs, unchecked


# Known limit: force accepts an empty reason.
def promote(repo, oss, cloud_rc, force=False, reason=""):
    """Known limit: the OSS stable tag, which stabilizes the OSS line, comes before the cloud tag, the retag and the
    chart push; if those fail, the OSS line is stabilized before its cloud line is GA.

    The other cloud product finds the tag already there and skips the conflict and gate checks.
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
    prs, unchecked = _conflicts(branch, force)
    if prs and not force:
        raise RuntimeError(
            f"OSS {branch} has open backport conflict PRs {', '.join(prs)}: resolve and merge or close "
            "them; to override, rerun with force and a reason"
        )
    code = gate(oss, branch, pinned, "error")
    if code == 1 or code == 2 and not force:
        raise RuntimeError(
            f"OSS convergence gate for {branch} at {pinned} "
            + (
                "did not run (see the log)"
                if code == 1
                else "blocks: MISSING picks (summary above); to override, rerun with force and a reason"
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
    """With an OSS GA the line's tags stay and the minor is never reused; without one its RC tags go and it is."""
    line = branch.removeprefix(RELEASE)
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
        f"- OSS `{branch}` (tip {rm.commit_link(sha, 12, OSS)}; "
        + ("has GA, tags kept)" if stable else "no GA, RC tags deleted)"),
        *(f"- OSS git tag `{t}`" for t in rcs),
        f"- OSS tag {f'`{archive}`' if dry_run else rm.tag_link(archive, OSS)}: {reason}",
    ]
    if dry_run:
        return out
    # Atomic and leased on the tip read above; the archive tag is always sent so a re-run in this clone archives too.
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
    c.add_argument("--line", type=rm.option_free, required=True)
    c.add_argument("--slack-url", default="")
    r = sub.add_parser("rc")
    r.add_argument("--branch", type=rm.option_free, required=True)
    r.add_argument("--slack-url", default="")
    r.add_argument("--force", action="store_true")
    r.add_argument("--reason", default="")
    r.add_argument("--notes")
    m = sub.add_parser("promote")
    m.add_argument("--rc", type=rm.option_free, required=True)
    m.add_argument("--force", action="store_true")
    m.add_argument("--reason", default="")
    a = p.parse_args(argv)
    try:
        if not a.oss_repo:
            raise RuntimeError("--oss-repo (or OSS_REPO) is required")
        if a.cmd == "cut":
            tag = cut(a.oss_repo, a.line, a.slack_url)
        elif a.cmd == "rc":
            tag = rc(a.oss_repo, a.branch, a.slack_url, a.force, a.reason, a.notes)
        else:
            tag = promote(".", a.oss_repo, a.rc, a.force, a.reason)
    except RuntimeError as e:
        print(f"::error::{e}", file=sys.stderr)  # stdout is the tag the workflow captures
        return 1
    print(tag)
    return 0


if __name__ == "__main__":
    sys.exit(main())
