"""The bot's side of a backport PR: Backport's squash of a clean pick, and the reaction when a person closes or
reopens one.

Usage: backport_merge.py --pr N --sender LOGIN   (Backport's record job, on `pull_request_target` closed or reopened
for a backport/* head into release/*; LOGIN is the event's sender; a failed run is recovered with "Re-run jobs").
Anything but a same-repo backport/X.Y/<sha7> head into release/X.Y, opened by the bot, is refused.

People land a conflict PR with the normal buttons (resolve, one approving review, Squash and merge) or close it. The PR's
state is read again here, so a re-run or a repeated event acts on what the PR is now. Labels on backport PRs are
the bot's: each case but a head with no pick sets exactly one `backport-*` label and removes the others.
- merged: label `backport-merged`; delete the head if it is still there.
- closed unmerged: a decline. The reason is the closer's newest comment made in the 2 minutes up to the close (the
  close comment), first line, a leading `Declined:` dropped; with none, `Closed by @<closer> without a reason (PR
  #<n>)`. Push an empty commit onto the base with the pick's message, the trailer and a final `Declined: <reason>`
  line; label `backport-declined`; comment `Recorded as a decline on <base> (<sha7>). To undo: ...` once per close.
  The head is kept so the PR can be reopened. A pick or decline already on the base (newest first) -> no commit,
  label and comment still fixed. The decline's message is the main commit's own, so a head edited by hand never
  names other fixes: the head's first commit must carry exactly one pick trailer, naming the main commit of the
  head's sha7. Otherwise -> no decline commit: the bot comments and the run fails. A head with no commit past the
  base (moved onto it) -> nothing declined, no label and no delete: the bot comments once. While the head is still
  this PR's, the comment says to delete it by hand, or to keep it until a hand-made decline is on the base; once
  the head is gone or holds another pick, it says only that nothing was declined.
- open (reopened): label `backport-conflict`, nothing else. Merging it then lands the pick after the decline, and
  the newest trailer on the line wins (relmgr.trailer_states): the fix counts as shipped again.
Run from a full clone of main, GH_TOKEN = the release App's installation token, RELEASE_BOT_APP_SLUG = its slug.
"""

import argparse
import datetime
import json
import os
import subprocess
import sys
import time

import relmgr as rm

MERGED, DECLINED, CONFLICT = "backport-merged", "backport-declined", "backport-conflict"
REASON_WINDOW = datetime.timedelta(minutes=2)
NO_PICK = "Nothing to record: this PR's head has no commit past"


def is_backport(head, base):
    """Is head a pick head for base (backport/X.Y/<sha7> into release/X.Y)?"""
    m = rm.BACKPORT_HEAD_RE.fullmatch(head)
    return bool(m) and base == f"release/{m[1]}"


def gh(*args, token=None):
    env = {**os.environ, "GH_TOKEN": token} if token else None
    r = subprocess.run(["gh", *args], capture_output=True, text=True, env=env)
    if r.returncode:
        raise RuntimeError(
            f"gh {' '.join(args[:2])} (exit {r.returncode}): {r.stderr.strip()}"
        )
    return r.stdout.strip()


def decline_reason(comments, sender, closed_at):
    """First line of the closer's newest comment in the REASON_WINDOW up to closed_at, a leading `Declined:` dropped;
    None if there is none or it is empty.
    """
    at = lambda t: datetime.datetime.fromisoformat(t.replace("Z", "+00:00"))
    end = at(closed_at)
    for c in sorted(comments, key=lambda c: c["created_at"], reverse=True):
        if c["user"] == sender and end - REASON_WINDOW <= at(c["created_at"]) <= end:
            line = (c["body"].strip().splitlines() or [""])[0]
            # A pick trailer in the reason would mark that other commit declined in the decline commit's message.
            # Strip until none is left: a trailer nested in another reassembles after one pass.
            while rm.PICK_RE.search(line):
                line = rm.PICK_RE.sub("", line)
            return line.removeprefix("Declined:").strip() or None
    return None


def head_messages(pr):
    """Messages of the PR head's commits above the base, oldest first. Fetched through refs/pull/N/head, which
    outlives the deleted head branch.
    """
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
        rm.git(".", "log", "-1", "--format=%B", c)
        for c in rm.git(".", "rev-list", "--reverse", f"origin/{base}..{sha}").split()
    ]


def first_pick(pr):
    """(message, [original]) for the decline: the main commit the head's first commit picks, its message plus the
    pick trailer. ("", []) when that commit has no single pick trailer naming the head's sha7 on main; (None, []) when
    the head has no commit past the base (moved onto it), so there is nothing to decline.
    """
    msgs = head_messages(pr)
    if not msgs:
        return None, []
    o = rm.pick_trailer(pr["headRefName"], msgs[0] if msgs else "")
    if not o or not rm.on_main(".", o, "origin/main"):
        return "", []
    full = rm.git(".", "rev-parse", f"{o}^{{commit}}")
    return (
        f"{rm.git('.', 'log', '-1', '--format=%B', full).strip()}\n\n(cherry picked from commit {full})",
        [full],
    )


def landed(originals, commits):
    """First (sha, message) in commits whose pick trailer names one of originals; None if the pick is not there."""
    for sha, msg in commits:
        if set(rm.PICK_RE.findall(msg)) & set(originals):
            return sha
    return None


def base_picks(base, originals):
    """(sha, message) of commits on origin/<base> whose message names one of originals in a pick trailer."""
    greps = [f"--grep=(cherry picked from commit {o}" for o in originals]
    out = rm.git(".", "log", "--format=%H%x00%B%x01", "-F", *greps, f"origin/{base}")
    return [tuple(c.strip("\n").split("\0", 1)) for c in out.split("\x01") if c.strip()]


def base_tip(base):
    """(commit, tree) of origin/<base>: the parent and the tree of an empty decline commit."""
    return rm.git(".", "rev-parse", f"origin/{base}"), rm.git(
        ".", "rev-parse", f"origin/{base}^{{tree}}"
    )


SQUASH_WAITS = (5, 20)  # seconds before the 2nd and 3rd merge attempt


def squash(slug, pr, msg, sleep=time.sleep):
    """REST squash merge of the PR head with msg as the commit message; False while a required check is pending.

    GitHub can answer a merge of a just-opened PR with 405 "Base branch was modified" although nothing moved the
    base; that answer is retried (3 attempts, 5 s then 20 s apart), then raised.
    """
    title, _, body = msg.partition("\n")
    for wait in (*SQUASH_WAITS, None):
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
            )
            return True
        except RuntimeError as e:
            # A required check GitHub still waits for: the caller reports it. Accepted: this matches GitHub's
            # "Required status check ... is expected/in progress" wording, which GitHub does not document as stable.
            # Known limit: a 405 naming a failed status check matches too and reads as pending.
            if "status check" in str(e).lower():
                print(f"#{pr['number']}: {str(e).splitlines()[0]}")
                return False
            if wait is None or "base branch was modified" not in str(e).lower():
                raise
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
    """The sha the head branch points at, or None when it is gone."""
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
    """(sha, written): the pick or decline for this PR's originals on the base, newest first, else a new decline;
    (None, False) when the head has no commit past the base.
    """
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
            "commit carrying that line, or ask the release manager.",
        )
        raise RuntimeError(
            f"#{n}: no single pick trailer for {pr['headRefName']}, decline not recorded"
        )
    if done := landed(
        originals, base_picks(base, originals)
    ):  # re-run, or a close after a reopen: nothing to write
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


def close(slug, n, sender):
    return record(slug, n, sender)["result"]


def bot_refusal(pr):
    """Why `pr` (gh's number and author) is not a PR the bot opened, or None.

    A head name and trailer are strings any writer can push; only a PR the bot opened is its pick. Backport opens
    pick PRs with the release App's installation token, so they are authored by app/<its slug>. That token cannot
    read `gh api user`, so the slug comes from the workflow.
    """
    if not (app := os.environ.get("RELEASE_BOT_APP_SLUG")):
        return f"#{pr['number']}: RELEASE_BOT_APP_SLUG is unset (the release App's slug)"
    author, bot = pr["author"], f"app/{app}"
    if not author.get("is_bot") or author["login"] != bot:
        return (
            f"#{pr['number']} was opened by @{author['login']}, not by the bot (@{bot})"
        )
    return None


def record(slug, n, sender):
    """What close did: {result, base, sha, reason}; sha is the squash, decline or existing pick, reason the decline's."""
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
    cs = comments(slug, n)
    reason = (
        decline_reason(cs, sender, pr["closedAt"])
        or f"Closed by @{sender} without a reason (PR #{n})"
    )
    sha, written = decline(slug, pr, reason)
    # No pick on the head: nothing to decline. Removing the head is manual: until a person deletes it, every
    # Backport run fails on it. The head may already be gone (deleting it closes the PR) or hold a later run's pick.
    if not sha:
        kept = head_ref(slug, head) == pr["headRefOid"]
        if not any(
            c["body"].startswith(NO_PICK) and c["created_at"] >= pr["closedAt"]
            for c in cs
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
    """The step summary block: what happened to the PR, by whom, and how to undo it."""
    base, sha, pr = rec["base"], rec["sha"], rm.pr_link(n)
    head = f"**Backport PR** {pr} on `{base}`: "
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
            f"Undo: revert {squash} on `{base}`.",
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
                "the release manager's decline commit is on the base (the PR comment says how)."
                if rec["result"] == "skipped: no pick"
                else "Next: nothing here; its head no longer holds this PR's commit."
            ),
        ]
    return [head + f"**skipped**: already on `{base}` as {rm.commit_link(sha)}"]


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
