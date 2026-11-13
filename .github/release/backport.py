"""Backport: cherry-pick (-x) main fixes onto every release branch that accepts them.

Usage: backport.py --state state.json (--commits SHA|PR[,...] | --rescan) [--patch-released-lines] [--lines X.Y[,...]]

--rescan (every push to main): pick every main commit since each target's cut that no trailer there names
(ga only on stabilized targets, held without --patch-released-lines). --commits (dispatch): only these;
with --patch-released-lines an rc fix also goes onto the stabilized lines --lines names.

Run from a full clone whose `origin` pushes with the bot token, with GH_TOKEN set to the bot token and
RELEASE_BOT_APP_SLUG set to the release App's slug.
Each pick is its own PR from backport/X.Y/<sha7> titled with the main PR's title, so PR-title changelogs list it.
A clean pick is squash-merged in the same run without waiting for checks: the bot bypasses the release ruleset,
and the push run of Release branch CI is the backstop.
A conflict is committed with markers and left open labelled backport-conflict for a person to resolve or close;
the record job (backport_merge.py) records the merge, or the close as a decline.
Targets come only from relstate's backport_targets: --lines narrows them, never adds one.
"""

import argparse
import collections
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
MAIN = "origin/main"
BOT_ENV = {"GIT_COMMITTER_NAME": "releases-bot", "GIT_COMMITTER_EMAIL": rm.BOT_EMAIL}
# The daily State run fails on an owed fix on a stabilizing line merged longer ago than this, and on a backport
# conflict PR open longer than CONFLICT_GRACE.
OWED_GRACE = datetime.timedelta(hours=2)
CONFLICT_GRACE = datetime.timedelta(hours=24)


def run(*args, check=True, input=None, env=None, retry=True):
    env = {**os.environ, **BOT_ENV, **(env or {})}
    if args[0] == "gh":
        r = bm.run_gh(args[1:], env=env, retry=retry, input=input)
    else:
        r = subprocess.run(args, capture_output=True, text=True, input=input, env=env)
    if check and r.returncode:
        raise RuntimeError(
            f"{' '.join(args[:3])} (exit {r.returncode}): {r.stderr.strip()}"
        )
    return r


def fetch_branch(name, check=True):
    return run(
        "git",
        "fetch",
        "-q",
        "origin",
        f"+refs/heads/{name}:refs/remotes/origin/{name}",
        check=check,
    )


def soft(what, *args):
    """A best-effort command (a comment, a head delete): a failure is a ::warning::, never the run's."""
    r = run(*args, check=False)
    if r.returncode:
        print(f"::warning::{what} failed (exit {r.returncode}): {r.stderr.strip()}")
    return r


def gh(*args, token=None, retry=True):
    return run(
        "gh", *args, env={"GH_TOKEN": token} if token else None, retry=retry
    ).stdout.strip()


def conflict_prs(slug, base=None, token=None):
    """A failed listing raises: it never reads as no PRs."""
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
            "number,url,baseRefName,headRefName,createdAt",
            "--limit",
            "200",
            token=token,
        )
    )
    return [p for p in prs if base is None or p["baseRefName"] == base]


def open_conflicts(lines, annotate="warning"):
    """A warning is safe for an open conflict PR: the pick is tracked there, and Promote blocks on it."""
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


def resolve(slug, item, prs=None):
    """Merge commit on main for a sha or PR number; a PR's JSON goes into prs, keyed by that sha."""
    item = item.removeprefix("#")  # the summary names PRs as #n
    if item.startswith("-"):
        return None  # never passed to git as an option
    if re.fullmatch(r"\d{1,6}", item):  # a PR number; SHAs are 7+ hex
        pr = json.loads(gh("api", f"repos/{slug}/pulls/{item}"))
        if not pr["merged"]:
            return None
        item = pr["merge_commit_sha"]
    else:
        pr = None
    sha = rm.resolve(REPO, item)
    if not (sha and rm.is_ancestor(REPO, sha, MAIN)):
        return None
    if pr and prs is not None:
        prs[sha] = pr
    return sha


def main_order(repo, shas):
    """Shas oldest first in main's history, duplicates dropped, whatever order the caller gave."""
    return rm.git(repo, "rev-list", "--reverse", "--no-walk=sorted", *shas).split()


def fix_class(slug, sha, token=None):
    """(class, PR ref, PR title) of the PR that merged sha; same rule as Lint PR."""
    out = gh("api", f"repos/{slug}/commits/{sha}/pulls", token=token)
    prs = json.loads(out)
    pr = prs[0] if prs else _subject_pr(slug, sha, token)
    return pr_class(pr) if pr else (None, "no PR", None)


def pr_class(pr):
    """A PR main_fix_class rejects is UNCLASSIFIABLE, keeping its #N; the error goes after its title."""
    try:
        return (
            rm.main_fix_class(pr["title"], _labels(pr)),
            f"#{pr['number']}",
            pr["title"],
        )
    except ValueError as e:
        return UNCLASSIFIABLE, f"#{pr['number']}", f"{pr['title']} ({e})"


def _subject_pr(slug, sha, token=None):
    """The merged PR a squash subject's trailing (#N) names, when GitHub's commit-to-PR index has no entry for sha."""
    commit = json.loads(gh("api", f"repos/{slug}/commits/{sha}", token=token))
    m = re.search(r"\(#(\d+)\)$", commit["commit"]["message"].split("\n", 1)[0])
    if not m:
        return None
    try:
        pr = json.loads(gh("api", f"repos/{slug}/pulls/{m[1]}", token=token))
    except RuntimeError:  # (#N) names an issue, or no longer exists
        return None
    # The subject is only a claim: trust it only for the PR that merged this exact commit.
    if not (pr["merged"] and pr["merge_commit_sha"] == sha):
        return None
    print(
        f"::notice::{sha[:7]}: no PR indexed for the commit; #{m[1]} from its subject merged it"
    )
    return pr


def _labels(pr):
    return [label["name"] for label in pr["labels"]]


def pr_body(sha, src, branch, head, files=()):
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
    """An empty listed keeps every target."""
    if not listed:
        return targets, []
    return [b for b in targets if b in listed], [b for b in listed if b not in targets]


def held_line(sha, cls, pr, branch, annotate="warning", slug=None, title=""):
    if cls == UNCLASSIFIABLE:  # a pick would fail: name the error instead
        return (
            f"::{annotate}::{sha[:7]} ({cls}, PR {slug or ''}{pr}, {title}) held for {branch}: "
            "add a backport label or fix its PR title, or record a decline"
        )
    return f"::{annotate}::{sha[:7]} ({cls}, PR {slug or ''}{pr}) held for {branch}: stabilized, needs patch_released_lines"


def held_warnings(awaiting):
    # Held for confirmation is a known state, not a missed pick: Promote blocks on it.
    counts = collections.Counter(b for _, b, *_ in awaiting)
    return [
        f"::warning::{b}: {n} held backport/ga fix{'es' if n > 1 else ''}, confirm with Backport and patch_released_lines"
        for b, n in counts.items()
    ]


STALE_DAYS = 5


def link_pr(ref):
    return rm.pr_link(int(ref[1:])) if re.fullmatch(r"#\d+", ref) else ref


def link_sha(sha):
    # Placeholder rows ("-------") have no commit to link.
    return rm.commit_link(sha) if re.fullmatch(r"[0-9a-f]{7,40}", sha) else f"`{sha[:7]}`"


def link_src(sha, pr, repo=None):
    if re.fullmatch(r"#\d+", pr):
        return rm.pr_link(int(pr[1:]), repo)
    return f"{rm.commit_link(sha, 7, repo)} ({pr})"


def link_branch(b):
    return rm.branch_link(b) if b != "-" else b


def dispatch_row(sha, pr, cls, b, res, rel):
    return f"| {link_sha(sha)} | {link_pr(pr)} | {cls} | {link_branch(b)} | {link_result(res)} | {rel} |"


def link_result(res):
    if m := re.fullmatch(r"merged (\w+) \(#(\d+)(, retried)?\)", res):
        return f"merged {rm.commit_link(m[1])} ({rm.pr_link(int(m[2]))}{m[3] or ''})"
    if m := re.fullmatch(r"pr \S+/pull/(\d+)", res):
        return f"pr {rm.pr_link(int(m[1]))}"
    return res


def latest_tag(repo, branch):
    """A stable tag ranks above the RC it was promoted from (same patch). A stable tag sits on Promote's GA commit,
    off the line, so a tag counts when its RC commit is on the line.
    """
    tags = [
        t
        for t in rs.line_tags(repo, branch.split("/", 1)[1])
        if rm.is_ancestor(repo, rm.rc_commit(repo, t, rs.PREFIX), f"origin/{branch}")
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
        return f"confirm {held_n} held backport/ga fix" + ("es" if held_n > 1 else "")
    driver = "cloud " if rs.PREFIX else ""  # OSS lines are built by the cloud workflows
    if unbuilt:
        return f"{driver}Take RC"
    if tag and "-rc." in tag:
        return f"{driver}Promote"
    return "-"


def status_row(branch, state, tag, unbuilt, missing, conflicts, held_n):
    if tag is None:
        built = "none"
    else:
        built = f"{rm.tag_link(tag)} · " + (
            f"+{unbuilt} not built" if unbuilt else "all built"
        )
    pending = ", ".join(
        ([f"{len(conflicts)} conflict"] if conflicts else [])
        + ([f"{held_n} held"] if held_n else [])
    )
    return (
        f"| {rm.branch_link(branch)} | {state} | {built} | {missing} | {pending or '-'} | "
        f"{next_step(conflicts, held_n, tag, unbuilt)} |"
    )


def this_run(rows):
    """Only what this run did: skipped and invalid rows are left out."""
    out = []
    for sha, pr, _, b, res, _ in rows:
        src = link_pr(pr) if pr.startswith("#") else rm.commit_link(sha)
        to = rm.branch_link(b)
        # finish_open adds ", retried" when it merges a pick PR an earlier run left open.
        if m := re.fullmatch(r"merged (\w+) \(#(\d+)(?:, retried)?\)", res):
            out.append(
                f"- {src} → {to}: merged as {rm.commit_link(m[1])} ({rm.pr_link(int(m[2]))})"
            )
        elif res.startswith("pr "):
            out.append(
                f"- {src} → {to}: conflict, {rm.pr_link(int(res.rsplit('/', 1)[1]))} to resolve"
            )
        elif res.startswith("failed"):
            out.append(f"- {src} → {to}: {res}")
    return out


def stale(days):
    return f"{days} day{'s' if days != 1 else ''}" + (" ⚠" if days >= STALE_DAYS else "")


def pending_block(conflicts, held_rows):
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
            f"- {rm.pr_link(c)} on {rm.branch_link(b)} · open {stale(d)}"
            for c, b, d in conflicts
        ] + [""]
    if groups:
        out += [
            "**Held for confirmation** (stabilized lines; pick with `patch_released_lines`):",
            "",
        ]
        out += [
            f"- {link_src(sha, pr)} {cls} → "
            + ", ".join(map(rm.branch_link, bs))
            + f" · merged {stale(d)} ago"
            for sha, (cls, pr, d, bs) in groups.items()
        ]
        commits = ",".join(_commit_arg(sha, pr) for sha, (_, pr, _, _) in groups.items())
        branches = ",".join(
            dict.fromkeys(rm.line(b) for _, _, _, bs in groups.values() for b in bs)
        )
        out += [
            "",
            "```",
            f"gh workflow run backport.yaml -f commits={commits} -f lines={branches} "
            "-f patch_released_lines=true",
            "```",
            "",
        ]
    return out + ["</details>"]


def _commit_arg(sha, pr):
    return pr if re.fullmatch(r"#\d+", pr) else sha[:12]


def push_summary(head, table, done, pending):
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


HELD = {"ga"}
OWED = {"rc", "ga"}
UNCLASSIFIABLE = (
    "UNCLASSIFIABLE"  # no PR found, or a PR main_fix_class rejects: shown, never dropped
)


def held_filter(commits, classes, trailers, accept=HELD):
    """Pure core of held(); trailers may be abbreviated."""
    return [
        (s, *classes[s])
        for s in commits
        if classes[s][0] in accept | {UNCLASSIFIABLE}
        and not any(s.startswith(t) for t in trailers)
    ]


def classes_from_listing(prs):
    out = {}
    for pr in prs:
        if not pr.get("mergeCommit"):
            continue
        out[pr["mergeCommit"]["oid"]] = pr_class(pr)
    return out


def pr_classes(slug, since):
    """Labels are read now, so a label edited after the merge counts.
    A failed listing returns {}: held() then looks each commit up on its own.
    """
    # Known limit: search stops at 1000 results; the rest are looked up per commit.
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
    except RuntimeError as e:  # safe: held() looks each commit up on its own
        print(f"::warning::PR listing failed, classing commit by commit: {e}")
        return {}
    return classes_from_listing(json.loads(out))


def held(slug, repo, branch, accept=HELD, cache=None, token=None):
    """Main commits since branch's cut whose class is in accept (or UNCLASSIFIABLE), neither picked nor declined.
    cache is shared across calls, so a commit is looked up on its own at most once per run.
    """
    remote = f"origin/{branch}"
    base = rm.git(repo, "merge-base", MAIN, remote)
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
        subject = lambda s=s: rm.git(repo, "log", "-1", "--format=%s", s)
        try:
            cls, pr, title = fix_class(slug, s, token=token)
            classes[s] = (
                (UNCLASSIFIABLE, pr, subject()) if pr == "no PR" else (cls, pr, title)
            )
        except ValueError as e:  # no usable PR data
            classes[s] = (UNCLASSIFIABLE, str(e), subject())
    print(
        f"held: {len(commits)} main commit(s) since the cut of {branch}, {looked} fix_class lookup(s)"
    )
    return held_filter(commits, classes, _trailers(repo, base, remote), accept)


def _trailers(repo, base, remote):
    """Main commits the line's pick trailers name. A decline carries the same trailer as a pick, so one grep covers both."""
    return {
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


REVERTS_ANY_RE = re.compile(r"^(?:\* )?This reverts commit ([0-9a-f]{7,40})", re.M)
PR_SUFFIX_RE = re.compile(r" \(#\d+\)$")


def declared(slug, repo, branch, token=None):
    """[(number, title)] of merged main PRs whose body declares `Backport-also: X.Y` for this line and whose merge
    commit, first-parent on main since the cut, is neither picked nor declined there, nor reverted on main.
    A failed listing raises: it never reads as nothing declared.
    """
    line = branch.removeprefix("release/")
    remote = f"origin/{branch}"
    base = rm.git(repo, "merge-base", MAIN, remote)
    since = search_since(repo, base)
    # Known limit: search stops at 1000 results; a PR past it is missed (no block), never wrongly blocked.
    prs = json.loads(
        gh(
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
            "number,title,body,mergeCommit",
            token=token,
        )
    )
    mine = [
        p for p in prs if p.get("mergeCommit") and line in rm.declared_lines(p["body"])
    ]
    if not mine:
        return []
    order = [
        c.split("\x1f")
        for c in rm.git(
            repo,
            "log",
            "--first-parent",
            "--reverse",
            "--format=%H%x1f%s%x1f%B%x1e",
            f"{base}..{MAIN}",
        ).split("\x1e")
        if c.strip()
    ]
    order = [(h.strip(), subj, body) for h, subj, body in order]
    at = {h: i for i, (h, _, _) in enumerate(order)}
    done = _trailers(repo, base, remote)
    for p in mine:
        c = p["mergeCommit"]["oid"]
        if (
            c not in at
            and rm.git(
                repo, "merge-base", "--is-ancestor", c, base, check=False
            ).returncode
        ):
            # Merged after the fetch (or not yet fetched): fail closed rather than skip it.
            raise RuntimeError(
                f"#{p['number']}'s merge commit {c[:9]} is not in the fetched main; retry"
            )
    return [
        (p["number"], p["title"])
        for p in mine
        if (c := p["mergeCommit"]["oid"]) in at
        and not any(c.startswith(t) for t in done)
        and not _undone(order, at[c], p["title"])
    ]


def _undone(order, i, title):
    """Whether main's first-parent commit i is reverted by a later one that is not itself reverted, so a revert
    of the revert keeps the fix. A revert names the commit (a squash lists it under "* "); only one that names
    none is matched by GitHub's revert PR title, since two PRs can share a title.
    """
    sha = order[i][0]
    for j in range(i + 1, len(order)):
        _, subj, body = order[j]
        named = REVERTS_ANY_RE.findall(body)
        m = rm.REVERT_RE.match(subj)
        hit = (
            any(sha.startswith(t) for t in named)
            if named
            else m and m[1].strip() == title.strip()
        )
        if hit and not _undone(order, j, PR_SUFFIX_RE.sub("", subj)):
            return True
    return False


def search_since(repo, base):
    """The date to pass GitHub's `merged:>=` for PRs merged after base: a day early, since GitHub reads the date
    as UTC and main's commits carry +0530. Callers keep only commits after base, so the margin costs nothing.
    """
    at = datetime.datetime.fromisoformat(rm.git(repo, "log", "-1", "--format=%cI", base))
    return (at - datetime.timedelta(days=1)).date().isoformat()


def backport_head(branch, sha):
    return f"backport/{branch.split('/', 1)[1]}/{sha[:7]}"


def backport_heads():
    """Pick heads on origin: an open pick or conflict PR, or another run's pick in flight."""
    out = rm.git(REPO, "ls-remote", "--heads", "origin", "refs/heads/backport/*")
    return {row.split("\t")[1].removeprefix("refs/heads/") for row in out.splitlines()}


def unsettled(targets, held_by_branch, rows, heads):
    """Owed commits a run leaves in no known state.

    held() already leaves out picked, declined and proven non-fixes; what remains must be held for confirmation, on a pick
    head, or answered by a row of this run (a failed row fails the run on its own).
    """
    stabilized = {t["branch"] for t in targets["ga"] if t["needs_rm_confirmation"]}
    answered = {(r[0], r[3]) for r in rows}
    return [
        (sha, pr, b, cls)
        for b, owed in held_by_branch.items()
        for sha, cls, pr, _ in owed
        if (sha, b) not in answered
        and not (b in stabilized and cls in HELD)
        and backport_head(b, sha) not in heads
    ]


def unsettled_lines(left, ran):
    """ran: the commits this run has rows for; any other was already owed when it started."""
    out = []
    for sha, pr, b, cls in left:
        do = (
            "fix its PR title or labels and rerun Backport, or record a decline"
            if cls == UNCLASSIFIABLE
            else f"dispatch Backport with commits={sha[:12]} lines={rm.line(b)}, or record a decline"
        )
        why = (
            "was left undone"
            if sha in ran
            else "was owed before this run, not caused by it"
        )
        print(f"::error::{sha[:7]} ({cls}, PR {pr}) is owed on {b} and {why}: {do}")
        before = "" if sha in ran else "owed before this run, not caused by it; "
        out.append(f"- {link_src(sha, pr)} ({cls}) → {rm.branch_link(b)}: {before}{do}")
    return out


def owed_now(slug, targets):
    """held() for every target line after a dispatch, on fresh line tips."""
    scan, _ = rescan_targets(targets, [])
    for b in scan:
        fetch_branch(b)
    cache = _rescan_classes(slug, scan)
    return {b: held(slug, REPO, b, accept=a, cache=cache) for b, a in scan.items()}


def overdue(sha, now):
    """Merged past OWED_GRACE: younger, its own push's rescan may still be picking it."""
    return now - rm.ts(rm.git(REPO, "log", "-1", "--format=%cI", sha)) > OWED_GRACE


def state_check(state, others=(), slug=None, now=None):
    """Daily State run: 1 when a pick is overdue, a commit cannot be classed, or a conflict PR is stale."""
    slug = slug or os.environ["GITHUB_REPOSITORY"]
    now = now or datetime.datetime.now(datetime.UTC)
    lines = {
        r["branch"]: OWED if r["state"] == "stabilizing" else HELD
        for r in state["branches"]
        if r["state"] in ("stabilizing", "stabilized")
    }
    errors = []
    prs = [
        (repo, p) for repo in dict.fromkeys([slug, *others]) for p in conflict_prs(repo)
    ]
    for repo, p in prs:
        if now - rm.ts(p["createdAt"]) > CONFLICT_GRACE:
            errors.append(
                f"{repo}#{p['number']} on {p['baseRefName']}: backport conflict PR open since {p['createdAt']}; "
                "resolve and merge it, or close it to decline"
            )
    in_pr = {p["headRefName"] for repo, p in prs if repo == slug}
    cache = _rescan_classes(slug, lines)
    for b, accept in lines.items():
        for sha, cls, pr, title in held(slug, REPO, b, accept=accept, cache=cache):
            if cls == UNCLASSIFIABLE:
                errors.append(
                    f"{sha[:7]} ({pr}, {title}) cannot be classed for {b}: fix its PR title or labels, or record a decline"
                )
            elif accept is HELD:  # listed, not failed: it waits for a confirm
                print(held_line(sha, cls, pr, b, "notice"))
            elif backport_head(b, sha) in in_pr:
                continue  # the conflict PR's own age decides
            elif overdue(sha, now):
                errors.append(
                    f"{sha[:7]} ({cls}, PR {pr}) owed on stabilizing {b} and not picked: "
                    f"dispatch Backport with commits={sha[:12]}, or record a decline"
                )
    for e in errors:
        print(f"::error::{e}")
    return 1 if errors else 0


def owed_summary(rows, branch):
    """Information only: a stabilized line takes an rc fix only when a Backport dispatch names the line."""
    out = [
        f"**Owed picks** for {rm.branch_link(branch)}: main fixes since the cut, neither picked nor declined",
        "",
    ]
    if not rows:
        return "\n".join(out + ["none"])
    out += ["| commit | PR | title | class |", "|---|---|---|---|"]
    cell = lambda t: t.replace("|", r"\|")  # a pipe in a title would split the row
    out += [
        f"| {link_sha(s)} | {link_pr(pr)} | {cell(title)} | {cls} |"
        for s, cls, pr, title in rows
    ]
    return "\n".join(
        out
        + [
            "",
            f"To pick a fix: dispatch Backport with its commit, `patch_released_lines=true` and `lines={rm.line(branch)}`"
            " plus every newer released line. Backport skips an unclassifiable row.",
        ]
    )


def warn_held(slug, repo, branch, annotate="warning", token=None):
    """For Take RC / Promote on a stabilized branch: Promote blocks on held fixes unless forced."""
    rows = held(slug, repo, branch, token=token)
    other = slug if token else None  # a token means another repo: name it
    for s, cls, pr, title in rows:
        print(held_line(s, cls, pr, branch, annotate, other, title))
    return held_note(rows, branch, other)


def held_note(rows, branch, slug=None):
    if not rows:
        return None
    # Backport refuses an unclassifiable commit, so it stays out of the suggested pick.
    pick = [r for r in rows if r[1] != UNCLASSIFIABLE]
    bad = [r for r in rows if r[1] == UNCLASSIFIABLE]
    note = f"⚠ Held for confirmation on {f'{slug} ' if slug else ''}{rm.branch_link(branch, slug)} (stabilized; Promote blocks unless forced): "
    if pick:
        commits = ",".join(_commit_arg(s, pr) for s, _, pr, _ in pick)
        note += (
            ", ".join(f"{link_src(s, pr, slug)} {cls}" for s, cls, pr, _ in pick)
            + f". Pick with `gh workflow run backport.yaml{f' -R {slug}' if slug else ''} -f commits={commits} "
            f"-f lines={rm.line(branch)} -f patch_released_lines=true`"
        )
    if bad:
        note += (" " if pick else "") + (
            f"{UNCLASSIFIABLE}, add a backport label or fix its PR title, or record a decline: "
            + ", ".join(f"{link_src(s, pr, slug)} {title}" for s, _, pr, title in bad)
        )
    return note


def patch_lines(state, slug=None):
    """Release state: per stabilized line, main fixes since its cut that it lacks, as Backport commits."""
    slug = slug or os.environ["GITHUB_REPOSITORY"]
    out = [
        "**Patch a released line**: main fixes since the line's cut, neither picked nor declined. Paste into Backport "
        "`commits` with `patch_released_lines` and `lines` (every newer released line too).",
        "",
    ]
    branches = [r["branch"] for r in state["branches"] if r["state"] == "stabilized"]
    if not branches:
        return "\n".join(out + ["no stabilized line"])
    # From the cut, not the GA: a fix merged before the GA is still owed when its label came later or its push run
    # failed. One listing from the oldest GA covers the newer lines; the oldest line's RC period is looked up per commit.
    gas = [
        tt["ga"]["pushed_at"]
        for r in state["branches"]
        if r["state"] == "stabilized"
        for tt in r["targets"].values()
        if tt.get("ga")
    ]
    cache = pr_classes(slug, min(gas, key=rs._ts)) if gas else {}
    for branch in branches:
        out.append(f"- {rm.branch_link(branch)}: {_owed_cell(slug, branch, cache)}")
    return "\n".join(out)


def _owed_cell(slug, branch, cache):
    """Owed main fixes on branch as Backport `commits`. A gh or git failure on one line must not fail the State run."""
    try:
        rows = held(slug, REPO, branch, accept=OWED, cache=cache)
    # Safe as a warning: State's check step repeats the lookup and fails the run.
    except RuntimeError as e:
        print(f"::warning::{branch}: patch list unavailable: {e}")
        return "patch list unavailable (see the run log)"
    commits = " ".join(
        _commit_arg(s, pr) for s, cls, pr, _ in rows if cls != UNCLASSIFIABLE
    )
    left = sum(cls == UNCLASSIFIABLE for _, cls, *_ in rows)
    return (f"`{commits}`" if commits else "none") + (
        f" ({left} unclassifiable left out)" if left else ""
    )


def missed_picks(state, others=(), slug=None):
    """Release state: per stabilizing line, main fixes Backport has not landed there and open conflict PRs on it here
    and in others, so a miss shows before QA tests the RC rather than at Promote's gate.
    """
    slug = slug or os.environ["GITHUB_REPOSITORY"]
    out = [
        "**Missed picks on stabilizing lines**: main fixes since the line's cut, neither picked nor declined, and open "
        "backport conflict PRs. Paste the commits into Backport `commits`.",
        "",
    ]
    branches = [r["branch"] for r in state["branches"] if r["state"] == "stabilizing"]
    if not branches:
        return "\n".join(out + ["no stabilizing line"])
    cut = lambda b: rm.git(
        REPO, "log", "-1", "--format=%cs", rm.git(REPO, "merge-base", MAIN, f"origin/{b}")
    )
    try:
        cache = pr_classes(slug, min(map(cut, branches)))
    except RuntimeError as e:  # held() then looks each commit up on its own
        print(f"::warning::cut date unavailable: {e}")
        cache = {}
    for branch in branches:
        try:
            prs = [
                rm.pr_link(p["number"], repo)
                for repo in dict.fromkeys([slug, *others])
                for p in conflict_prs(repo, branch)
            ]
            conflicts = ", ".join(prs) or "none"
        # Never reads as no PRs; State's check step lists them again and fails.
        except RuntimeError as e:
            print(f"::warning::{branch}: conflict PR listing failed: {e}")
            conflicts = "unavailable (see the run log)"
        out.append(
            f"- {rm.branch_link(branch)}: owed {_owed_cell(slug, branch, cache)}; conflict PRs {conflicts}"
        )
    return "\n".join(out)


def rescan_targets(targets, listed):
    """Stabilizing targets owe rc and ga fixes (OWED); stabilized ones only ga (HELD)."""
    scan = dict.fromkeys(targets["rc"], OWED)
    for t in targets["ga"]:
        scan.setdefault(t["branch"], HELD)
    kept, others = only_listed(list(scan), listed)
    return {b: scan[b] for b in kept}, others


def rescan_plan(targets, held_by_branch, confirm):
    stabilized = {t["branch"] for t in targets["ga"] if t["needs_rm_confirmation"]}
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
    """A failure never stalls the other branches."""
    try:
        rel = rm.relevance(
            REPO, sha, f"origin/{b}"
        )  # advisory only: never skips the pick
    except Exception as e:
        rel = f"unknown ({type(e).__name__}: {(str(e).splitlines() or [''])[0]})"
        rel = rel.replace("|", r"\|")
        print(f"::warning::{sha[:7]} relevance on {b}: {rel}")
    try:
        outcome, detail = pick(slug, sha, b, title, pr)
    except Exception as e:
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


def _rescan_classes(slug, scan):
    cuts = [rm.git(REPO, "merge-base", MAIN, f"origin/{b}") for b in scan]
    oldest = min(
        (rm.git(REPO, "log", "-1", "--format=%cI", c) for c in cuts), default=None
    )
    # A day's margin for clock and merge-time skew.
    since = (
        (datetime.datetime.fromisoformat(oldest) - datetime.timedelta(days=1)).date()
        if oldest
        else None
    )
    return pr_classes(slug, since.isoformat()) if since else {}


def _rescan_missing(scan, rows, held_by_branch):
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
    return missing


def rescan(slug, targets, confirm, listed):
    scan, others = rescan_targets(targets, listed)
    rows = []
    for b in others:
        print(f"::error::{b} is not a target: nothing picked there")
        rows.append(("-" * 7, "-", "-", b, "failed: not a target", "-"))
    classes = _rescan_classes(slug, scan)
    listed_n = len(classes)
    held_by_branch = {
        b: held(slug, REPO, b, accept=accept, cache=classes) for b, accept in scan.items()
    }
    print(f"rescan: {listed_n} PRs listed, {len(classes) - listed_n} fallback lookup(s)")
    plan, awaiting, unclassifiable = rescan_plan(targets, held_by_branch, confirm)
    # Fails every push until the commit is picked or declined: a skip here is never seen.
    for sha, b, pr, title in unclassifiable:
        print(f"::error::{sha[:7]} ({pr}, {title}) cannot be classed for {b}: not picked")
        rows.append((sha, pr, UNCLASSIFIABLE, b, "failed: unclassifiable", "-"))
    for b, sha, cls, pr, title in plan:
        rows.append(pick_row(slug, sha, b, cls, pr, title))
    return rows, awaiting, _rescan_missing(scan, rows, held_by_branch), held_by_branch


PUSH_WAITS = (5, 20)  # seconds before the 2nd and 3rd push attempt
PICK_TIMEOUT = 30 * 60  # = the pick job's timeout-minutes in backport.yaml


def run_url():
    e = os.environ
    return (
        f"{e['GITHUB_SERVER_URL']}/{e['GITHUB_REPOSITORY']}/actions/runs/{e['GITHUB_RUN_ID']}"
        if e.get("GITHUB_RUN_ID")
        else None
    )


def push_head(slug, sha, branch, head, src, sleep=time.sleep):
    """A final rejection comments on the source PR (Actions only); a pick another run landed meanwhile is
    skipped, not failed.
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
    fetch_branch(branch, check=False)
    # The run that won the head landed it.
    if rm.is_converged(REPO, sha, f"origin/{branch}", main=MAIN):
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


# The block pick() adds to a conflict pick's message.
CONFLICTS_RE = re.compile(r"^Conflicts:\n\t", re.M)


def fix_labels(slug, src):
    """Lint PR classes a pick PR by its backport label too."""
    if not re.fullmatch(r"#\d+", src):
        return []
    names = gh("api", f"repos/{slug}/pulls/{src[1:]}", "--jq", ".labels[].name").split(
        "\n"
    )
    return [x for x in names if x in rm.BACKPORT_LABELS]


def _closed_pr(slug, branch, head):
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
            "closed",
            "--json",
            "number,state",
        )
    )
    return next((p["number"] for p in prs if p["state"] == "CLOSED"), None)


def _no_open_pr(slug, branch, head):
    fetch_branch(head)
    age = time.time() - int(rm.git(REPO, "log", "-1", "--format=%ct", f"origin/{head}"))
    if age < PICK_TIMEOUT:
        return (
            "skipped",
            f"head {head} is {int(age // 60)} min old with no open PR: another run is picking it",
        )
    # A head with no commit past the base: reopening its PR only parks it as a conflict PR with nothing to merge.
    empty = rm.git(REPO, "rev-list", "--count", f"origin/{branch}..origin/{head}") == "0"
    # A closed PR whose head still holds a pick: its decline was not recorded, and deleting the head re-picks it.
    if not empty and (n := _closed_pr(slug, branch, head)):
        return (
            "failed",
            f"head {head} exists and its PR #{n} is closed, but no decline is recorded on {branch}: "
            f"re-run the Backport record job for #{n}, then rerun",
        )
    if empty:
        return "failed", f"head {head} exists with no open PR: delete it, then rerun"
    # No PR open or closed: a create whose failure outlasted the lookup. Deleting lets the next run pick it again.
    deleted = not soft(
        f"delete of {head}",
        "gh",
        "api",
        "-X",
        "DELETE",
        f"repos/{slug}/git/refs/heads/{head}",
    ).returncode
    return (
        "failed",
        f"head {head} had no PR: deleted it, so the next Backport run picks the fix again"
        if deleted
        else f"head {head} has no PR and its delete failed: delete it, then rerun",
    )


def finish_open(slug, branch, head):
    """Squash only an open bot PR whose single commit carries the head's pick trailer; any other PR fails or waits.
    Known limits: only the trailer is checked, not the content; age is the head tip's commit time.
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
    if not prs:  # a live run opens its PR after pushing the head
        return _no_open_pr(slug, branch, head)
    if len(prs) != 1:
        return pending
    pr, remote = prs[0], f"origin/{branch}"
    # The squash bypasses the release ruleset: only the bot's own PR may go through it.
    if why := bm.bot_refusal(pr):
        return "failed", f"{why}: not merged"
    if any(x["name"].startswith("backport-") for x in pr["labels"]):
        return pending
    fetch_branch(head)
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
    msg = rm.message(REPO, pr["headRefOid"])
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
    return _land(slug, branch, head, pr["number"], retried=True)


def _land(slug, branch, head, n, retried=False):
    """Refetch branch after the squash: later picks stack on it."""
    soft(
        f"delete of {head}",
        "gh",
        "api",
        "-X",
        "DELETE",
        f"repos/{slug}/git/refs/heads/{head}",
    )
    fetch_branch(branch)
    short = rm.git(REPO, "rev-parse", "--short=7", f"origin/{branch}")
    return "merged", f"{short} (#{n}{', retried' if retried else ''})"


def _open_pr(slug, branch, head, body, *opts, sleep=time.sleep):
    """A create GitHub failed transiently may have opened the PR: look before retrying. Still none after the retries:
    keep the head. Deleting it would close a PR the listing has not shown yet, and record() would take that close as a
    decline; the next run's _no_open_pr deletes the head once it is past PICK_TIMEOUT and has no PR.
    """
    for n in range(bm.GH_TRIES):
        try:
            return gh(
                "pr",
                "create",
                "-R",
                slug,
                "--base",
                branch,
                "--head",
                head,
                *opts,
                "--body",
                body,
                retry=False,
            )
        except RuntimeError as e:
            if not bm.transient(str(e)):
                raise
            if url := gh(
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
                "url",
                "--jq",
                ".[0].url // empty",
            ):
                return url
            if n == bm.GH_TRIES - 1:
                raise
            wait = bm.gh_wait(n, str(e))
            print(f"{str(e).splitlines()[0]}; PR create retried in {wait} s")
            sleep(wait)


def _land_clean(slug, sha, branch, title, src, head, labels):
    pick_sha = rm.git(REPO, "rev-parse", "HEAD")
    if failed := push_head(slug, sha, branch, head, src):
        return failed
    url = _open_pr(
        slug, branch, head, pr_body(sha, src, branch, head), "--title", title, *labels
    )
    n = int(url.rsplit("/", 1)[1])
    # False: a required check is pending; PR and head stay for the next run.
    if not bm.squash(
        slug, {"number": n, "headRefOid": pick_sha}, rm.message(REPO, pick_sha)
    ):
        return "failed", f"{url} opened, merge pending check"
    return _land(slug, branch, head, n)


def pick(slug, sha, branch, title, src):
    remote = f"origin/{branch}"
    # Fresh tip: an overlapping run may have merged this pick after this run fetched.
    fetch_branch(branch)
    if rm.is_converged(REPO, sha, remote, main=MAIN):
        return "skipped", "already on branch"
    head = backport_head(branch, sha)
    # Known limit: an ls-remote error reads as "no head"; the push then fails.
    ls = run("git", "ls-remote", "--exit-code", "--heads", "origin", head, check=False)
    if ls.returncode == 0:
        return finish_open(slug, branch, head)
    labels = [x for name in fix_labels(slug, src) for x in ("--label", name)]
    run("git", "checkout", "-q", "--detach", remote)
    r = run("git", "cherry-pick", "-x", sha, check=False)
    if r.returncode == 0:
        return _land_clean(slug, sha, branch, title, src, head, labels)
    # -z keeps paths with spaces or non-ASCII intact (rm.git's strip may trim a leading space; display only).
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
    with open(os.path.join(REPO, ".git", "MERGE_MSG")) as f:
        msg = "".join(line for line in f if not line.startswith("#")).strip()
    msg += "\n\nConflicts:\n" + "".join(f"\t{p}\n" for p in files)
    # -u: tracked and unmerged paths only; -A would also commit untracked files such as state.json.
    run("git", "add", "-u")
    run("git", "commit", "-q", "--no-verify", "-F", "-", input=msg)
    if failed := push_head(slug, sha, branch, head, src):
        return failed
    url = _open_pr(
        slug,
        branch,
        head,
        pr_body(sha, src, branch, head, files),
        "--label",
        "backport-conflict",
        *labels,
        "--title",
        title,
    )
    return "pr", url


def push_title(slug, sha):
    # Known limit: a gh error past fix_class's retry ends the run before the summary.
    try:
        cls, pr, title = fix_class(slug, sha)
    except ValueError as e:  # the picks are done, only this line is left
        print(f"::warning::{sha[:7]}: fix class: {e}")
        cls, pr = UNCLASSIFIABLE, "-"
    if pr == "no PR":  # as rescan classes it: shown, never "not a fix"
        cls, title = UNCLASSIFIABLE, "no PR found, so it cannot be classed"
    if cls == UNCLASSIFIABLE and pr != "-":
        print(f"::warning::{sha[:7]}: fix class: {title}")
    return f"Backport · push {rm.commit_link(sha)} ({link_pr(pr)}, {cls or 'not a fix'})"


def listed_branches(value):
    """The --lines input as release branches: "0.186, release/0.188" gives both as release/X.Y.

    Commas or spaces separate the items; each item itself must be exact.
    """
    return [f"release/{rm.line(b)}" for b in re.split(r"[,\s]+", value) if b]


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
    p.add_argument("--patch-released-lines", action="store_true")
    p.add_argument(
        "--lines",
        default="",
        help="only these release lines, X.Y or release/X.Y, by commas or spaces (default every target)",
    )
    a = p.parse_args()
    slug = os.environ["GITHUB_REPOSITORY"]
    with open(rm.local_path(a.state)) as f:
        state = json.load(f)
    targets = state["backport_targets"]
    try:
        listed = listed_branches(a.lines)
    except ValueError as e:
        sys.exit(f"::error::lines: {e}")
    if a.rescan:
        rows, awaiting, missing, owed = rescan(
            slug, targets, a.patch_released_lines, listed
        )
    else:
        rows, awaiting = dispatch(
            slug, targets, a.commits, a.patch_released_lines, listed
        )
    failed = sum(res.startswith("failed") for *_, res, _ in rows)
    # Every owed commit ends the run picked, declined, held, on a pick head, or not a fix; else the run is red.
    try:
        if not a.rescan:
            owed = owed_now(slug, targets)
        ran, now = {r[0] for r in rows}, datetime.datetime.now(datetime.UTC)
        left = unsettled(targets, owed, rows, backport_heads())
        undone = unsettled_lines(
            [u for u in left if u[0] in ran or overdue(u[0], now)], ran
        )
    except RuntimeError as e:
        print(f"::error::cannot check what this run left undone: {e}")
        undone = ["- unchecked: see the run log"]
    if awaiting:
        print("\n".join(held_warnings(awaiting)))  # a held pick is never silent

    now = datetime.datetime.now(datetime.UTC)
    days = lambda iso: (now - rm.ts(iso)).days
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
        out += [dispatch_row(*r) for r in rows]
        out += [""] + pending
    if undone:
        out += [
            "",
            "**⛔ Left undone**: owed, and not picked, declined, held or on a pick PR",
            "",
            *undone,
        ]
    print("\n".join(out))
    if os.environ.get("GITHUB_STEP_SUMMARY"):
        with open(os.environ["GITHUB_STEP_SUMMARY"], "a") as f:
            f.write("\n".join(out) + "\n")
    return 1 if failed or undone else 0


def dispatch(slug, targets, commits, confirm, listed):
    # Commas or spaces: State's patch-lines list pastes as is.
    items = [c for c in re.split(r"[,\s]+", commits) if c]
    prs = {}
    shas = [resolve(slug, c, prs) for c in items]
    if not items or None in shas:
        bad = [c for c, s in zip(items, shas, strict=False) if s is None]
        sys.exit(f"::error::refused: not merged commits on main: {bad or 'none given'}")
    shas = main_order(REPO, shas)

    rows, awaiting = [], []
    for sha in shas:
        rows += _dispatch_commit(
            slug, targets, sha, confirm, listed, awaiting, prs.get(sha)
        )
    return rows, awaiting


def _dispatch_targets(targets, sha, cls, pr, confirm, listed):
    if cls == "rc":
        # An rc fix reaches a stabilized line only when a dispatch names it: patch_released_lines and lines.
        named = [
            t["branch"]
            for t in targets["ga"]
            if t["needs_rm_confirmation"] and confirm and t["branch"] in listed
        ]
        return targets["rc"] + named, []
    branches = [
        t["branch"] for t in targets["ga"] if confirm or not t["needs_rm_confirmation"]
    ]
    return branches, [
        (sha, t["branch"], cls, pr)
        for t in targets["ga"]
        if t["needs_rm_confirmation"]
        and not confirm
        and (not listed or t["branch"] in listed)
    ]


def _dispatch_commit(slug, targets, sha, confirm, listed, awaiting, named_pr=None):
    """Appends its held picks to awaiting. named_pr: the PR the dispatch named, already fetched."""
    try:
        cls, pr, title = pr_class(named_pr) if named_pr else fix_class(slug, sha)
    except ValueError as e:
        print(f"::error::{sha[:7]}: fix class: {e}")
        # A named commit nothing could pick fails the dispatch.
        return [(sha, "?", "error", "-", f"failed: {e}", "-")]
    if cls == UNCLASSIFIABLE:
        print(f"::error::{sha[:7]}: fix class: {title}")
        return [(sha, pr, "error", "-", f"failed: {title}", "-")]
    if pr == "no PR":
        print(f"::error::{sha[:7]}: no PR found, so it cannot be classed")
        return [(sha, pr, "error", "-", "failed: no PR found", "-")]
    if cls is None:
        route = f"swap {pr}'s main-only label for a backport label and rerun"
        return [(sha, pr, "none", "-", f"skipped: not a fix; {route}", "-")]
    branches, held_picks = _dispatch_targets(targets, sha, cls, pr, confirm, listed)
    awaiting += held_picks
    rows = []
    branches, others = only_listed(branches, listed)
    others = [b for b in others if (sha, b, cls, pr) not in awaiting]
    stabilized = {t["branch"] for t in targets["ga"] if t["needs_rm_confirmation"]}
    for b in others:
        if cls == "rc" and b in stabilized:  # named, but patch_released_lines is off
            print(
                f"::error::{sha[:7]} (rc, PR {pr}): {b} is stabilized, needs patch_released_lines"
            )
            rows.append(
                (sha, pr, cls, b, "failed: stabilized; needs patch_released_lines", "-")
            )
            continue
        print(f"::error::{sha[:7]} ({cls}, PR {pr}): {b} is not a target, not picked")
        rows.append((sha, pr, cls, b, "failed: not a target", "-"))
    if cls == "rc" and confirm and not listed:
        for t in targets["ga"]:
            if t["needs_rm_confirmation"]:
                print(f"::error::{sha[:7]} (rc, PR {pr}): {t['branch']} needs lines")
                rows.append(
                    (
                        sha,
                        pr,
                        cls,
                        t["branch"],
                        "failed: stabilized; a backport/rc fix needs lines",
                        "-",
                    )
                )
    if not branches and not others and not rows:
        rows.append((sha, pr, cls, "-", "skipped: no target branch", "-"))
    rows += [pick_row(slug, sha, b, cls, pr, title) for b in branches]
    return rows


if __name__ == "__main__":
    sys.exit(main())
