"""Backport: a fix lands on main first, then is cherry-picked with -x onto every release branch that
accepts it, all at once.

Usage: backport.py --state state.json (--commits SHA|PR[,...] | --rescan) [--confirm-stabilized] [--branches release/X.Y[,...]]

--rescan (every push to main): ignore the pushed commits and pick, for each target, every main commit since its cut
that no pick or decline trailer there names: plain fixes too on fix targets (held accept=OWED), security/critical
only on stabilized ones (accept=HELD, held for the RM without --confirm-stabilized). A run cancelled by a newer push
costs nothing: the next run rescans. The exception is a run stopped after pushing a pick head and before opening
its PR, or whose `gh pr create` failed: after PICK_TIMEOUT that head fails later runs until a person deletes it
(finish_open). So does a pick PR closed with no commit past its base, whose head the record job keeps. Keeping the
run red until a person acts is deliberate: a passing run would hide a fix that is neither picked nor declined.
A decline carries the pick trailer, so a declined fix is never re-picked; an open conflict PR is left alone
(`skipped: conflict PR pending`) until a person merges or closes it; an open clean pick PR whose merge failed in
an earlier run is merged by the next run.
--commits (dispatch): only these commits.

Run from a full clone whose `origin` pushes with the bot token, with GH_TOKEN set to the bot token and
RELEASE_BOT_APP_SLUG set to the release App's slug.
Every pick is a PR from backport/X.Y/<sha7> to release/X.Y titled with the original main PR's title (every pick
is its own PR), so PR-title changelogs list it. The class comes from that PR's title and fix/ labels.
Clean pick: the bot squash-merges the PR in the same run through backport_merge.squash with the pick's own
message, so the -x trailer survives whatever the repo's squash default, and deletes
the head. No wait for the PR check: the bot is a bypass actor on the release/* ruleset, the check only
classifies commits, which an -x pick passes, and the push run of Release branch CI stays the backstop, as for
the direct pushes this replaced. If GitHub still holds the merge for a required check, the PR stays open and
the run reports it.
A rejected push of the pick head is retried (3 attempts, 5 s then 20 s apart); a final rejection is one
sentence naming the cause and the fix, in the run's ::error::, on the source PR and in the gate's MISSING row.
Conflict: committed with markers and left open with label backport-conflict. A person resolves it, gets one
approving review and merges it, or closes it; Backport's record job (backport_merge.py) then records the merge,
or the close as a decline (the close comment is the reason). Reopening and merging undoes a decline.
Never builds. Targets come from relstate's backport_targets only, never from input: a branch is a
target when its state accepts the fix. --branches only narrows those targets; it never adds one.
"""

import argparse
import datetime
import json
import os
import re
import subprocess
import sys
import time
import traceback

import backport_merge as bm
import relmgr as rm
import relstate as rs

REPO = "."
BOT_ENV = {"GIT_COMMITTER_NAME": "releases-bot", "GIT_COMMITTER_EMAIL": rm.BOT_EMAIL}


def run(*args, check=True, input=None, env=None):
    r = subprocess.run(
        args,
        capture_output=True,
        text=True,
        input=input,
        env={**os.environ, **BOT_ENV, **(env or {})},
    )
    if check and r.returncode:
        raise RuntimeError(
            f"{' '.join(args[:3])} (exit {r.returncode}): {r.stderr.strip()}"
        )
    return r


def soft(what, *args):
    """A best-effort command (a comment, a head delete): a failure is a ::warning::, never the run's."""
    r = run(*args, check=False)
    if r.returncode:
        print(f"::warning::{what} failed (exit {r.returncode}): {r.stderr.strip()}")
    return r


def gh(*args, token=None):
    """Gh as GH_TOKEN, or as token (another repo's) when given."""
    return run("gh", *args, env={"GH_TOKEN": token} if token else None).stdout.strip()


def conflict_prs(slug, base=None, token=None):
    """Open backport-conflict PRs of repo slug, [{number, url, baseRefName, createdAt}], only those on base when given.
    A failed listing raises: it never reads as no PRs.
    """
    prs = json.loads(
        gh(
            "pr",
            "list",
            "-R",
            slug,
            "--label",
            "backport-conflict",
            "--state",
            "open",
            "--json",
            "number,url,baseRefName,createdAt",
            "--limit",
            "200",
            token=token,
        )
    )
    return [p for p in prs if base is None or p["baseRefName"] == base]


def open_conflicts(lines, annotate="warning"):
    """lines: [(slug, branch, token)]. One ::annotate per open backport-conflict PR on each line, then
    (refs like `slug#n`, one summary line or None). A failed listing raises.
    """
    refs, links = [], []
    for slug, branch, token in lines:
        for p in conflict_prs(slug, branch, token):
            ref = f"{slug}#{p['number']}"
            print(
                f"::{annotate}::Open backport conflict PR {ref} on {branch}: resolve and merge it, or close it to decline"
            )
            refs.append(ref)
            links.append(f"[{ref}]({p['url']}) on `{branch}`")
    return refs, (f"⚠ Open backport conflict PRs: {', '.join(links)}" if links else None)


def resolve(slug, item):
    """A main SHA or PR number (`#` optional) -> full SHA on origin/main; None if it is not on main."""
    item = item.removeprefix("#")  # the summary's paste command names PRs as #n
    if re.fullmatch(
        r"\d{1,6}", item
    ):  # PR numbers are short; SHAs given here are 7+ hex chars
        pr = json.loads(gh("api", f"repos/{slug}/pulls/{item}"))
        if not pr["merged"]:
            return None
        item = pr["merge_commit_sha"]
    r = rm.git(REPO, "rev-parse", "-q", "--verify", f"{item}^{{commit}}", check=False)
    sha = r.stdout.strip()
    return sha if r.returncode == 0 and rm.is_ancestor(REPO, sha, "origin/main") else None


def main_order(repo, shas):
    """Shas oldest first in main's history, duplicates dropped, whatever order the caller gave."""
    return rm.git(repo, "rev-list", "--reverse", "--no-walk=sorted", *shas).split()


def fix_class(slug, sha, token=None):
    """(class, PR ref, PR title) from the PR that merged sha, via relmgr.pr_fix_class (same rule as Lint PR).
    token: another repo's, as in gh().
    """
    try:
        out = gh("api", f"repos/{slug}/commits/{sha}/pulls", token=token)
    except RuntimeError:  # a read, and a rescan makes dozens: retry a transient error once ("unexpected end of JSON input")
        out = gh("api", f"repos/{slug}/commits/{sha}/pulls", token=token)
    prs = json.loads(out)
    if not prs:
        return None, "no PR", None
    pr = prs[0]
    return (
        rm.pr_fix_class(pr["title"], [label["name"] for label in pr["labels"]]),
        f"#{pr['number']}",
        pr["title"],
    )


def pr_body(sha, src, branch, head, files=()):
    """Body of the pick PR; files = conflicted paths (empty for a clean pick)."""
    origin = f"Backport of {src} (`{sha}`) to `{branch}`"
    if not files:
        return f"{origin}. Clean pick; the bot squash-merges it in the same Backport run."
    return (
        f"{origin} conflicted. The conflicted tree is committed **with markers** in:\n\n"
        + "".join(f"- `{p}`\n" for p in files)
        + f"\nResolve on this branch (`{head}`): amend the pick commit or push a fix-up commit; the "
        f"first commit's `(cherry picked from commit {sha})` line carries into the squash. Conflict markers "
        "left in any file fail the PR check. Resolve, get one approval and merge, or close the PR to decline (the close comment is the reason)."
    )


def only_listed(targets, listed):
    """(targets kept, listed branches that are not targets); an empty listed keeps every target."""
    if not listed:
        return targets, []
    return [b for b in targets if b in listed], [b for b in listed if b not in targets]


def held_line(sha, cls, pr, branch, annotate="warning", slug=None):
    """slug: the other repo the fix is from, named before its PR."""
    return f"::{annotate}::{sha[:7]} ({cls}, PR {slug or ''}{pr}) held for {branch}: stabilized, needs confirm_stabilized"


def held_warnings(awaiting):
    """One warning per stabilized branch (first-seen order) for awaiting [(sha, branch, class, PR ref)]."""
    counts = {}
    for _, b, *_ in awaiting:
        counts[b] = counts.get(b, 0) + 1
    return [
        f"::warning::{b}: {n} held security/critical fix{'es' if n > 1 else ''}, Backport with confirm_stabilized"
        for b, n in counts.items()
    ]


STALE_DAYS = 5  # a pending item this many days old gets a stale mark


def link_pr(ref):
    """A `#n` PR ref as a link; anything else ("no PR", "-") as is."""
    return rm.pr_link(int(ref[1:])) if re.fullmatch(r"#\d+", ref) else ref


def latest_tag(repo, branch):
    """(newest tag on the line, RC or stable, commits on the branch after it), or (None, None) before any.
    A stable tag ranks above the RC it was promoted from (same commit, same patch).
    """
    line = branch.split("/", 1)[1]
    tags = [
        t
        for t in rm.git(
            repo, "tag", "--merged", f"origin/{branch}", "-l", f"{rs.PREFIX}v{line}.*"
        ).split()
        if (m := rs.VER_RE.fullmatch(t)) and f"{m[1]}.{m[2]}" == line
    ]
    if not tags:
        return None, None
    m = lambda t: rs.VER_RE.fullmatch(t)
    tag = max(tags, key=lambda t: (int(m(t)[3]), m(t)[4] is None, int(m(t)[4] or 0)))
    return tag, int(rm.git(repo, "rev-list", "--count", f"{tag}..origin/{branch}"))


def next_step(conflicts, held_n, tag, unbuilt):
    """The one thing to do next on a line; first match wins."""
    if conflicts:
        return f"resolve {rm.pr_link(conflicts[0])}"
    if held_n:
        return f"RM: confirm {held_n} security fix" + ("es" if held_n > 1 else "")
    driver = (
        "cloud " if rs.PREFIX else ""
    )  # prefixed (OSS) lines are built and promoted by the cloud workflows
    if unbuilt:
        return f"{driver}Take RC"
    if tag and "-rc." in tag:
        return f"{driver}Promote"
    return "-"


def status_row(branch, state, tag, unbuilt, missing, conflicts, held_n):
    """One `| line | state | latest tag | missing | pending | next step |` row; conflicts: open conflict PR numbers."""
    built = (
        "none"
        if tag is None
        else f"{rm.tag_link(tag)} · "
        + (f"+{unbuilt} not built" if unbuilt else "all built")
    )
    pending = ", ".join(
        ([f"{len(conflicts)} conflict"] if conflicts else [])
        + ([f"{held_n} RM"] if held_n else [])
    )
    return (
        f"| `{branch}` | {state} | {built} | {missing} | {pending or '-'} | "
        f"{next_step(conflicts, held_n, tag, unbuilt)} |"
    )


def this_run(rows):
    """Only what this run did: merged picks, new conflict PRs, failures (skipped and invalid rows are left out)."""
    out = []
    for sha, pr, _, b, res, _ in rows:
        src = link_pr(pr) if pr.startswith("#") else rm.commit_link(sha)
        # finish_open adds ", retried" when it merges a pick PR an earlier run left open.
        if m := re.fullmatch(r"merged (\w+) \(#(\d+)(?:, retried)?\)", res):
            out.append(
                f"- {src} → `{b}`: merged as {rm.commit_link(m[1])} ({rm.pr_link(int(m[2]))})"
            )
        elif res.startswith("pr "):
            out.append(
                f"- {src} → `{b}`: conflict, {rm.pr_link(int(res.rsplit('/', 1)[1]))} to resolve"
            )
        elif res.startswith("failed"):
            out.append(f"- {src} → `{b}`: {res}")
    return out


def stale(days):
    return f"{days} day{'s' if days != 1 else ''}" + (" ⚠" if days >= STALE_DAYS else "")


def pending_block(conflicts, held_rows):
    """Folded detail. conflicts: [(n, base, days open)]; held_rows: [(sha, branch, class, PR ref, days since the
    main merge)] for stabilized lines, grouped per commit, then one command that picks them all.
    """
    groups = {}
    for sha, b, cls, pr, days in held_rows:
        groups.setdefault(sha, [cls, pr, days, []])[3].append(b)
    n = len(conflicts) + len(groups)
    if not n:
        return []
    out = [f"<details><summary>Pending ({n})</summary>", ""]
    if conflicts:
        out += [
            "**Conflict PRs** (resolve and merge, or close with `Declined: <reason>`):",
            "",
        ]
        out += [
            f"- {rm.pr_link(c)} on `{b}` · open {stale(d)}" for c, b, d in conflicts
        ] + [""]
    if groups:
        out += [
            "**Held for the RM** (stabilized lines; pick with `confirm_stabilized`):",
            "",
        ]
        out += [
            f"- {link_pr(pr)} {cls} → "
            + ", ".join(f"`{b}`" for b in bs)
            + f" · merged {stale(d)} ago"
            for cls, pr, d, bs in groups.values()
        ]
        commits = ",".join(
            pr if re.fullmatch(r"#\d+", pr) else sha[:12]
            for sha, (_, pr, _, _) in groups.items()
        )
        branches = ",".join(
            dict.fromkeys(b for _, _, _, bs in groups.values() for b in bs)
        )
        out += [
            "",
            "```",
            f"gh workflow run backport.yaml -f commits={commits} -f branches={branches} "
            "-f confirm_stabilized=true",
            "```",
            "",
        ]
    return out + ["</details>"]


def push_summary(head, table, done, pending):
    """Push mode summary lines; a quiet push (nothing done, nothing pending) is the head line alone."""
    if not done and not pending:
        return [f"{head} · nothing picked, nothing pending"]
    out = [
        f"### {head}",
        "",
        "| line | state | latest tag | missing | pending | next step |",
        "|---|---|---|---|---|---|",
        *table,
        "",
    ]
    out += (
        ["**This run**", "", *done, ""] if done else ["**This run:** nothing picked", ""]
    )
    return out + pending


HELD = {"security", "critical"}
OWED = {"fix", "security", "critical"}
UNCLASSIFIABLE = "UNCLASSIFIABLE"  # no PR found, or a title Lint PR should have refused: shown, never dropped


def held_filter(commits, classes, trailers, accept=HELD):
    """Pure core of held(): the main commits whose class is in accept (or UNCLASSIFIABLE) and that no pick or
    decline trailer on the branch names (trailers may be abbreviated). classes: {sha: (class, PR ref, ...)}.
    """
    return [
        (s, *classes[s])
        for s in commits
        if classes[s][0] in accept | {UNCLASSIFIABLE}
        and not any(s.startswith(t) for t in trailers)
    ]


def classes_from_listing(prs):
    """Pure: {merge sha: (class, PR ref, title)} from `gh pr list --json number,title,labels,mergeCommit` rows; a title
    Lint PR should have refused maps to UNCLASSIFIABLE with the error, as in held().
    """
    out = {}
    for pr in prs:
        if not pr.get("mergeCommit"):
            continue
        try:
            cls = rm.pr_fix_class(pr["title"], [label["name"] for label in pr["labels"]])
            out[pr["mergeCommit"]["oid"]] = (cls, f"#{pr['number']}", pr["title"])
        except ValueError as e:
            out[pr["mergeCommit"]["oid"]] = (UNCLASSIFIABLE, str(e), pr["title"])
    return out


def pr_classes(slug, since):
    """{merge sha: (class, PR ref, title)} for every PR merged into main since `since` (YYYY-MM-DD): one search
    listing per run, labels read now, so a label edited after the merge counts. A failed listing returns {}:
    held() then looks each commit up on its own.
    """
    # ponytail: the search API stops at 1000 results; a range with more merged PRs falls back per commit beyond them.
    try:
        out = gh(
            "pr",
            "list",
            "-R",
            slug,
            "--state",
            "merged",
            "--base",
            "main",
            "--search",
            f"merged:>={since}",
            "--limit",
            "1000",
            "--json",
            "number,title,labels,mergeCommit",
        )
    except RuntimeError as e:
        print(f"::warning::PR listing failed, classing commit by commit: {e}")
        return {}
    return classes_from_listing(json.loads(out))


def held(slug, repo, branch, accept=HELD, cache=None, token=None):
    """[(sha, class, PR ref, title)] of main commits since branch's cut whose class is in accept (or
    UNCLASSIFIABLE), neither picked nor declined: the held (or, with OWED, owed) picks the RM must see.
    cache: {sha: (class, PR ref, title)} shared across calls (the rescan primes it from pr_classes), so a main commit
    is looked up on its own at most once per run: only when the listing missed it (no PR, search index lag).
    token: slug's, when slug is not this repo (the OSS line).
    """
    remote = f"origin/{branch}"
    base = rm.git(repo, "merge-base", "origin/main", remote)
    # First parent, no merges: a merge-back's merge and the old release commits it brings in are not main's own. The
    # bot's direct commits (RC Helm bumps) are build-generated, as relmgr.classify_commit classes them.
    out = rm.git(
        repo,
        "log",
        "--reverse",
        "--first-parent",
        "--no-merges",
        "--format=%H %ae",
        f"{base}..origin/main",
    )
    commits = [
        sha
        for sha, email in (row.split(" ", 1) for row in out.splitlines())
        if email.lower() != rm.BOT_EMAIL.lower()
    ]
    classes = {} if cache is None else cache
    looked = 0
    for s in commits:
        if s in classes:
            continue
        looked += 1
        try:
            cls, pr, title = fix_class(slug, s, token=token)
            classes[s] = (
                (UNCLASSIFIABLE, pr, rm.git(repo, "log", "-1", "--format=%s", s))
                if pr == "no PR"
                else (cls, pr, title)
            )
        except ValueError as e:  # a title Lint PR should have stopped
            classes[s] = (
                UNCLASSIFIABLE,
                str(e),
                rm.git(repo, "log", "-1", "--format=%s", s),
            )
    print(
        f"held: {len(commits)} main commit(s) since the cut of {branch}, {looked} fix_class lookup(s)"
    )
    # A decline carries the same trailer as a pick, so one grep covers both.
    trailers = {
        o
        for c in rm.git(
            repo,
            "log",
            "--format=%H",
            "-F",
            "--grep=(cherry picked from commit",
            f"{base}..{remote}",
        ).split()
        for o in rm.picked_from(repo, c)
    }
    return held_filter(commits, classes, trailers, accept)


def owed_summary(rows, branch):
    """Markdown: the owed-picks table for a branch gaining a late target, plus the line to paste into Backport's
    commits input (UNCLASSIFIABLE rows are listed but left out of it: Backport cannot class them either).
    """
    out = [
        f"**Owed picks** for `{branch}`: main fixes since the cut, neither picked nor declined",
        "",
    ]
    if not rows:
        return "\n".join(out + ["none"])
    out += ["| commit | PR | title | class |", "|---|---|---|---|"]
    cell = lambda t: t.replace("|", r"\|")  # a pipe in a title would split the row
    out += [f"| `{s[:7]}` | {pr} | {cell(title)} | {cls} |" for s, cls, pr, title in rows]
    return "\n".join(
        out
        + [
            "",
            "Backport commits: "
            + " ".join(s for s, cls, *_ in rows if cls != UNCLASSIFIABLE),
        ]
    )


def warn_held(slug, repo, branch, annotate="warning", token=None):
    """Take RC build / Promote on a stabilized branch: one annotation per held fix (Promote blocks on them unless
    forced). Returns the summary line (the fixes, linked, and the RM's confirm command), or None when nothing is held.
    """
    rows = held(slug, repo, branch, token=token)
    other = slug if token else None  # a token means another repo: name it
    for s, cls, pr, _ in rows:
        print(held_line(s, cls, pr, branch, annotate, other))
    return held_note(rows, branch, other)


def held_note(rows, branch, slug=None):
    """One summary line for held() rows of stabilized `branch`, or None. slug: the other repo the rows are from."""
    if not rows:
        return None
    commits = ",".join(
        pr if re.fullmatch(r"#\d+", pr) else s[:12] for s, _, pr, _ in rows
    )
    link = (
        (
            lambda pr: f"[{slug}{pr}](https://github.com/{slug}/pull/{pr[1:]})"
            if pr.startswith("#")
            else pr
        )
        if slug
        else link_pr
    )
    return (
        f"⚠ Held for the RM on {f'{slug} ' if slug else ''}`{branch}` (stabilized; Promote blocks unless forced): "
        + ", ".join(f"{link(pr)} {cls}" for _, cls, pr, _ in rows)
        + f". Pick with `gh workflow run backport.yaml{f' -R {slug}' if slug else ''} -f commits={commits} "
        f"-f branches={branch} -f confirm_stabilized=true`"
    )


def rescan_targets(targets, listed):
    """({branch: accept} to rescan, listed branches that are no target): fix targets owe plain fixes too (OWED),
    the other security/critical targets (stabilized) only HELD. listed narrows, never adds.
    """
    scan = {b: OWED for b in targets["fix"]}
    for t in targets["security_critical"]:
        scan.setdefault(t["branch"], HELD)
    kept, others = only_listed(list(scan), listed)
    return {b: scan[b] for b in kept}, others


def rescan_plan(targets, held_by_branch, confirm):
    """Pure: (plan, awaiting, unclassifiable) from each rescanned branch's held() rows (main order, picked and
    declined commits already dropped). plan: [(branch, sha, class, PR ref, title)], each branch in main order;
    awaiting: [(sha, branch, class, PR ref)] on a stabilized branch without confirm; unclassifiable:
    [(sha, branch, PR ref, title)], never picked.
    """
    stabilized = {
        t["branch"] for t in targets["security_critical"] if t["needs_rm_confirmation"]
    }
    plan, awaiting, unclassifiable = [], [], []
    for b, rows in held_by_branch.items():
        for sha, cls, pr, title in rows:
            if cls == UNCLASSIFIABLE:
                unclassifiable.append((sha, b, pr, title))
            elif b in stabilized and not confirm:
                awaiting.append((sha, b, cls, pr))
            else:
                plan.append((b, sha, cls, pr, title))
    return plan, awaiting, unclassifiable


def pick_row(slug, sha, b, cls, pr, title):
    """Pick sha onto b and return its summary row; a failure never stalls the other branches."""
    try:
        rel = rm.relevance(
            REPO, sha, f"origin/{b}"
        )  # advisory only: never skips the pick
    except Exception as e:
        rel = f"unknown ({type(e).__name__}: {(str(e).splitlines() or [''])[0]})".replace(
            "|", r"\|"
        )  # a table cell
        print(f"::warning::{sha[:7]} relevance on {b}: {rel}")
    try:
        outcome, detail = pick(slug, sha, b, title, pr)
    except (
        Exception
    ) as e:  # branches are independent: one failure never stalls the others
        traceback.print_exc()
        run("git", "cherry-pick", "--abort", check=False)
        outcome, detail = "failed", f"{type(e).__name__}: {e}"
    print(f"{sha[:7]} {cls} {b}: {outcome} {detail}")
    return (
        sha,
        pr,
        cls,
        b,
        f"{outcome}{':' if outcome in ('skipped', 'failed') else ''} {detail}",
        rel,
    )


def rescan(slug, targets, confirm, listed):
    """Push mode: (rows, awaiting, {branch: missing}) over every target since its cut (see the module doc).
    Known limit: no test drives rescan itself; rescan_plan and held are tested on their own.
    """
    scan, others = rescan_targets(targets, listed)
    rows = []
    for b in others:
        print(f"::warning::{b} is not a target, skipped")
        rows.append(("-" * 7, "-", "-", b, "skipped: not a target", "-"))
    cuts = [rm.git(REPO, "merge-base", "origin/main", f"origin/{b}") for b in scan]
    oldest = min(
        (rm.git(REPO, "log", "-1", "--format=%cI", c) for c in cuts), default=None
    )
    since = (
        (datetime.datetime.fromisoformat(oldest) - datetime.timedelta(days=1)).date()
        if oldest
        else None
    )
    classes = (
        pr_classes(slug, since.isoformat()) if since else {}
    )  # a day's margin for clock and merge-time skew
    listed_n = len(classes)
    held_by_branch = {
        b: held(slug, REPO, b, accept=accept, cache=classes) for b, accept in scan.items()
    }
    print(f"rescan: {listed_n} PRs listed, {len(classes) - listed_n} fallback lookup(s)")
    plan, awaiting, unclassifiable = rescan_plan(targets, held_by_branch, confirm)
    # A human fixes the merged PR's title or adds a fix/ label (declines it when there is no PR); re-warned each push.
    for sha, b, pr, title in unclassifiable:
        print(
            f"::warning::{sha[:7]} ({pr}, {title}) cannot be classed for {b}: not picked"
        )
        rows.append((sha, pr, UNCLASSIFIABLE, b, "skipped: unclassifiable", "-"))
    for b, sha, cls, pr, title in plan:
        rows.append(pick_row(slug, sha, b, cls, pr, title))
    missing = {}
    for b in scan:
        results = [r[4] for r in rows if r[3] == b]
        picked = sum(res.startswith("merged") for res in results)
        pending = sum(
            res.startswith("pr ") or "pending" in res for res in results
        )  # conflict PR, or merge held
        missing[b] = len(held_by_branch[b]) - picked
        print(
            f"rescan {b}: {len(held_by_branch[b])} missing, {picked} picked, {pending} pending"
        )
    return rows, awaiting, missing


PUSH_WAITS = (5, 20)  # seconds before the 2nd and 3rd push attempt
PICK_TIMEOUT = (
    30 * 60
)  # seconds: the pick job's timeout-minutes in backport.yaml; no run holds a head longer


def run_url():
    """This Actions run's URL, or None outside Actions."""
    e = os.environ
    return (
        f"{e['GITHUB_SERVER_URL']}/{e['GITHUB_REPOSITORY']}/actions/runs/{e['GITHUB_RUN_ID']}"
        if e.get("GITHUB_RUN_ID")
        else None
    )


def push_head(slug, sha, branch, head, src, sleep=time.sleep):
    """Push HEAD to head, retrying a rejection. None on success; after the last attempt ("failed", detail),
    nothing pushed, the sentence on the run's ::error:: and as a comment on the source PR (Actions only). A pick
    another run landed meanwhile is ("skipped", detail), with no comment.
    """
    first = None
    for wait in (*PUSH_WAITS, None):
        r = run("git", "push", "-q", "origin", f"HEAD:refs/heads/{head}", check=False)
        if r.returncode == 0:
            return None
        lines = (r.stderr.strip() or r.stdout.strip()).splitlines() or [
            f"exit {r.returncode}"
        ]
        # git prints "To <remote>" first; the "! [remote rejected] ..." or "error:" line names the cause
        first = first or next(
            (
                l.strip()
                for l in lines
                if l.lstrip().startswith(("!", "error:", "fatal:"))
            ),
            lines[0],
        )
        if wait is not None:
            sleep(wait)
    run(
        "git",
        "fetch",
        "-q",
        "origin",
        f"+refs/heads/{branch}:refs/remotes/origin/{branch}",
        check=False,
    )
    if rm.is_converged(
        REPO, sha, f"origin/{branch}", main="origin/main"
    ):  # the run that won the head landed it
        return (
            "skipped",
            f"already on branch (push of {head} rejected: another run landed the pick)",
        )
    url = run_url()
    # convgate.missing_message matches this first line on the source PR: keep the two in step.
    sentence = (
        f"Backport to {branch} failed: push of {head} rejected (run {url or 'outside Actions'}). "
        f"Rerun Backport for {sha[:7]} on {branch}."
    )
    print(f"::error::{sentence}")
    # Not de-duplicated: a push rejected on every run comments on every run (convgate reads only the newest).
    if url and re.fullmatch(r"#\d+", src):
        soft(
            f"comment on {src}",
            "gh",
            "pr",
            "comment",
            src[1:],
            "-R",
            slug,
            "--body",
            f"{sentence}\n\n`{first}`",
        )
    return "failed", f"push of {head} rejected {len(PUSH_WAITS) + 1} times: {first}"


CONFLICTS_RE = re.compile(
    r"^Conflicts:\n\t", re.M
)  # the block pick() adds to a conflict pick's message


def fix_labels(slug, src):
    """The fix/* labels of the original PR src (`#n`), for its pick PR: Lint PR classes a pick PR by them too."""
    if not re.fullmatch(r"#\d+", src):
        return []
    names = gh("api", f"repos/{slug}/pulls/{src[1:]}", "--jq", ".labels[].name").split(
        "\n"
    )
    return [x for x in names if x.startswith("fix/")]


def finish_open(slug, branch, head):
    """The pick head already exists. An open unlabelled PR the bot opened, with one commit carrying the pick trailer
    of the head's sha7, is a clean pick whose merge failed in an earlier run: squash it now, unless it is a conflict
    pick that lost its label. A PR a person opened fails unmerged; a bot PR carrying any backport-* label waits for a
    person; more than one commit or none, or one commit without that trailer, fails unmerged. A head with no open PR waits PICK_TIMEOUT for the run
    that pushed it, then fails until a person deletes it or reopens its PR.
    Known limits: the trailer is checked, not the commit's content, so a writer who force-pushes the bot's open pick
    PR with one commit carrying that trailer gets it squashed (a writer can already run a workflow with the App's
    token). A head whose PR was closed but whose decline record failed also reads as "no open PR": deleting that
    head re-picks the declined fix; re-run the record job instead. A closed pick PR whose head has no commit past
    the base also fails every run until the head is deleted (deliberately, see the module docstring). The age is
    the head tip's commit time, so a head moved onto a fresh base tip reads as "another run is picking it" for up
    to PICK_TIMEOUT.
    """
    pending = "skipped", f"conflict PR pending on `{head}`"
    prs = json.loads(
        gh(
            "pr",
            "list",
            "-R",
            slug,
            "--head",
            head,
            "--base",
            branch,
            "--state",
            "open",
            "--json",
            "number,headRefOid,labels,author",
        )
    )
    if (
        not prs
    ):  # a running run opens its PR after the push and deletes the head after the squash
        run(
            "git",
            "fetch",
            "-q",
            "origin",
            f"+refs/heads/{head}:refs/remotes/origin/{head}",
        )
        age = time.time() - int(
            rm.git(REPO, "log", "-1", "--format=%ct", f"origin/{head}")
        )
        if age < PICK_TIMEOUT:
            return (
                "skipped",
                f"head {head} is {int(age // 60)} min old with no open PR: another run is picking it",
            )
        # A head with no commit past the base: reopening its PR only parks it as a conflict PR with nothing to merge.
        empty = (
            rm.git(REPO, "rev-list", "--count", f"origin/{branch}..origin/{head}") == "0"
        )
        return (
            "failed",
            f"head {head} exists with no open PR: delete it"
            + ("" if empty else " or reopen its PR")
            + ", then rerun",
        )
    if len(prs) != 1:
        return pending
    pr, remote = prs[0], f"origin/{branch}"
    # The bot squashes with a token that bypasses the release ruleset: only its own PR, with one commit carrying
    # its pick trailer (the trailer, not the content: see the docstring). A person's PR fails even when labelled:
    # the record job would refuse it once merged.
    if why := bm.bot_refusal(pr):
        return "failed", f"{why}: not merged"
    if any(x["name"].startswith("backport-") for x in pr["labels"]):
        return pending
    run("git", "fetch", "-q", "origin", f"+refs/heads/{head}:refs/remotes/origin/{head}")
    # A person's commit on the bot's unlabelled PR (say a fixup after a failed squash): no conflict PR lists it.
    if (n := rm.git(REPO, "rev-list", "--count", f"{remote}..{pr['headRefOid']}")) != "1":
        return (
            "failed",
            f"#{pr['number']} has {n} commits, not the one pick: not merged; "
            + (
                f"its head has no pick on {branch}: delete {head} (this closes #{pr['number']}), and the next "
                "Backport run treats the fix as not picked"
                if n == "0"
                else "label it backport-conflict, then merge it, or close it to decline"
            ),
        )
    msg = rm.git(REPO, "log", "-1", "--format=%B", pr["headRefOid"])
    if not rm.pick_trailer(head, msg):
        return (
            "failed",
            f"#{pr['number']}: its commit lacks the pick trailer {head} names: not merged",
        )
    if rm.conflict_markers(REPO, pr["headRefOid"]) or CONFLICTS_RE.search(msg):
        return "failed", (
            f"#{pr['number']} is a conflict pick without the backport-conflict label: label it "
            "backport-conflict, then resolve and merge it, or close it to decline"
        )
    try:
        if not bm.squash(slug, pr, msg):
            return "failed", f"#{pr['number']} merge pending check"
    except RuntimeError as e:
        return "failed", f"#{pr['number']} merge retry: {str(e).splitlines()[0]}"
    soft(
        f"delete of {head}",
        "gh",
        "api",
        "-X",
        "DELETE",
        f"repos/{slug}/git/refs/heads/{head}",
    )
    run("git", "fetch", "-q", "origin", f"+refs/heads/{branch}:refs/remotes/{remote}")
    return (
        "merged",
        f"{rm.git(REPO, 'rev-parse', '--short=7', remote)} (#{pr['number']}, retried)",
    )


def pick(slug, sha, branch, title, src):
    """Returns (outcome, detail); outcome in merged | pr | skipped | failed. title: PR title; src: original PR ref."""
    remote = f"origin/{branch}"
    # Fresh tip: an overlapping run may have merged this pick after this run fetched.
    run("git", "fetch", "-q", "origin", f"+refs/heads/{branch}:refs/remotes/{remote}")
    if rm.is_converged(REPO, sha, remote, main="origin/main"):
        return "skipped", "already on branch"
    head = f"backport/{branch.split('/', 1)[1]}/{sha[:7]}"
    if (
        run(
            "git", "ls-remote", "--exit-code", "--heads", "origin", head, check=False
        ).returncode
        == 0
    ):  # known limit: any other ls-remote failure (network, auth) reads as "no head", and the pick push then fails
        return finish_open(slug, branch, head)
    labels = [x for name in fix_labels(slug, src) for x in ("--label", name)]
    run("git", "checkout", "-q", "--detach", remote)
    r = run("git", "cherry-pick", "-x", sha, check=False)
    if r.returncode == 0:
        pick_sha = rm.git(REPO, "rev-parse", "HEAD")
        if failed := push_head(slug, sha, branch, head, src):
            return failed
        url = gh(
            "pr",
            "create",
            "-R",
            slug,
            "--base",
            branch,
            "--head",
            head,
            "--title",
            title,
            *labels,
            "--body",
            pr_body(sha, src, branch, head),
        )
        n = int(url.rsplit("/", 1)[1])
        # backport_merge.squash: REST squash pinned to the head, with the pick's message.
        # A required check GitHub still waits for -> False: PR and head stay, the next run reports it pending.
        if not bm.squash(
            slug,
            {"number": n, "headRefOid": pick_sha},
            rm.git(REPO, "log", "-1", "--format=%B", pick_sha),
        ):
            return "failed", f"{url} opened, merge pending check"
        soft(
            f"delete of {head}",
            "gh",
            "api",
            "-X",
            "DELETE",
            f"repos/{slug}/git/refs/heads/{head}",
        )
        run(
            "git", "fetch", "-q", "origin", f"+refs/heads/{branch}:refs/remotes/{remote}"
        )  # later picks stack on it
        return "merged", f"{rm.git(REPO, 'rev-parse', '--short=7', remote)} (#{n})"
    # -z: a path with a space or a non-ASCII name comes back unquoted and in one piece (rm.git's strip can still
    # drop a leading space on the first path; only the commit message and PR body read this list).
    files = [
        f
        for f in rm.git(REPO, "diff", "--name-only", "-z", "--diff-filter=U").split("\0")
        if f
    ]
    if not files:  # not a conflict a human can resolve on a PR
        empty = rm.git(
            REPO, "rev-parse", "-q", "--verify", "CHERRY_PICK_HEAD", check=False
        ).returncode == 0 and not rm.git(
            REPO, "status", "--porcelain", "--untracked-files=no"
        )
        run("git", "cherry-pick", "--abort", check=False)
        if empty:
            return "failed", (
                f"pick of {sha[:7]} onto {branch} is empty: the change is already there in another "
                f"form. Record a decline: an empty commit on {branch} with the lines `(cherry picked "
                f"from commit {sha})` and `Declined: already on {branch}`"
            )
        return "failed", (
            (r.stderr.strip() or r.stdout.strip()).splitlines()
            or [f"cherry-pick exit {r.returncode}"]
        )[0]
    # The message cherry-pick -x prepared (subject, body, trailer), minus git's commented hints.
    with open(os.path.join(REPO, ".git", "MERGE_MSG")) as f:
        msg = "".join(line for line in f if not line.startswith("#")).strip()
    msg += "\n\nConflicts:\n" + "".join(f"\t{p}\n" for p in files)
    # -u: tracked and unmerged paths only; -A would also commit untracked files such as state.json.
    run("git", "add", "-u")
    run("git", "commit", "-q", "--no-verify", "-F", "-", input=msg)
    if failed := push_head(slug, sha, branch, head, src):
        return failed
    url = gh(
        "pr",
        "create",
        "-R",
        slug,
        "--base",
        branch,
        "--head",
        head,
        "--label",
        "backport-conflict",
        *labels,
        "--title",
        title,
        "--body",
        pr_body(sha, src, branch, head, files),
    )
    return "pr", url


def push_title(slug, sha):
    """The push summary's head line: the pushed commit and its class."""
    # Known limit: a gh failure that survives fix_class's retry (RuntimeError) is not caught here and ends the run
    # before its summary.
    try:
        cls, pr, _ = fix_class(slug, sha)
    except ValueError as e:  # a title Lint PR should have stopped: the picks are done, only this line is left
        print(f"::warning::{sha[:7]}: fix class: {e}")
        cls, pr = UNCLASSIFIABLE, "-"
    return f"Backport · push {rm.commit_link(sha)} ({link_pr(pr)}, {cls or 'not a fix'})"


def main():
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--state", required=True)
    mode = p.add_mutually_exclusive_group(required=True)
    mode.add_argument(
        "--commits",
        help="main SHAs or merged PR numbers, comma- or space-separated, any order",
    )
    mode.add_argument(
        "--rescan", action="store_true", help="every target since its cut (push to main)"
    )
    p.add_argument("--confirm-stabilized", action="store_true")
    p.add_argument(
        "--branches",
        default="",
        help="comma list: only these release branches (default every target)",
    )
    a = p.parse_args()
    slug = os.environ["GITHUB_REPOSITORY"]
    with open(a.state) as f:
        state = json.load(f)
    targets = state["backport_targets"]
    listed = [b.strip() for b in a.branches.split(",") if b.strip()]
    if a.rescan:
        rows, awaiting, missing = rescan(slug, targets, a.confirm_stabilized, listed)
    else:
        rows, awaiting = dispatch(slug, targets, a.commits, a.confirm_stabilized, listed)
    failed = sum(res.startswith("failed") for *_, res, _ in rows)
    if awaiting:
        print("\n".join(held_warnings(awaiting)))  # a held pick is never silent

    now = datetime.datetime.now(datetime.UTC)
    days = lambda iso: (
        now - datetime.datetime.fromisoformat(iso.replace("Z", "+00:00"))
    ).days
    conflicts = sorted(
        (p["number"], p["baseRefName"], days(p["createdAt"])) for p in conflict_prs(slug)
    )
    held_rows = [
        (s, b, c, pr, days(rm.git(REPO, "log", "-1", "--format=%cI", s)))
        for s, b, c, pr in awaiting
    ]
    pending = pending_block(conflicts, held_rows)
    if a.rescan:
        head = push_title(
            slug, os.environ.get("GITHUB_SHA") or rm.git(REPO, "rev-parse", "origin/main")
        )
        states = {r["branch"]: r["state"] for r in state["branches"]}
        table = []
        for b in missing:
            tag, unbuilt = latest_tag(REPO, b)
            table.append(
                status_row(
                    b,
                    states.get(b, "-"),
                    tag,
                    unbuilt,
                    missing[b],
                    [n for n, base, _ in conflicts if base == b],
                    sum(x[1] == b for x in awaiting),
                )
            )
        out = push_summary(head, table, this_run(rows), pending)
    else:  # the person named these commits: every row answers them, skipped ones included
        out = [
            "### Backport · dispatch",
            "",
            "| commit | PR | class | branch | result | relevance |",
            "|---|---|---|---|---|---|",
        ]
        out += [
            f"| `{s[:7]}` | {pr} | {c} | {b} | {res} | {rel} |"
            for s, pr, c, b, res, rel in rows
        ]
        out += [""] + pending
    print("\n".join(out))
    if os.environ.get("GITHUB_STEP_SUMMARY"):
        with open(os.environ["GITHUB_STEP_SUMMARY"], "a") as f:
            f.write("\n".join(out) + "\n")
    return 1 if failed else 0


def dispatch(slug, targets, commits, confirm, listed):
    """Dispatch mode: (rows, awaiting) for the given commits only."""
    items = [
        c for c in re.split(r"[,\s]+", commits) if c
    ]  # commas or spaces: the owed-picks line pastes as is
    shas = [resolve(slug, c) for c in items]
    if not items or None in shas:
        bad = [c for c, s in zip(items, shas, strict=False) if s is None]
        sys.exit(f"::error::refused: not merged commits on main: {bad or 'none given'}")
    shas = main_order(REPO, shas)

    rows, awaiting = [], []
    for sha in shas:
        try:
            cls, pr, title = fix_class(slug, sha)
        except ValueError as e:  # Lint PR should have stopped this PR
            print(f"::error::{sha[:7]}: fix class: {e}")
            rows.append((sha, "?", "error", "-", f"skipped: {e}", "-"))
            continue
        if cls is None:
            route = (
                f"; label {pr} fix/needs-backport (or the fix label it needs) and rerun"
                if pr.startswith("#")
                else ""
            )
            rows.append((sha, pr, "none", "-", f"skipped: not a fix{route}", "-"))
            continue
        if cls == "fix":
            branches = targets["fix"]
        else:
            branches = [
                t["branch"]
                for t in targets["security_critical"]
                if confirm or not t["needs_rm_confirmation"]
            ]
            awaiting += [
                (sha, t["branch"], cls, pr)
                for t in targets["security_critical"]
                if t["needs_rm_confirmation"]
                and not confirm
                and (not listed or t["branch"] in listed)
            ]
        branches, others = only_listed(branches, listed)
        others = [b for b in others if (sha, b, cls, pr) not in awaiting]
        for b in others:
            print(f"::warning::{sha[:7]} ({cls}, PR {pr}): {b} is not a target, skipped")
            rows.append((sha, pr, cls, b, "skipped: not a target", "-"))
        if not branches and not others:
            rows.append((sha, pr, cls, "-", "skipped: no target branch", "-"))
        rows += [pick_row(slug, sha, b, cls, pr, title) for b in branches]
    return rows, awaiting


if __name__ == "__main__":
    sys.exit(main())
