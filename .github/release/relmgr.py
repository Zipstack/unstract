"""Pure-git checks for the release-branch strategy.

Every function reads a local repo only; nothing is stored, everything is derived from git.
"""

import ast
import os
import re
import subprocess

BOT_EMAIL = "releases@unstract.com"
PICK_RE = re.compile(r"\(cherry picked from commit ([0-9a-f]{7,40})\)")
# Anywhere in the message, at a line start; `* ` too, because a squash with COMMIT_MESSAGES lists each commit's
# subject as `* <subject>` and the bot's Release-branch-only commit is subject-only.
RBO_RE = re.compile(r"^(?:\* )?Release-branch-only: (\S+)", re.M)
# `UN-1 [FIX] x` or `[FIX] x`: the ticket is optional. Known limit: one ticket only, so `UN-1 UN-2 [FIX] x` fails
# Lint PR and is unclassifiable for Backport.
PR_TITLE_RE = re.compile(
    r"^(?:(?P<ticket>[A-Z][A-Z0-9]*-\d+) )?\[(?P<type>FIX|HOT-FIX|FEAT|GATED-FEAT|DOCS|DEPS|MISC|DEV|WIP)\] \S"
)
FIX_CLASSES = ("fix", "security", "critical")
REVERT_RE = re.compile(
    r'^Revert "(.+)"'
)  # GitHub's revert button; greedy, so a revert of a revert nests
REVERTS_RE = re.compile(
    r"^This reverts commit ([0-9a-f]{7,40})", re.M
)  # git revert's body line
DECLINED_RE = re.compile(
    r"^Declined: (.+)$", re.M
)  # the reason line Backport PR writes on a decline commit
BACKPORT_HEAD_RE = re.compile(
    r"backport/(\d+\.\d+)/([0-9a-f]{7})"
)  # the head Backport PR opens: line, sha7; fullmatch


def _web():
    """https://github.com/<owner>/<repo> inside Actions; None outside it (the links below are then plain text)."""
    server, slug = (
        os.environ.get("GITHUB_SERVER_URL"),
        os.environ.get("GITHUB_REPOSITORY"),
    )
    return f"{server}/{slug}" if server and slug else None


def pr_link(n):
    return f"[#{n}]({_web()}/pull/{n})" if _web() else f"#{n}"


def commit_link(sha, n=7):
    return f"[`{sha[:n]}`]({_web()}/commit/{sha})" if _web() else f"`{sha[:n]}`"


def tag_link(tag):
    # The release page: it shows the tag message (an RC's Slack thread) and later the published notes.
    return f"[`{tag}`]({_web()}/releases/tag/{tag})" if _web() else f"`{tag}`"


def run_link(run_id):
    return f"[run]({_web()}/actions/runs/{run_id})" if _web() else f"run {run_id}"


def image_link(target, tag):
    """The Artifact Registry console page of target's repository (RELSTATE_AR_<TARGET>), the tag in the text;
    plain text when that variable is unset.
    """
    text = f"`{target}:{tag}`"
    repo = os.environ.get("RELSTATE_AR_" + target.upper().replace("-", "_"), "")
    m = re.fullmatch(r"projects/([^/]+)/locations/([^/]+)/repositories/([^/]+)", repo)
    return (
        f"[{text}](https://console.cloud.google.com/artifacts/docker/{m[1]}/{m[2]}/{m[3]})"
        if m
        else text
    )


_FULL = (
    set()
)  # repos confirmed non-shallow; a failed check is retried, never cached as a pass


def _require_full_history(repo):
    if repo in _FULL:
        return
    r = subprocess.run(
        ["git", "-C", repo, "rev-parse", "--is-shallow-repository"],
        capture_output=True,
        text=True,
    )
    if (
        r.stdout.strip() == "true"
    ):  # truncated history reads as "not an ancestor" and allocates taken names
        raise RuntimeError(
            f"{repo} is a shallow clone: relmgr needs full history and tags (fetch-depth: 0)"
        )
    if r.returncode == 0 and r.stdout.strip() == "false":
        _FULL.add(repo)


def git(repo, *args, check=True):
    _require_full_history(repo)
    r = subprocess.run(["git", "-C", repo, *args], capture_output=True, text=True)
    if check and r.returncode:
        raise RuntimeError(
            f"git {' '.join(args)} (exit {r.returncode}): {r.stderr.strip()}"
        )
    return r.stdout.strip() if check else r


def is_ancestor(repo, a, b):
    r = git(repo, "merge-base", "--is-ancestor", a, b, check=False)
    if r.returncode not in (0, 1):  # 1 = "no"; anything else is an error, never a "no"
        raise RuntimeError(f"git merge-base --is-ancestor {a} {b}: {r.stderr.strip()}")
    return r.returncode == 0


def on_main(repo, sha, main="main"):
    """Does `sha` (full or unambiguous prefix) name a commit on `main`?"""
    r = git(repo, "rev-parse", "-q", "--verify", f"{sha}^{{commit}}", check=False)
    return r.returncode == 0 and is_ancestor(repo, r.stdout.strip(), main)


def _is_empty(repo, sha):
    return git(repo, "rev-parse", f"{sha}^{{tree}}") == git(
        repo, "rev-parse", f"{sha}^^{{tree}}"
    )


def picked_from(repo, sha):
    """Main originals named by the commit's `-x` trailers."""
    return PICK_RE.findall(git(repo, "log", "-1", "--format=%B", sha))


def branch_range(repo, branch, main):
    """Commits in merge-base(main, branch)..branch: the convergence scan range."""
    base = git(repo, "merge-base", main, branch)
    out = git(repo, "rev-list", "--reverse", f"{base}..{branch}")
    return out.split() if out else []


def range_messages(repo, branch, main):
    """All commit messages in merge-base(main, branch)..branch, as one string (one git call)."""
    return git(
        repo, "log", "--format=%B", f"{git(repo, 'merge-base', main, branch)}..{branch}"
    )


# 1. Commit kinds / release-branch CI gate ---------------------------------------------------------------


def reverted_pick(repo, sha, main="main"):
    """The full sha of the pick that `sha` reverts on its own branch (after the cut), else None."""
    m = REVERTS_RE.search(git(repo, "log", "-1", "--format=%B", sha))
    if not m or git(repo, "cat-file", "-e", f"{m[1]}^{{commit}}", check=False).returncode:
        return None
    t = git(repo, "rev-parse", f"{m[1]}^{{commit}}")
    on_branch = is_ancestor(repo, t, sha) and not is_ancestor(repo, t, main)
    return (
        t if on_branch and classify_commit(repo, t, main=main) == "cherry-pick" else None
    )


def classify_commit(repo, sha, bot_email=BOT_EMAIL, main="main"):
    body = git(repo, "log", "-1", "--format=%B", sha)
    if PICK_RE.search(body):
        if not all(on_main(repo, o, main) for o in PICK_RE.findall(body)):
            return (
                "invalid"  # trailer names nothing on main: not a pick of a main original
            )
        return "declined" if _is_empty(repo, sha) else "cherry-pick"
    if reverted_pick(
        repo, sha, main
    ):  # backing a pick out of one branch declines it there
        return "declined"
    if RBO_RE.search(
        body
    ):  # before the author check: a bot-made pin bump is still owed a report
        return "release-branch-only"
    # Trust assumption: the author email is client-set; the review every release-branch PR gets is the backstop.
    if git(repo, "log", "-1", "--format=%ae", sha).lower() == bot_email.lower():
        return "build-generated"
    return "invalid"


def pr_commits(repo, base, head_ref, head="HEAD"):
    """The commits the PR check classifies on a PR from head_ref into base. A backport/* PR lands as its squash, whose
    message keeps the first commit's pick trailer: only that commit is judged, so a plain resolution commit after it
    passes. This relies on release/* allowing squash merges only (a ruleset, set before Backport runs); a rebase
    merge would land the unjudged commits as they are. Any other PR: every commit in base..head.
    """
    out = git(repo, "rev-list", "--reverse", f"{base}..{head}")
    commits = out.split() if out else []
    return commits[:1] if is_backport(head_ref) else commits


def is_backport(head_ref):
    """Is head_ref a branch Backport PR names (backport/X.Y/<sha7>)? Any other name is judged commit by commit."""
    return bool(BACKPORT_HEAD_RE.fullmatch(head_ref))


def pick_trailer(head_ref, msg):
    """The one pick trailer of msg when it names head_ref's sha7 (backport/X.Y/<sha7>), else None."""
    found = PICK_RE.findall(msg)
    m = BACKPORT_HEAD_RE.fullmatch(head_ref)
    return found[0] if m and len(found) == 1 and found[0].startswith(m[2]) else None


def conflict_markers(repo, rev="HEAD"):
    """Files in rev's tree with a `<<<<<<<` or `>>>>>>>` conflict-marker line."""
    r = git(repo, "grep", "-l", "-E", "^(<<<<<<<|>>>>>>>)( |$)", rev, "--", check=False)
    if r.returncode not in (0, 1):  # 1 = no match
        raise RuntimeError(f"git grep (exit {r.returncode}): {r.stderr.strip()}")
    return [m.split(":", 1)[1] for m in r.stdout.splitlines()]


def ci_commits(
    repo, branch, event, before="", head_ref="", labelled=False, main="origin/main"
):
    """Release branch CI over one event: ([(sha, kind)], where). ValueError: conflict markers in a backport PR's tree.

    pull_request: the PR's own commits (a backport PR's first only, invalid unless it carries exactly one pick
    trailer, naming the head's sha7); labelled turns its invalid commits into
    release-branch-only, since the squash at merge writes the line. push: the pushed commits before..HEAD, or the
    whole branch when before is all zeros (branch creation) or gone (a force push).
    """
    if event == "pull_request":
        if is_backport(head_ref) and (marked := conflict_markers(repo)):
            raise ValueError(
                f"conflict markers in {', '.join(marked)}: resolve before merging"
            )
        commits, where = pr_commits(repo, branch, head_ref), f"PR into {branch}"
    elif (
        set(before) - {"0"}
        and git(repo, "cat-file", "-e", f"{before}^{{commit}}", check=False).returncode
        == 0
    ):
        # Only the pushed commits. Classifying the whole branch would keep every later push red
        # after one invalid commit landed, so a revert could never clear it. The PR check covers PR commits.
        out = git(repo, "rev-list", "--reverse", f"{before}..HEAD")
        commits, where = out.split() if out else [], f"push to {branch}"
    else:
        commits, where = branch_range(repo, branch, main), branch
    labelled = labelled and event == "pull_request"
    rows = []
    for c in commits:
        kind = classify_commit(repo, c, main=main)
        # The squash keeps every trailer of a backport PR's first commit: one naming the head's fix, or it records others.
        if (
            event == "pull_request"
            and is_backport(head_ref)
            and not pick_trailer(head_ref, git(repo, "log", "-1", "--format=%B", c))
        ):
            kind = "invalid"
        # Known limit: the label passes every invalid commit; it does not check that a Release-branch-only line will
        # be in the squash (a fork PR, or a merge before the bot pushes that commit).
        rows.append(
            (c, "release-branch-only (label)" if labelled and kind == "invalid" else kind)
        )
    return rows, where


def check_branch(repo, branch, main="main"):
    """Release-branch CI gate: the invalid commits on the branch. Empty list == pass."""
    return [
        c
        for c in branch_range(repo, branch, main)
        if classify_commit(repo, c, main=main) == "invalid"
    ]


# 2. PR class (Lint PR) ------------------------------------------------------

FIX_LABELS = ("fix/security", "fix/critical", "fix/needs-backport")


def pr_fix_class(title, labels=()):
    """'fix' | 'security' | 'critical' for fix PRs, None for non-fix PRs; ValueError = CI rejects."""
    # Anything that looks like a class label (fix/<x>, the old fix-class/<x>, near-typos) but is
    # not one of FIX_LABELS: a typo must not silently drop or downgrade the class.
    bad = [
        l
        for l in labels
        if l not in FIX_LABELS
        and re.match(r"\s*fix(\w{0,3}[\W_]*class(?![a-z])|\s*/)", l, re.I)
    ]
    if bad:
        raise ValueError(f"unknown fix label(s) {bad}; allowed: {', '.join(FIX_LABELS)}")
    classes = {
        l.split("/", 1)[1] for l in labels if l in ("fix/security", "fix/critical")
    }
    if len(classes) > 1:
        raise ValueError(f"conflicting fix labels: {sorted('fix/' + c for c in classes)}")
    # A revert takes the reverted PR's class: it must follow the original onto every branch that carries it.
    # Stripped: GitHub keeps a title's leading space, and a typo'd space must not leave a merged fix unclassifiable.
    inner = title.strip()
    while r := REVERT_RE.match(inner):
        inner = r.group(1).strip()
    m = PR_TITLE_RE.match(inner)
    if not m and not set(labels) & set(FIX_LABELS):
        raise ValueError(
            f"no recognised '[TYPE]' or 'TICKET [TYPE]' prefix and no fix/ label: {title!r}"
        )
    if classes:
        return classes.pop()
    # fix/needs-backport: a non-[FIX] PR (e.g. [MISC]) that stabilizing lines need; no-op on a [FIX] title.
    return (
        "fix"
        if (m and m["type"] in ("FIX", "HOT-FIX")) or "fix/needs-backport" in labels
        else None
    )


def release_only_refusal(base, labels):
    """Why Lint PR refuses the release-branch-only label on a PR into `base`, or None. The label is for PRs into
    a release/X.Y branch; a main change reaches release branches through Backport.
    """
    if "release-branch-only" in labels and not base.startswith("release/"):
        return (
            "label `release-branch-only` is for PRs into a release/X.Y branch; remove it here "
            "(a main change reaches release branches through Backport)"
        )
    return None


def rbo_key(title, pr):
    """The `Release-branch-only:` value for PR `pr`: the title's ticket, else `#<pr>`. A `#<pr>` key matches no
    other line's, so the convergence report always lists that change on the newer line for a human to check.
    """
    m = PR_TITLE_RE.match(title.strip())
    return m["ticket"] if m and m["ticket"] else f"#{pr}"


# 3. Version allocation (at build time; a version names one commit) ------------------------------------------------


def _line(branch):
    m = re.fullmatch(
        r"(?:refs/heads/|(?:refs/remotes/)?[^/]+/)?release/(\d+)\.(\d+)", branch
    )
    if not m:
        raise ValueError(f"not a release branch: {branch}")
    return m.group(1), m.group(2)


def _tags(repo, x, y, prefix=""):
    """({stable Z}, {Z: [RC N]}) of line x.y. prefix: the repo's tag prefix (`ee-` on OSS lines); tags without it are
    another series and never counted.
    """
    stable, rc = set(), {}
    for t in git(repo, "tag", "-l", f"{prefix}v{x}.{y}.*").split():
        m = re.fullmatch(rf"{re.escape(prefix)}v{x}\.{y}\.(\d+)(?:-rc\.(\d+))?", t)
        if m and m.group(2):
            rc.setdefault(int(m.group(1)), []).append(int(m.group(2)))
        elif m:
            stable.add(int(m.group(1)))
    return stable, rc


def next_patch(repo, branch, prefix=""):
    """The X.Y.Z RC builds are cut for: one past the highest stable Z (0 before GA)."""
    x, y = _line(branch)
    stable, _ = _tags(repo, x, y, prefix)
    return f"{x}.{y}.{max(stable) + 1 if stable else 0}"


def rc_version(repo, branch, prefix="", taken=()):
    """Tag for a build of the branch tip, allocated from tags at build time.

    If the tip already carries an RC tag of this line, that tag is returned: a commit gets one RC tag.
    taken: tag names already used elsewhere (every target's registry tags). An RC there is never allocated again:
    an artifact pushed by a run whose tag push failed would otherwise block the line. The one exception is a tip
    that is already the bot's bump for it (already_bumped): that run is resumed.
    Needs the full tag set locally (fetch tags in CI): with no tags every line reads as freshly cut.
    """
    x, y = _line(branch)
    for t in git(repo, "tag", "--points-at", branch).split():
        if re.fullmatch(rf"{re.escape(prefix)}v{x}\.{y}\.\d+-rc\.\d+", t):
            return t
    ver = next_patch(repo, branch, prefix)
    _, rc = _tags(repo, x, y, prefix)
    tagged = max(rc.get(int(ver.rsplit(".", 1)[1]), [0]))
    pushed = [
        int(m[1])
        for t in taken
        if (m := re.fullmatch(rf"{re.escape(prefix)}v{re.escape(ver)}-rc\.(\d+)", t))
    ]
    top = max([tagged, *pushed])
    for n in range(tagged + 1, top + 1):
        if already_bumped(repo, branch, f"{prefix}v{ver}-rc.{n}"):
            return f"{prefix}v{ver}-rc.{n}"
    return f"{prefix}v{ver}-rc.{top + 1}"


CHART = "charts/unstract-platform/Chart.yaml"


def already_bumped(repo, branch, tag):
    """True when the branch tip is the bot's bump for tag: build-generated with subject `release: chart <version>`
    and the chart at the version, or, in a repo with no chart, subject `release: <version>` (an empty commit).
    That tip is left behind when the bump was pushed but the run stopped before the tag push (a failed build);
    Take RC build then tags it instead of committing another bump.
    """
    ver = tag.removeprefix("v")
    chart = git(repo, "show", f"{branch}:{CHART}", check=False)
    if chart.returncode == 0 and not re.search(
        rf"^version: {re.escape(ver)}$", chart.stdout, re.M
    ):
        return False
    email, subject = git(repo, "log", "-1", "--format=%ae%n%s", branch).split("\n", 1)
    want = f"release: chart {ver}" if chart.returncode == 0 else f"release: {ver}"
    return email.lower() == BOT_EMAIL.lower() and subject == want


def promote_version(repo, rc_tag):
    """Stable tag for promoting rc_tag: the commit's existing stable tag, else one past the highest.

    Stable Z follows commit order, so an upgrade never loses a fix. The Z can differ from the
    RC's (a target that passes a later RC takes the next patch, so a version names one commit; the
    RC->stable mapping goes in the release body), which departs from the spec's
    x.y.(z+1)-rc.N -> vx.y.(z+1) when a promote lands while a later patch is in RC. An RC older than a
    commit that already has a stable tag is refused as a downgrade. Both are harness choices, open
    with the spec owner.
    """
    m = re.fullmatch(
        r"((?:[a-z]+-)?)v(\d+)\.(\d+)\.(\d+)-rc\.\d+", rc_tag
    )  # the stable tag keeps the RC's prefix
    if not m:
        raise ValueError(f"not an RC tag: {rc_tag}")
    p, x, y = m.group(1), m.group(2), m.group(3)
    commit = git(repo, "rev-parse", f"{rc_tag}^{{commit}}")
    stable, _ = _tags(repo, x, y, p)
    for z in sorted(stable):
        shipped = git(repo, "rev-parse", f"refs/tags/{p}v{x}.{y}.{z}^{{commit}}")
        if shipped == commit:
            return f"{p}v{x}.{y}.{z}"
        if is_ancestor(repo, commit, shipped):
            raise ValueError(
                f"{rc_tag} is older than {p}v{x}.{y}.{z}: promoting it would be a downgrade"
            )
    return f"{p}v{x}.{y}.{max(stable) + 1 if stable else 0}"


# 4. Convergence --------------------------------------------------------------------


def is_converged(repo, c_main, branch, main="main"):
    """Inherited (ancestor) or picked/declined after the cut (trailer in merge-base..branch).
    Known limit: no test covers the inherited path (a commit from before the cut) on its own.
    """
    full = git(repo, "rev-parse", f"{c_main}^{{commit}}")
    if is_ancestor(repo, full, branch):
        return True
    return any(
        o.startswith(full) or full.startswith(o)
        for o in PICK_RE.findall(range_messages(repo, branch, main))
    )


def trailer_states(repo, branch, main="main"):
    """{original: "cherry-pick" | "declined"} from merge-base(main, branch)..branch, the newest commit per original
    winning: a pick after a decline ships the fix again (a decline undone by merging the reopened PR), a revert of
    a pick declines it. Declines are empty pick-trailer commits and reverts of picks.
    """
    state = {}
    for c in branch_range(repo, branch, main):
        kind = classify_commit(repo, c, main=main)
        if kind in ("cherry-pick", "declined"):
            for o in picked_from(repo, reverted_pick(repo, c, main) or c):
                state[o] = kind
    return state


def declined_originals(repo, branch, main="main"):
    """Originals whose newest pick-trailer commit after the cut is a decline (see trailer_states)."""
    return {
        o for o, kind in trailer_states(repo, branch, main).items() if kind == "declined"
    }


def decline_records(repo, branch, main="main"):
    """{original: (decline sha, reason)} for the originals declined_originals returns, from the same walk. Reason: the
    last `Declined: ...` line of an empty decline commit (its subject if it has none), or a revert's subject.
    """
    rec = {}
    for c in branch_range(repo, branch, main):
        kind = classify_commit(repo, c, main=main)
        if kind in ("cherry-pick", "declined"):
            rp = reverted_pick(repo, c, main)
            body = git(repo, "log", "-1", "--format=%B", c)
            reasons = DECLINED_RE.findall(body)
            reason = reasons[-1].strip() if reasons and not rp else body.splitlines()[0]
            for o in picked_from(repo, rp or c):
                rec[o] = (c, reason) if kind == "declined" else None
    return {o: r for o, r in rec.items() if r}


def shipped_prs(repo, tags, main="main", lookup=None, line=None):
    """PR numbers whose main original was cherry-picked (declines excluded) into any of `tags`: the changelog drops them.

    Newest trailer wins per tag (see trailer_states): a pick that a later decline or revert on that line backed out is
    not shipped, and a pick after a decline is. The PR number is the `(#n)` at the end of the original's subject
    (every squash on main has it); `lookup(sha) -> int | None` is the fallback for an original without one.

    line: the ref being published (Publish passes its RC tag). Its picks of a shipped original are dropped too, by the
    PR that landed them: `lookup(pick)` (a clean pick keeps the original's subject, so its `(#n)` is the main PR) and
    the pick's own `(#n)` (a conflict pick lands as the PR's squash). A pick with neither is skipped, not an error.
    """
    originals = {
        o
        for t in tags
        for o, kind in trailer_states(repo, t, main).items()
        if kind == "cherry-pick"
    }
    prs = set()
    for o in originals:
        m = re.search(r"\(#(\d+)\)$", git(repo, "log", "-1", "--format=%s", o))
        n = int(m[1]) if m else lookup(o) if lookup else None
        if n is None:
            raise RuntimeError(
                f"no PR number for {o[:12]} (picked into {', '.join(tags)})"
            )
        prs.add(n)
    for c in branch_range(repo, line, main) if line else []:
        if classify_commit(repo, c, main=main) == "cherry-pick" and any(
            o.startswith(d) or d.startswith(o)
            for o in originals
            for d in picked_from(repo, c)
        ):  # may be abbreviated
            m = re.search(r"\(#(\d+)\)$", git(repo, "log", "-1", "--format=%s", c))
            prs |= {
                n
                for n in (int(m[1]) if m else None, lookup(c) if lookup else None)
                if n is not None
            }
    return prs


def convergence_report(repo, older, newer, main="main", newer_branch=None):
    """[(sha_on_older, status)] with status CONVERGED | MISSING | UNCLASSIFIABLE | RBO-ABSENT. Blocks iff any MISSING.

    RBO-ABSENT is report-only: a Release-branch-only key (the ticket, or `#<PR>`) on `older` with no
    Release-branch-only commit for that key on `newer`. Case 5 (config/migration) owes nothing;
    a security fix for code gone from main may need its own equivalent on `newer` if the vulnerable code is still
    there, so a human looks.

    Both scan directions are this one call: promoting `newer` scans each older branch into it,
    promoting `older` scans it into each newer branch; either way it is older's picks vs newer.
    Pass `newer` as a branch while it is in RC. Once it is GA, pass its latest stable tag (for
    the promoting target) as `newer`, since "shipped in its latest patch" is not the branch tip, and
    the branch as `newer_branch`: a branch need only carry a decline, not ship it.

    A pick whose original cannot be placed on `main` fails release-branch CI and is MISSING here: it is never
    report-only, and never CONVERGED (a branch-first fix has no main original to converge on).
    """
    out = []
    # Newest trailer wins on both sides: a decline on newer that a later pick undid is not a decline, and a pick on
    # older that a later decline or revert backed out is not owed.
    declined = declined_originals(repo, newer_branch or newer, main)
    newer_picks = {
        o
        for o, kind in trailer_states(repo, newer, main).items()
        if kind == "cherry-pick"
    }
    older_declined = declined_originals(repo, older, main)
    newer_rbo = set(RBO_RE.findall(range_messages(repo, newer, main)))
    same = lambda o, names: any(
        o.startswith(d) or d.startswith(o) for d in names
    )  # trailers may be abbreviated
    for c in branch_range(repo, older, main):
        kind = classify_commit(repo, c, main=main)
        if kind == "invalid":
            out.append((c, "MISSING" if picked_from(repo, c) else "UNCLASSIFIABLE"))
        elif kind == "cherry-pick":
            if all(
                same(o, older_declined) for o in picked_from(repo, c)
            ):  # backed out of `older`: newer owes nothing
                continue
            ok = all(
                is_ancestor(repo, git(repo, "rev-parse", f"{o}^{{commit}}"), newer)
                or same(o, newer_picks)
                or same(o, declined)
                for o in picked_from(repo, c)
            )
            out.append((c, "CONVERGED" if ok else "MISSING"))
        elif kind == "release-branch-only":
            body = git(repo, "log", "-1", "--format=%B", c)
            if not set(RBO_RE.findall(body)) & newer_rbo:
                out.append((c, "RBO-ABSENT"))
        # build-generated: excluded from convergence.
        # declined on `older`: older does not carry the fix, so newer owes nothing.
    return out


# 5. Relevance (advisory: does the branch still have the code a fix touches?) ------------------


def relevance(repo, fix_sha, branch):
    """Are the exact line versions a main fix edits on `branch`? relevant | not-relevant | partial | unknown.

    Blames the pre-image lines the fix modifies/deletes in fix^; each last-modifying commit counts
    if it is an ancestor of `branch` or was picked onto it. 'not-relevant' means those line versions
    are absent, not that the code is: a line rewritten on main after the cut still exists on the
    branch in its older form (adapt the pick by hand, never refactor). Advisory only.
    Pure additions have no pre-image: 'unknown' (fallback, not implemented: treat as relevant iff
    the touched files exist on the branch).
    """
    parent, introducers, path, header = f"{fix_sha}^", set(), None, False
    diff = git(
        repo,
        "-c",
        "core.quotePath=false",
        "diff",
        "-U0",
        "--no-renames",
        "--src-prefix=a/",
        "--dst-prefix=b/",
        parent,
        fix_sha,
    )
    for line in diff.splitlines():
        if line.startswith("diff --git "):
            path, header = None, True
        elif header and line.startswith(
            "--- "
        ):  # only in the file header: `--- x` in a hunk is content
            p = line[4:].rstrip("\t")  # git tab-suffixes paths with spaces
            if p.startswith(
                '"'
            ):  # C-quoted (", \, control chars): unquote to the raw bytes
                p = ast.literal_eval("b" + p).decode()
            path = None if p == "/dev/null" else p[2:]
        elif line.startswith("@@"):
            header = False
        m = re.match(r"@@ -(\d+)(?:,(\d+))? ", line)
        if m and path and m.group(2) != "0":
            start, n = int(m.group(1)), int(m.group(2) or 1)
            blame = git(
                repo, "blame", "--porcelain", "-L", f"{start},+{n}", parent, "--", path
            )
            introducers |= set(re.findall(r"^([0-9a-f]{40}) \d+ \d+", blame, re.M))
    if not introducers:
        return "unknown"
    # ponytail: scans the whole branch log once per call; fine for fixtures, index trailers once if slow.
    picked = {
        o
        for c in git(
            repo, "log", "--format=%H", "-F", "--grep=(cherry picked from commit", branch
        ).split()
        if not _is_empty(repo, c)
        for o in picked_from(repo, c)
    }  # a decline carries nothing
    hits = [
        is_ancestor(repo, c, branch) or any(c.startswith(p) for p in picked)
        for c in introducers
    ]
    return "relevant" if all(hits) else "not-relevant" if not any(hits) else "partial"
