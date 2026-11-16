"""The bot's side of a backport PR: Backport's squash of a clean pick, and the reaction when a person closes or
reopens one.

Usage: backport_merge.py --pr N --sender LOGIN   (on `pull_request_target` closed or reopened for a backport/* head
into release/*; a failed run is recovered with "Re-run jobs").
Anything but a same-repo backport/X.Y/<sha7> head into release/X.Y, opened by the bot, is refused.
The PR's state is read again here, so a re-run or a repeated event acts on what the PR is now.
Run from a full clone of main, GH_TOKEN = the release App's installation token, RELEASE_BOT_APP_SLUG = its slug.
"""

import argparse
import datetime
import json
import os
import random
import re
import subprocess
import sys
import time

import relmgr as rm

MERGED, DECLINED, CONFLICT = "backport-merged", "backport-declined", "backport-conflict"
REASON_WINDOW = datetime.timedelta(minutes=2)
NO_PICK = "Nothing to record: this PR's head has no commit past"


def is_backport(head, base):
    return (
        rm.is_backport(head)
        and base == f"release/{rm.BACKPORT_HEAD_RE.fullmatch(head)[1]}"
    )


GH_TRIES = 5
# A 5xx or a reply cut short (GitHub incidents) or a network fault. Another 4xx is GitHub's answer: never retried.
TRANSIENT_RE = re.compile(
    r"HTTP 5\d\d|unexpected end of JSON input|unexpected EOF|connection reset|timeout|deadline exceeded",
    re.I,
)
# Primary and secondary rate limits (403 or 429). gh hides the Retry-After and reset headers, so GitHub's
# fallback applies: wait at least a minute, longer on each try.
RATE_LIMIT_RE = re.compile(r"rate limit|HTTP 429", re.I)


def transient(err):
    if RATE_LIMIT_RE.search(err):
        return True
    return bool(TRANSIENT_RE.search(err)) and not re.search(r"HTTP 4\d\d", err)


def gh_wait(n, err=""):
    """Seconds before try n + 2: exponential backoff with jitter, so parallel jobs do not retry in step."""
    top = min(120, 60 * 2**n) if RATE_LIMIT_RE.search(err) else 4 * 2**n
    floor = 60 if RATE_LIMIT_RE.search(err) else top / 2
    return round(random.uniform(floor, top), 1)


def run_gh(args, env=None, retry=True, input=None):
    """Every gh call goes through here. retry=False: a write that may have landed although gh failed; its caller
    checks before retrying.
    """
    for n in range(GH_TRIES):
        r = subprocess.run(
            ["gh", *args], capture_output=True, text=True, env=env, input=input
        )
        if not (r.returncode and retry and n < GH_TRIES - 1 and transient(r.stderr)):
            return r
        wait = gh_wait(n, r.stderr)
        # Safe: the call is retried, and a last failure is returned to the caller. Stderr: a caller's stdout may be its result.
        print(
            f"::warning::gh {' '.join(args[:2])}: {r.stderr.strip()}; retried in {wait} s",
            file=sys.stderr,
        )
        time.sleep(wait)


def gh(*args, token=None, retry=True):
    env = {**os.environ, "GH_TOKEN": token} if token else None
    r = run_gh(args, env, retry)
    if r.returncode:
        raise RuntimeError(
            f"gh {' '.join(args[:2])} (exit {r.returncode}): {r.stderr.strip()}"
        )
    return r.stdout.strip()


def decline_reason(comments, sender, closed_at):
    end = rm.ts(closed_at)
    for c in sorted(comments, key=lambda c: c["created_at"], reverse=True):
        if c["user"] == sender and end - REASON_WINDOW <= rm.ts(c["created_at"]) <= end:
            line = (c["body"].strip().splitlines() or [""])[0]
            # Strip pick trailers (repeatedly: nested ones reassemble) so the reason cannot decline another commit.
            while rm.PICK_RE.search(line):
                line = rm.PICK_RE.sub("", line)
            return line.removeprefix("Declined:").strip() or None
    return None


def head_messages(pr):
    """Fetched through refs/pull/N/head, which outlives the deleted head branch."""
    n, base, sha = pr["number"], pr["baseRefName"], pr["headRefOid"]
    rm.git(
        ".",
        "fetch",
        "-q",
        "origin",
        f"+refs/heads/{base}:refs/remotes/origin/{base}",
        f"+refs/pull/{n}/head:refs/backport/{n}",
    )
    return [
        rm.message(".", c)
        for c in rm.git(".", "rev-list", "--reverse", f"origin/{base}..{sha}").split()
    ]


def first_pick(pr):
    """("", []) when the head's first commit has no single pick trailer naming its sha7 on main; (None, []) when the
    head has no commit past the base, so there is nothing to decline.
    """
    msgs = head_messages(pr)
    if not msgs:
        return None, []
    o = rm.pick_trailer(pr["headRefName"], msgs[0])
    if not o or not rm.on_main(".", o, "origin/main"):
        return "", []
    full = rm.git(".", "rev-parse", f"{o}^{{commit}}")
    return (
        f"{rm.message('.', full).strip()}\n\n(cherry picked from commit {full})",
        [full],
    )


def landed(originals, commits):
    for sha, msg in commits:
        if set(rm.PICK_RE.findall(msg)) & set(originals):
            return sha
    return None


def base_picks(base, originals):
    greps = [f"--grep=(cherry picked from commit {o}" for o in originals]
    out = rm.git(".", "log", "--format=%H%x00%B%x01", "-F", *greps, f"origin/{base}")
    return [tuple(c.strip("\n").split("\0", 1)) for c in out.split("\x01") if c.strip()]


def fetch_base(base):
    rm.git(".", "fetch", "-q", "origin", f"+refs/heads/{base}:refs/remotes/origin/{base}")


def base_tip(base):
    return rm.git(".", "rev-parse", f"origin/{base}"), rm.git(
        ".", "rev-parse", f"origin/{base}^{{tree}}"
    )


DECLINE_TRIES = (
    3  # a 422 on the base ref update: the base moved since base_tip, so re-read it
)


def merged(slug, n):
    return gh("api", f"repos/{slug}/pulls/{n}", "--jq", ".merged") == "true"


def squash(slug, pr, msg, sleep=time.sleep):
    """False while a required check is pending. GitHub can answer a just-opened PR's merge with 405 "Base branch was
    modified" although nothing moved the base, so that is retried. A transient failure may still have merged the PR:
    that is checked before a retry or a failure.
    """
    title, _, body = msg.partition("\n")
    for n in range(GH_TRIES):
        try:
            gh(
                "api",
                "-X",
                "PUT",
                f"repos/{slug}/pulls/{pr['number']}/merge",
                "-f",
                "merge_method=squash",
                "-f",
                f"sha={pr['headRefOid']}",
                "-f",
                f"commit_title={title}",
                "-f",
                f"commit_message={body.strip()}",
                retry=False,
            )
            return True
        except RuntimeError as e:
            # Required check pending: the caller reports it. Accepted: matches GitHub's undocumented "status check"
            # wording, so a failed check also reads as pending.
            if "status check" in str(e).lower():
                print(f"#{pr['number']}: {str(e).splitlines()[0]}")
                return False
            moved = "base branch was modified" in str(e).lower()
            if transient(str(e)) and merged(slug, pr["number"]):
                print(f"#{pr['number']}: {str(e).splitlines()[0]}; merged all the same")
                return True
            if n == GH_TRIES - 1 or not (moved or transient(str(e))):
                raise
            wait = gh_wait(n, str(e))
            print(f"#{pr['number']}: {e}; merge retried in {wait} s")
            sleep(wait)


def set_label(slug, pr, label):
    """Make `label` the PR's only backport-* label (REST: works on closed PRs)."""
    have = {x["name"] for x in pr["labels"]}
    for old in sorted(x for x in have if x.startswith("backport-") and x != label):
        gh("api", "-X", "DELETE", f"repos/{slug}/issues/{pr['number']}/labels/{old}")
    if label not in have:
        gh(
            "api",
            "-X",
            "POST",
            f"repos/{slug}/issues/{pr['number']}/labels",
            "-f",
            f"labels[]={label}",
        )


def delete_head(slug, head):
    """Delete the head branch; already gone (autodelete on merge, a person, a re-run) is fine."""
    try:
        gh("api", "-X", "DELETE", f"repos/{slug}/git/refs/heads/{head}")
    except RuntimeError as e:
        if (
            "404" not in str(e)
            and "422" not in str(e)
            and "Reference does not exist" not in str(e)
        ):
            raise


def head_ref(slug, head):
    try:
        return gh("api", f"repos/{slug}/git/ref/heads/{head}", "--jq", ".object.sha")
    except RuntimeError as e:
        if "404" not in str(e):
            raise
        return None


def comments(slug, n):
    out = gh(
        "api",
        "--paginate",
        f"repos/{slug}/issues/{n}/comments",
        "--jq",
        ".[] | {created_at, body, user: .user.login}",
    )
    return [json.loads(line) for line in out.splitlines()]


def decline(slug, pr, reason):
    n, base = pr["number"], pr["baseRefName"]
    msg, originals = first_pick(pr)
    if msg is None:
        return None, False
    if not originals:
        gh(
            "pr",
            "comment",
            str(n),
            "-R",
            slug,
            "--body",
            "Bot could not record the decline: the first commit's message needs exactly one `(cherry picked from "
            "commit <full main sha>)` line, naming the main commit of this branch's name. Decline it with a hand-made empty "
            "commit carrying that line, or ask whoever runs the release.",
        )
        raise RuntimeError(
            f"#{n}: no single pick trailer for {pr['headRefName']}, decline not recorded"
        )
    for attempt in range(DECLINE_TRIES):
        # A re-run, a close after a reopen, or a concurrent record run: nothing to write.
        if done := landed(originals, base_picks(base, originals)):
            return done, False
        # Empty commit = the base's own tree. REST, so author and committer are the bot token's user, as on merge.
        tip, tree = base_tip(base)
        new = json.loads(
            gh(
                "api",
                "-X",
                "POST",
                f"repos/{slug}/git/commits",
                "-f",
                f"message={msg}\n\nDeclined: {reason}",
                "-f",
                f"tree={tree}",
                "-f",
                f"parents[]={tip}",
            )
        )["sha"]
        try:
            gh(
                "api",
                "-X",
                "PATCH",
                f"repos/{slug}/git/refs/heads/{base}",
                "-f",
                f"sha={new}",
                "-F",
                "force=false",
            )
            return new, True
        except RuntimeError as e:
            if "422" not in str(e) or attempt == DECLINE_TRIES - 1:
                raise
        fetch_base(base)


def bot_refusal(pr):
    """Head names and trailers are forgeable; only a PR authored by app/<RELEASE_BOT_APP_SLUG> is the bot's (the App
    token cannot read gh api user).
    """
    if not (app := os.environ.get("RELEASE_BOT_APP_SLUG")):
        return f"#{pr['number']}: RELEASE_BOT_APP_SLUG is unset (the release App's slug)"
    author, bot = pr["author"], f"app/{app}"
    if not author.get("is_bot") or author["login"] != bot:
        return (
            f"#{pr['number']} was opened by @{author['login']}, not by the bot (@{bot})"
        )
    return None


def _no_pick(slug, n, pr, cs):
    base, head = pr["baseRefName"], pr["headRefName"]
    kept = head_ref(slug, head) == pr["headRefOid"]
    if not any(
        c["body"].startswith(NO_PICK) and c["created_at"] >= pr["closedAt"] for c in cs
    ):
        gh(
            "pr",
            "comment",
            str(n),
            "-R",
            slug,
            "--body",
            f"{NO_PICK} {base}, so nothing was declined. "
            + (
                f"Until `{head}` is deleted, Backport fails on it. To have the fix picked again, delete "
                f"`{head}` by hand. To decline the fix instead, do not delete the head yet: ask the release "
                f"manager for a hand-made empty commit on {base} with the pick's message, its `(cherry picked "
                "from commit <full main sha>)` line and a final `Declined: <reason>` line. Once it is on "
                f"{base}, Backport stops failing and the head can be deleted."
                if kept
                else f"`{head}` no longer holds this PR's head, so there is nothing to delete here."
            ),
        )
    return {
        "result": "skipped: no pick" + ("" if kept else ", head gone"),
        "base": base,
        "sha": None,
        "reason": None,
    }


def record(slug, n, sender):
    pr = json.loads(
        gh(
            "pr",
            "view",
            str(n),
            "-R",
            slug,
            "--json",
            "number,state,closedAt,baseRefName,headRefName,headRefOid,labels,isCrossRepository,mergeCommit,author",
        )
    )
    base, head = pr["baseRefName"], pr["headRefName"]
    if not is_backport(head, base) or pr["isCrossRepository"]:
        raise RuntimeError(
            f"#{n} is not a backport PR ({head} into {base}): nothing recorded"
        )
    if why := bot_refusal(pr):
        raise RuntimeError(f"{why}: nothing recorded")
    if pr["state"] == "OPEN":
        set_label(slug, pr, CONFLICT)
        return {"result": "reopened", "base": base, "sha": None, "reason": None}
    if pr["state"] == "MERGED":
        set_label(slug, pr, MERGED)
        delete_head(slug, head)
        return {
            "result": "merged",
            "base": base,
            "sha": (pr.get("mergeCommit") or {}).get("oid"),
            "reason": None,
        }
    # The App never closes a PR to decline; a close by it comes from a head delete, e.g. a create whose PR was not
    # listed yet. Recording it would settle the fix with no pick.
    if sender == f"{os.environ['RELEASE_BOT_APP_SLUG']}[bot]":
        raise RuntimeError(
            f"#{n} was closed by the release App, not a person: no decline recorded; the next Backport run picks it again"
        )
    cs = comments(slug, n)
    reason = (
        decline_reason(cs, sender, pr["closedAt"])
        or f"Closed by @{sender} without a reason (PR #{n})"
    )
    sha, written = decline(slug, pr, reason)
    # No pick on the head: nothing to decline. Removing the head is manual: until a person deletes it, every
    # Backport run fails on it. The head may already be gone (deleting it closes the PR) or hold a later run's pick.
    if not sha:
        return _no_pick(slug, n, pr, cs)
    set_label(slug, pr, DECLINED)
    if not any(
        c["body"].startswith("Recorded as a decline")
        and c["created_at"] >= pr["closedAt"]
        for c in cs
    ):
        gh(
            "pr",
            "comment",
            str(n),
            "-R",
            slug,
            "--body",
            f"Recorded as a decline on {base} ({sha[:7]}). To undo: reopen this PR and merge it.",
        )
    result = (
        f"declined {sha[:7]}" if written else f"skipped: already on {base} as {sha[:7]}"
    )
    return {"result": result, "base": base, "sha": sha, "reason": reason}


def summary(n, sender, rec):
    base, sha, pr = rec["base"], rec["sha"], rm.pr_link(n)
    head = f"**Backport PR** {pr} on {rm.branch_link(base)}: "
    if rec["result"].startswith("declined"):
        return [
            head + f"**declined** as {rm.commit_link(sha)}",
            f'Reason: "{rec["reason"]}" (@{sender})',
            f"Undo: reopen {pr} and merge it.",
        ]
    if rec["result"] == "merged":
        squash = rm.commit_link(sha) if sha else "the squash"
        return [
            head + f"**merged** as {squash} (@{sender})",
            f"Undo: revert {squash} on {rm.branch_link(base)}.",
        ]
    if rec["result"] == "reopened":
        return [
            head + f"**reopened** (@{sender})",
            "Next: merge it to land the pick, or close it again to keep the decline.",
        ]
    if not sha:
        return [
            head
            + "**skipped**: its head has no commit past the base, so nothing was declined",
            (
                "Next: delete the head by hand to have the fix picked again; to decline it, keep the head until "
                "the decline commit is on the base (the PR comment says how)."
                if rec["result"] == "skipped: no pick"
                else "Next: nothing here; its head no longer holds this PR's commit."
            ),
        ]
    return [
        head + f"**skipped**: already on {rm.branch_link(base)} as {rm.commit_link(sha)}"
    ]


def main():
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--pr", type=int, required=True)
    p.add_argument("--sender", required=True)
    a = p.parse_args()
    rec = record(os.environ["GITHUB_REPOSITORY"], a.pr, a.sender)
    print(f"#{a.pr}: {rec['result']}")
    if os.environ.get("GITHUB_STEP_SUMMARY"):
        with open(os.environ["GITHUB_STEP_SUMMARY"], "a") as f:
            f.write("  \n".join(summary(a.pr, a.sender, rec)) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
