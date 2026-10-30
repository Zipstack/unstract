"""Pure-git checks for the release-branch strategy.

Every function reads a local repo; nothing is stored.
Repo, state and output paths must resolve under the working directory, GITHUB_WORKSPACE, RUNNER_TEMP or the temp dir.
"""

import ast
import datetime as dt
import os
import re
import subprocess
import tempfile

BOT_EMAIL = "releases@unstract.com"
_FORMAT_BODY = "--format=%B"  # git log: a commit's raw message
PICK_RE = re.compile(r"\(cherry picked from commit ([0-9a-f]{7,40})\)")
# At any line start; also after "* ", as a COMMIT_MESSAGES squash lists each subject that way.
RBO_RE = re.compile(r"^(?:\* )?Release-branch-only: (\S+)", re.M)
# `TICKET [FIX] x` or `[FIX] x`; the ticket is optional. Known limit: one ticket only; `A-1 B-2 [FIX] x` needs a
# fix/ label.
PR_TITLE_RE = re.compile(
    r"^(?:(?P<ticket>[A-Z][A-Z0-9]*-\d+) )?\[(?P<type>FIX|HOT-FIX|FEAT|GATED-FEAT|DOCS|DEPS|MISC|DEV|WIP)\] \S"
)
FIX_CLASSES = ("fix", "security", "critical")
# GitHub's revert title; greedy, so a revert of a revert nests.
REVERT_RE = re.compile(r'^Revert "(.+)"')
# git revert's body line.
REVERTS_RE = re.compile(r"^This reverts commit ([0-9a-f]{7,40})", re.M)
# Reason line of a decline commit.
DECLINED_RE = re.compile(r"^Declined: (.+)$", re.M)
# Pick-PR head: backport/<X.Y>/<sha7> (use fullmatch).
BACKPORT_HEAD_RE = re.compile(r"backport/(\d+\.\d+)/([0-9a-f]{7})")


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


def image_link(target, tag):
    """The Artifact Registry console page of the repository holding target's RC builds (RELSTATE_AR_<TARGET>_RC,
    else RELSTATE_AR_<TARGET>), the tag in the text; plain text when neither is set.
    """
    text = f"`{target}:{tag}`"
    var = "RELSTATE_AR_" + target.upper().replace("-", "_")
    repo = os.environ.get(var + "_RC") or os.environ.get(var, "")
    m = re.fullmatch(r"projects/([^/]+)/locations/([^/]+)/repositories/([^/]+)", repo)
    return (
        f"[{text}](https://console.cloud.google.com/artifacts/docker/{m[1]}/{m[2]}/{m[3]})"
        if m
        else text
    )


_FULL = set()  # repos confirmed non-shallow; failures are not cached


class Refused(RuntimeError, ValueError):
    """An argument refused by a guard: a RuntimeError for the CLI handlers, a ValueError for argparse `type=`."""


def option_free(value):
    """value, refused when git or a subprocess would read it as an option."""
    if value.startswith("-"):
        raise Refused(f"{value!r} starts with '-'")
    return value


def local_path(path):
    """path, refused unless it is the runner's step summary file or resolves under the working directory,
    GITHUB_WORKSPACE, RUNNER_TEMP or the temp dir.
    """
    if path == os.environ.get("GITHUB_STEP_SUMMARY"):
        return path
    real = os.path.realpath(option_free(path))
    roots = {
        os.path.realpath(r)
        for r in (
            os.getcwd(),
            os.environ.get("GITHUB_WORKSPACE"),
            os.environ.get("RUNNER_TEMP"),
            tempfile.gettempdir(),
        )
        if r
    }
    if not any(os.path.commonpath([real, r]) == r for r in roots):
        raise Refused(f"{path} is outside the workspace and temp dirs")
    return path


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
    repo = local_path(repo)
    _require_full_history(repo)
    r = subprocess.run(["git", "-C", repo, *args], capture_output=True, text=True)
    if check and r.returncode:
        raise RuntimeError(
            f"git {' '.join(args)} (exit {r.returncode}): {r.stderr.strip()}"
        )
    return r.stdout.strip() if check else r


def resolve(repo, rev):
    """Full sha of the commit rev names, or None."""
    r = git(repo, "rev-parse", "-q", "--verify", f"{rev}^{{commit}}", check=False)
    return r.stdout.strip() if r.returncode == 0 else None


def message(repo, sha):
    """The raw commit message of sha."""
    return git(repo, "log", "-1", _FORMAT_BODY, sha)


def subject_pr(repo, sha, check=True):
    """The `(#n)` at the end of sha's subject, else None. check=False: an unknown sha reads as None."""
    r = git(repo, "log", "-1", "--format=%s", sha, check=check)
    m = re.search(r"\(#(\d+)\)$", r if check else r.stdout.strip())
    return int(m[1]) if m else None


def same_sha(a, b):
    """Do a and b name the same commit, either one abbreviated?"""
    return a.startswith(b) or b.startswith(a)


def ts(s):
    """An ISO-8601 time; a trailing Z reads as UTC."""
    return dt.datetime.fromisoformat(s.replace("Z", "+00:00"))


def is_ancestor(repo, a, b):
    r = git(repo, "merge-base", "--is-ancestor", a, b, check=False)
    if r.returncode not in (0, 1):  # 1 = "no"; anything else is an error, never a "no"
        raise RuntimeError(f"git merge-base --is-ancestor {a} {b}: {r.stderr.strip()}")
    return r.returncode == 0


def on_main(repo, sha, main="main"):
    """Does `sha` (full or unambiguous prefix) name a commit on `main`?"""
    full = resolve(repo, sha)
    return full is not None and is_ancestor(repo, full, main)


def _is_empty(repo, sha):
    return git(repo, "rev-parse", f"{sha}^{{tree}}") == git(
        repo, "rev-parse", f"{sha}^^{{tree}}"
    )


def picked_from(repo, sha):
    """Main originals named by the commit's `-x` trailers, each resolved to its full sha so that callers keying on
    them see a hand-written short sha and the bot's full one as the same original. A trailer that does not resolve
    (unknown or ambiguous) is kept as written.
    """
    return [resolve(repo, o) or o for o in PICK_RE.findall(message(repo, sha))]


def branch_range(repo, branch, main):
    """Commits in merge-base(main, branch)..branch: the convergence scan range."""
    base = git(repo, "merge-base", main, branch)
    out = git(repo, "rev-list", "--reverse", f"{base}..{branch}")
    return out.split() if out else []


def range_messages(repo, branch, main):
    """All commit messages in merge-base(main, branch)..branch, as one string (one git call)."""
    return git(
        repo, "log", _FORMAT_BODY, f"{git(repo, 'merge-base', main, branch)}..{branch}"
    )


# Commit kinds / release-branch CI gate ---------------------------------------------------------------


def reverted_pick(repo, sha, main="main"):
    """The full sha of the pick that `sha` reverts on its own branch (after the cut), else None."""
    m = REVERTS_RE.search(message(repo, sha))
    if not m or git(repo, "cat-file", "-e", f"{m[1]}^{{commit}}", check=False).returncode:
        return None
    t = git(repo, "rev-parse", f"{m[1]}^{{commit}}")
    on_branch = is_ancestor(repo, t, sha) and not is_ancestor(repo, t, main)
    return (
        t if on_branch and classify_commit(repo, t, main=main) == "cherry-pick" else None
    )


def classify_commit(repo, sha, bot_email=BOT_EMAIL, main="main"):
    body = message(repo, sha)
    if PICK_RE.search(body):
        if not all(on_main(repo, o, main) for o in PICK_RE.findall(body)):
            return "invalid"  # trailer names nothing on main
        return "declined" if _is_empty(repo, sha) else "cherry-pick"
    # A revert of a pick declines it on this branch.
    if reverted_pick(repo, sha, main):
        return "declined"
    # Checked before the author: a bot-made pin bump still needs a report.
    if RBO_RE.search(body):
        return "release-branch-only"
    # Trust assumption: the author email is client-set; the review every release-branch PR gets is the backstop.
    if git(repo, "log", "-1", "--format=%ae", sha).lower() == bot_email.lower():
        return "build-generated"
    return "invalid"


def pr_commits(repo, base, head_ref, head="HEAD"):
    """Commits the PR check classifies. A backport/* PR lands as one squash, so only its first commit is judged
    (needs squash-only merges on release/*). Any other PR: every commit in base..head.
    """
    out = git(repo, "rev-list", "--reverse", f"{base}..{head}")
    commits = out.split() if out else []
    if not commits or not is_backport(head_ref):
        return commits
    return [commits[0]]


def is_backport(head_ref):
    """Is head_ref a pick head Backport names (backport/X.Y/<sha7>)? Any other name is judged commit by commit."""
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


def _ci_scope(repo, branch, event, before, head_ref, main):
    """ci_commits' ([sha], where) for one event."""
    if event == "pull_request":
        if is_backport(head_ref) and (marked := conflict_markers(repo)):
            raise ValueError(
                f"conflict markers in {', '.join(marked)}: resolve before merging"
            )
        return pr_commits(repo, branch, head_ref), f"PR into {branch}"
    if (
        set(before) - {"0"}
        and git(repo, "cat-file", "-e", f"{before}^{{commit}}", check=False).returncode
        == 0
    ):
        # Pushed commits only, so a revert can clear an earlier invalid commit.
        out = git(repo, "rev-list", "--reverse", f"{before}..HEAD")
        return (out.split() if out else []), f"push to {branch}"
    return branch_range(repo, branch, main), branch


def ci_commits(
    repo, branch, event, before="", head_ref="", labelled=False, main="origin/main"
):
    """Release branch CI over one event: ([(sha, kind)], where). ValueError: conflict markers in a backport PR's tree.

    pull_request: the PR's own commits (a backport PR's first only, invalid unless it carries exactly one pick
    trailer, naming the head's sha7); labelled turns its invalid commits into
    release-branch-only, since the squash at merge writes the line. push: the pushed commits before..HEAD, or the
    whole branch when before is all zeros (branch creation) or gone (a force push).
    """
    commits, where = _ci_scope(repo, branch, event, before, head_ref, main)
    labelled = labelled and event == "pull_request"
    backport_pr = event == "pull_request" and is_backport(head_ref)
    rows = []
    for c in commits:
        kind = classify_commit(repo, c, main=main)
        # The squash keeps the first commit's trailers: it must name the head's fix only.
        if backport_pr and not pick_trailer(head_ref, message(repo, c)):
            kind = "invalid"
        # Known limit: the label passes every invalid commit without checking that the squash will carry a
        # Release-branch-only line.
        rows.append(
            (c, "release-branch-only (label)" if labelled and kind == "invalid" else kind)
        )
    return rows, where


# PR class (Lint PR) ------------------------------------------------------

FIX_LABELS = ("fix/security", "fix/critical", "fix/needs-backport")


def pr_fix_class(title, labels=()):
    """'fix' | 'security' | 'critical' for fix PRs, None for non-fix PRs; ValueError = CI rejects."""
    # Reject near-miss class labels (fix/<x>, fix-class/<x>, typos) so a typo cannot drop the class.
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
    # A revert takes the reverted PR's class. Strip: GitHub keeps a leading space.
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


# Version allocation (at build time; a version names one commit) ------------------------------------------------


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
    taken: tags already pushed to a registry; never reallocated, except for a tip that is already the bot's bump
    for that tag (resumed). Needs all tags fetched.
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
    """Is the branch tip the bot's bump for tag (`release: chart <v>` with the chart at <v>, or `release: <v>` with
    no chart)? Left behind when a run pushed the bump but not the tag.
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
    """Stable tag for rc_tag: the commit's existing stable tag, else one past the highest. Z follows commit order,
    so it can differ from the RC's Z (the release body maps RC to stable). An RC older than an already-stable commit
    is refused as a downgrade.
    """
    # The stable tag keeps the RC's prefix.
    m = re.fullmatch(r"((?:[a-z]+-)?)v(\d+)\.(\d+)\.(\d+)-rc\.\d+", rc_tag)
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


# Convergence --------------------------------------------------------------------


def is_converged(repo, c_main, branch, main="main"):
    """Inherited (ancestor) or picked/declined after the cut (trailer in merge-base..branch)."""
    full = git(repo, "rev-parse", f"{c_main}^{{commit}}")
    if is_ancestor(repo, full, branch):
        return True
    return any(
        same_sha(o, full) for o in PICK_RE.findall(range_messages(repo, branch, main))
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
            _record_decline(repo, c, kind, main, rec)
    return {o: r for o, r in rec.items() if r}


def _record_decline(repo, c, kind, main, rec):
    """decline_records' step for one pick-trailer commit c: set rec[original] for each original it names."""
    rp = reverted_pick(repo, c, main)
    body = message(repo, c)
    reasons = DECLINED_RE.findall(body)
    reason = reasons[-1].strip() if reasons and not rp else body.splitlines()[0]
    for o in picked_from(repo, rp or c):
        rec[o] = (c, reason) if kind == "declined" else None


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
        n = subject_pr(repo, o)
        if n is None and lookup:
            n = lookup(o)
        if n is None:
            raise RuntimeError(
                f"no PR number for {o[:12]} (picked into {', '.join(tags)})"
            )
        prs.add(n)
    if line:
        prs |= _line_pick_prs(repo, line, originals, main, lookup)
    return prs


def _line_pick_prs(repo, line, originals, main, lookup):
    """shipped_prs' PRs that landed line's picks of `originals`."""
    prs = set()
    for c in branch_range(repo, line, main):
        if classify_commit(repo, c, main=main) == "cherry-pick" and any(
            same_sha(o, d) for o in originals for d in picked_from(repo, c)
        ):
            prs |= {
                n
                for n in (subject_pr(repo, c), lookup(c) if lookup else None)
                if n is not None
            }
    return prs


def convergence_report(repo, older, newer, main="main", newer_branch=None):
    """[(sha_on_older, status)] with status CONVERGED | MISSING | UNCLASSIFIABLE | RBO-ABSENT. Blocks iff any MISSING.

    RBO-ABSENT is report-only (a key on older with no Release-branch-only commit on newer). Pass newer as a branch
    while in RC, or as its latest stable tag once GA, with the branch as newer_branch (it need only carry a
    decline). A pick whose original is not on main is MISSING.
    """
    out = []
    # Newest trailer wins on both sides (see trailer_states).
    declined = declined_originals(repo, newer_branch or newer, main)
    newer_picks = {
        o
        for o, kind in trailer_states(repo, newer, main).items()
        if kind == "cherry-pick"
    }
    older_declined = declined_originals(repo, older, main)
    newer_rbo = set(RBO_RE.findall(range_messages(repo, newer, main)))
    for c in branch_range(repo, older, main):
        kind = classify_commit(repo, c, main=main)
        status = _older_status(
            repo, c, kind, newer, older_declined, newer_picks, declined, newer_rbo
        )
        if status:
            out.append((c, status))
    return out


def _older_status(repo, c, kind, newer, older_declined, newer_picks, declined, newer_rbo):
    """convergence_report's status for commit c on older, None when it is not reported."""
    if kind == "invalid":
        return "MISSING" if picked_from(repo, c) else "UNCLASSIFIABLE"
    if kind == "cherry-pick":
        return _pick_status(repo, c, newer, older_declined, newer_picks, declined)
    if kind == "release-branch-only":
        body = message(repo, c)
        if not set(RBO_RE.findall(body)) & newer_rbo:
            return "RBO-ABSENT"
    # build-generated: excluded from convergence.
    # declined on `older`: older does not carry the fix, so newer owes nothing.
    return None


def _same(o, names):
    return any(same_sha(o, d) for d in names)


def _pick_status(repo, c, newer, older_declined, newer_picks, declined):
    """convergence_report's status for a pick on older: CONVERGED | MISSING, None when it owes nothing."""
    # Backed out of older: newer owes nothing.
    if all(_same(o, older_declined) for o in picked_from(repo, c)):
        return None
    ok = all(
        is_ancestor(repo, git(repo, "rev-parse", f"{o}^{{commit}}"), newer)
        or _same(o, newer_picks)
        or _same(o, declined)
        for o in picked_from(repo, c)
    )
    return "CONVERGED" if ok else "MISSING"


# Relevance (advisory: does the branch still have the code a fix touches?) ------------------


def relevance(repo, fix_sha, branch):
    """Are the line versions a main fix edits on branch? relevant | not-relevant | partial | unknown. Blames the
    fix's pre-image lines; each introducer counts if it is an ancestor of branch or picked onto it. Pure additions:
    unknown. Advisory only.
    """
    introducers = _introducers(repo, fix_sha)
    if not introducers:
        return "unknown"
    # Known limit: scans the branch log once per call.
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
    if all(hits):
        return "relevant"
    if not any(hits):
        return "not-relevant"
    return "partial"


def _minus_path(line):
    """The path of a `--- ` file-header line, None for /dev/null."""
    p = line[4:].rstrip("\t")  # git tab-suffixes paths with spaces
    if p.startswith('"'):  # C-quoted (", \, control chars): unquote to the raw bytes
        p = ast.literal_eval("b" + p).decode()
    return None if p == "/dev/null" else p[2:]


def _introducers(repo, fix_sha):
    """The last-modifying commits of the pre-image lines fix_sha modifies/deletes (for relevance)."""
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
        # Only in the file header: `--- x` in a hunk is content.
        elif header and line.startswith("--- "):
            path = _minus_path(line)
        elif line.startswith("@@"):
            header = False
        m = re.match(r"@@ -(\d+)(?:,(\d+))? ", line)
        if m and path and m.group(2) != "0":
            start, n = int(m.group(1)), int(m.group(2) or 1)
            blame = git(
                repo, "blame", "--porcelain", "-L", f"{start},+{n}", parent, "--", path
            )
            introducers |= set(re.findall(r"^([0-9a-f]{40}) \d+ \d+", blame, re.M))
    return introducers
