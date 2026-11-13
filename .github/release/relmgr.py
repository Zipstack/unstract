"""Pure-git checks for the release-branch strategy.

Every function reads a local repo; nothing is stored.
"""

import ast
import datetime as dt
import os
import re
import subprocess
import tempfile

BOT_EMAIL = "releases@unstract.com"
_FORMAT_BODY = "--format=%B"
PICK_RE = re.compile(r"\(cherry picked from commit ([0-9a-f]{7,40})\)")
# At any line start; also after "* ", as a COMMIT_MESSAGES squash lists each subject that way.
RBO_RE = re.compile(r"^(?:\* )?Release-branch-only: (\S+)", re.M)
# Known limit: one ticket only, so `A-1 B-2 [FIX] x` fails.
PR_TITLE_RE = re.compile(
    r"^(?:(?P<ticket>[A-Z][A-Z0-9]*-\d+) )?\[(?P<type>FIX|HOT-FIX|FEAT|GATED-FEAT|DOCS|DEPS|MISC|DEV|WIP)\] \S"
)
# Greedy, so a revert of a revert nests.
REVERT_RE = re.compile(r'^Revert "(.+)"')
REVERTS_RE = re.compile(r"^This reverts commit ([0-9a-f]{7,40})", re.M)
DECLINED_RE = re.compile(r"^Declined: (.+)$", re.M)
# Match with fullmatch.
BACKPORT_HEAD_RE = re.compile(r"backport/(\d+\.\d+)/([0-9a-f]{7})")
LINE_RE = re.compile(r"[0-9]+\.[0-9]+")
# `Backport-also: X.Y` on its own line in a PR body: the fix is owed to release/X.Y although its label does not
# reach that line (a line GA for cloud but not yet for on-prem). Any other line that starts with it, after quote or
# list markers, is malformed.
DECLARE_RE = re.compile(r"^Backport-also: ([0-9]+\.[0-9]+)[ \t]*$", re.M)
_DECLARE_ANY_RE = re.compile(
    r"^[ \t>*+-]*(?:[0-9]+[.)][ \t]*)?backport[ \t_-]*also\b.*$", re.I | re.M
)


def line(value):
    """A release-line input as X.Y: "0.186" and "release/0.186" both give "0.186".

    No stripping: Take RC's concurrency group is keyed on the raw input, so a padded value must not pass.
    """
    v = value.removeprefix("release/")
    if not LINE_RE.fullmatch(v):
        raise ValueError(f"not a release line X.Y (e.g. 0.186): {value!r}")
    return v


def declared_lines(body):
    """The release lines X.Y a PR body declares with `Backport-also: X.Y`."""
    return set(DECLARE_RE.findall((body or "").replace("\r", "")))


def declaration_errors(body):
    """Body lines that try to declare a line but are not exactly `Backport-also: X.Y`."""
    body = (body or "").replace("\r", "")
    return [
        m.strip() for m in _DECLARE_ANY_RE.findall(body) if not DECLARE_RE.fullmatch(m)
    ]


def body_errors(body, labels=()):
    """Lint PR's check on a PR body: a malformed declaration would silently declare nothing, and one on a
    main-only PR can never be picked (Backport skips main-only).
    """
    errors = [
        f"malformed `{b}`: write exactly `Backport-also: X.Y` (e.g. `Backport-also: 0.186`), one line per release "
        "line"
        for b in declaration_errors(body)
    ]
    if MAIN_ONLY in labels and declared_lines(body):
        errors.append(
            f"`{MAIN_ONLY}` with a `Backport-also` line: Backport never picks a {MAIN_ONLY} PR. Label it "
            "`backport/rc` (or `backport/ga`), or remove the declaration"
        )
    return errors


def vtag(value):
    """A version-tag input with its leading v: "0.186.0-rc.2" and "v0.186.0-rc.2" both give "v0.186.0-rc.2"."""
    v = value.strip()
    return v if v.startswith("v") else f"v{v}"


def _web(repo=None):
    server, slug = (
        os.environ.get("GITHUB_SERVER_URL"),
        repo or os.environ.get("GITHUB_REPOSITORY"),
    )
    return f"{server}/{slug}" if server and slug else None


def pr_link(n, repo=None):
    # A repo other than this run's is named in the text, so the reader sees which repo's PR it is.
    web, text = _web(repo), f"{repo or ''}#{n}"
    return f"[{text}]({web}/pull/{n})" if web else text


def commit_link(sha, n=7, repo=None):
    web = _web(repo)
    return f"[`{sha[:int(n)]}`]({web}/commit/{sha})" if web else f"`{sha[:int(n)]}`"


def tag_link(tag, repo=None):
    # The release page: it shows the tag message (an RC's Slack thread) and later the published notes.
    web = _web(repo)
    return f"[`{tag}`]({web}/releases/tag/{tag})" if web else f"`{tag}`"


def branch_link(branch, repo=None):
    web = _web(repo)
    return f"[`{branch}`]({web}/tree/{branch})" if web else f"`{branch}`"


def ref_link(ref, repo=None):
    """The full ref stays the text: a local head and origin's copy of a branch are different reads."""
    web = _web(repo)
    if web and ref.startswith("refs/tags/"):
        return f"[`{ref}`]({web}/releases/tag/{ref.removeprefix('refs/tags/')})"
    if web and (m := re.fullmatch(r"refs/(?:heads|remotes/origin)/(.+)", ref)):
        return f"[`{ref}`]({web}/tree/{m[1]})"
    return f"`{ref}`"


def image_link(target, tag):
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
    r = git(repo, "rev-parse", "-q", "--verify", f"{rev}^{{commit}}", check=False)
    return r.stdout.strip() if r.returncode == 0 else None


def message(repo, sha):
    return git(repo, "log", "-1", _FORMAT_BODY, sha)


def subject_pr(repo, sha, check=True):
    r = git(repo, "log", "-1", "--format=%s", sha, check=check)
    m = re.search(r"\(#(\d+)\)$", r if check else r.stdout.strip())
    return int(m[1]) if m else None


def same_sha(a, b):
    return a.startswith(b) or b.startswith(a)


def ts(s):
    return dt.datetime.fromisoformat(s.replace("Z", "+00:00"))


def is_ancestor(repo, a, b):
    r = git(repo, "merge-base", "--is-ancestor", a, b, check=False)
    if r.returncode not in (0, 1):  # 1 = "no"; anything else is an error, never a "no"
        raise RuntimeError(f"git merge-base --is-ancestor {a} {b}: {r.stderr.strip()}")
    return r.returncode == 0


def on_main(repo, sha, main="main"):
    full = resolve(repo, sha)
    return full is not None and is_ancestor(repo, full, main)


def _is_empty(repo, sha):
    return git(repo, "rev-parse", f"{sha}^{{tree}}") == git(
        repo, "rev-parse", f"{sha}^^{{tree}}"
    )


def picked_from(repo, sha):
    """Resolved to full shas so a hand-written short sha and the bot's full one key the same."""
    return [resolve(repo, o) or o for o in PICK_RE.findall(message(repo, sha))]


def branch_range(repo, branch, main):
    base = git(repo, "merge-base", main, branch)
    out = git(repo, "rev-list", "--reverse", f"{base}..{branch}")
    return out.split() if out else []


def range_messages(repo, branch, main):
    return git(
        repo, "log", _FORMAT_BODY, f"{git(repo, 'merge-base', main, branch)}..{branch}"
    )


def reverted_pick(repo, sha, main="main"):
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
            return "invalid"
        return "declined" if _is_empty(repo, sha) else "cherry-pick"
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
    """A backport/* PR lands as one squash, so only its first commit is judged (needs squash-only merges on
    release/*).
    """
    out = git(repo, "rev-list", "--reverse", f"{base}..{head}")
    commits = out.split() if out else []
    if not commits or not is_backport(head_ref):
        return commits
    return [commits[0]]


def is_backport(head_ref):
    return bool(BACKPORT_HEAD_RE.fullmatch(head_ref))


def pick_trailer(head_ref, msg):
    found = PICK_RE.findall(msg)
    m = BACKPORT_HEAD_RE.fullmatch(head_ref)
    return found[0] if m and len(found) == 1 and found[0].startswith(m[2]) else None


def conflict_markers(repo, rev="HEAD"):
    r = git(repo, "grep", "-l", "-E", "^(<<<<<<<|>>>>>>>)( |$)", rev, "--", check=False)
    if r.returncode not in (0, 1):  # 1 = no match
        raise RuntimeError(f"git grep (exit {r.returncode}): {r.stderr.strip()}")
    return [m.split(":", 1)[1] for m in r.stdout.splitlines()]


def _ci_scope(repo, branch, event, before, head_ref, main):
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
    """Labelled passes a PR's invalid commits as release-branch-only: the squash at merge writes the line. A push
    scans the whole branch when before is all zeros (branch creation) or gone (a force push).
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


BACKPORT_LABELS = {"backport/rc": "rc", "backport/ga": "ga"}
MAIN_ONLY = "main-only"


def _ticks(names):
    return ", ".join(f"`{n}`" for n in names)


def pr_fix_class(title, labels=()):
    """The class ("rc" or "ga") comes from labels only; None without one. A main merge also needs a label: main_fix_class."""
    # Reject near-miss class labels (backport/<x>, backport-ga, fix/<x>, fix-class/<x>, typos) so a typo cannot drop the class.
    bad = [
        l
        for l in labels
        if l not in BACKPORT_LABELS
        and re.match(
            r"\s*(backports?\s*(/|[\W_]+\s*(rc|ga)(?![a-z]))|fix(\w{0,3}[\W_]*class(?![a-z])|\s*/))",
            l,
            re.I,
        )
    ]
    if bad:
        raise ValueError(
            f"unknown label(s) {_ticks(bad)}: use `backport/rc`, `backport/ga` or `{MAIN_ONLY}`"
        )
    found = sorted(set(labels) & set(BACKPORT_LABELS))
    if len(found) > 1:
        raise ValueError(f"conflicting labels {_ticks(found)}: keep one")
    # The changelogs read the title, so no label excuses it. strip: GitHub keeps a leading space.
    inner = title.strip()
    while r := REVERT_RE.match(inner):
        inner = r.group(1).strip()
    if not PR_TITLE_RE.match(inner):
        raise ValueError(f"no recognised '[TYPE]' or 'TICKET [TYPE]' prefix: {title!r}")
    if MAIN_ONLY in labels and found:
        raise ValueError(f"conflicting labels {_ticks([MAIN_ONLY, *found])}: keep one")
    return BACKPORT_LABELS[found[0]] if found else None


def main_fix_class(title, labels=()):
    """pr_fix_class for a PR merged into main, which must say whether it is backported."""
    cls = pr_fix_class(title, labels)
    if refusal := release_only_refusal("main", labels):
        raise ValueError(refusal)
    return cls


def release_only_refusal(base, labels):
    """Label errors that depend on the base. Lint PR on every branch calls this by name, old workflow copies included."""
    if "release-branch-only" in labels and not base.startswith("release/"):
        return (
            "label `release-branch-only` is for PRs into a release/X.Y branch; remove it here "
            "(a main change reaches release branches through Backport)"
        )
    if MAIN_ONLY in labels and base.startswith("release/"):
        return f"label `{MAIN_ONLY}` is for PRs into main; remove it here"
    if not base.startswith("release/") and not set(labels) & {
        MAIN_ONLY,
        *BACKPORT_LABELS,
    }:
        return f"no backport label: add `backport/rc`, `backport/ga` or `{MAIN_ONLY}`"
    return None


def rbo_key(title, pr):
    """A `#<pr>` key matches no other line's, so the convergence report always lists that change for a human."""
    m = PR_TITLE_RE.match(title.strip())
    return m["ticket"] if m and m["ticket"] else f"#{pr}"


# A version names one commit.


def _line(branch):
    m = re.fullmatch(
        r"(?:refs/heads/|(?:refs/remotes/)?[^/]+/)?release/(\d+)\.(\d+)", branch
    )
    if not m:
        raise ValueError(f"not a release branch: {branch}")
    return m.group(1), m.group(2)


def _tags(repo, x, y, prefix=""):
    """Tags without prefix (`ee-` on OSS lines) are another series and never counted."""
    stable, rc = set(), {}
    for t in git(repo, "tag", "-l", f"{prefix}v{x}.{y}.*").split():
        m = re.fullmatch(rf"{re.escape(prefix)}v{x}\.{y}\.(\d+)(?:-rc\.(\d+))?", t)
        if m and m.group(2):
            rc.setdefault(int(m.group(1)), []).append(int(m.group(2)))
        elif m:
            stable.add(int(m.group(1)))
    return stable, rc


def next_patch(repo, branch, prefix=""):
    x, y = _line(branch)
    stable, _ = _tags(repo, x, y, prefix)
    return f"{x}.{y}.{max(stable) + 1 if stable else 0}"


def rc_version(repo, branch, prefix="", taken=()):
    """A commit gets one RC tag. taken: tags already pushed to a registry; never reallocated, except for a tip that
    is already the bot's bump for that tag (resumed). Needs all tags fetched.
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
    """Is the tip the bot's bump for tag? Left behind when a run pushed the bump but not the tag."""
    ver = tag.removeprefix("v")
    chart = git(repo, "show", f"{branch}:{CHART}", check=False)
    if chart.returncode == 0:
        # Older bumps set the chart version without the v; their tags must still resolve.
        ok = {tag, ver}
        found = re.search(r"^version: (.*)$", chart.stdout, re.M)
        if not found or found[1] not in ok:
            return False
        want = {f"release: chart {v}" for v in ok}
    else:
        want = {f"release: {ver}"}
    email, subject = git(repo, "log", "-1", "--format=%ae%n%s", branch).split("\n", 1)
    return email.lower() == BOT_EMAIL.lower() and subject in want


VALUES = "charts/unstract-platform/values.yaml"
# The lines Promote's GA commit may change, by file: the chart version, appVersion and the image tag anchor.
GA_KEYS = {
    CHART: ("version: ", "appVersion: "),
    VALUES: ("UNSTRACT_APPS_VERSION: &UNSTRACT_APPS_VERSION ",),
}


def ga_bump_stray(repo, base, sha, stable):
    """What base..sha changes beyond the GA bump (each GA_KEYS line changed exactly once, to stable); empty when none."""
    want = {
        "version: ": {
            stable,
            stable.removeprefix("v"),
        },  # GA commits made before the v came back
        "appVersion: ": {f'"{stable}"'},
        "UNSTRACT_APPS_VERSION: &UNSTRACT_APPS_VERSION ": {stable},
    }
    stray = [
        f"{s}: {p}"
        for s, p in (
            ln.split("\t", 1)
            for ln in git(
                repo, "diff", "--name-status", "--no-renames", base, sha
            ).splitlines()
        )
        if s != "M" or p not in GA_KEYS
    ]
    if git(repo, "diff", "--summary", base, sha):  # a mode change, create or delete
        stray.append("mode, create or delete")
    path, hunk, count = None, False, {}
    diff = git(
        repo, "diff", "--no-ext-diff", "--no-color", "--no-renames", "-U0", base, sha
    )
    for ln in diff.splitlines():
        if ln.startswith("diff --git "):
            path, hunk = ln.rsplit(" b/", 1)[1], False
        elif ln.startswith("@@"):
            hunk = True
        elif hunk and ln[:1] in ("+", "-") and path in GA_KEYS:
            key = next((k for k in GA_KEYS[path] if ln[1:].startswith(k)), None)
            if key is None or (ln[0] == "+" and ln[1 + len(key) :] not in want[key]):
                stray.append(f"{path}: {ln}")
            else:
                count[path, key, ln[0]] = count.get((path, key, ln[0]), 0) + 1
    for path, key in ((p, k) for p, keys in GA_KEYS.items() for k in keys):
        if not count.get((path, key, "+")) == count.get((path, key, "-")) == 1:
            stray.append(
                f"{path}: {key.strip()} changed {count.get((path, key, '+'), 0)} times"
            )
    return stray


def is_ga_bump(repo, sha, base, stable):
    """Is sha Promote's GA commit for stable on base: the bot's one commit on it, changing only the GA_KEYS lines?"""
    parents = git(repo, "rev-list", "--parents", "-n1", sha).split()[1:]
    return (
        parents == [resolve(repo, base)]
        and already_bumped(repo, sha, stable)
        and not ga_bump_stray(repo, base, sha, stable)
    )


def rc_commit(repo, rev, prefix=""):
    """The commit whose RC tag stands for rev: rev itself, or its parent when rev is a tagged GA commit."""
    sha = git(repo, "rev-parse", f"{rev}^{{commit}}")
    parents = git(repo, "rev-list", "--parents", "-n1", sha).split()[1:]
    for t in git(repo, "tag", "--points-at", sha).split():
        if (
            len(parents) == 1
            and re.fullmatch(rf"{re.escape(prefix)}v\d+\.\d+\.\d+", t)
            and is_ga_bump(repo, sha, parents[0], t)
        ):
            return parents[0]
    return sha


def promote_version(repo, rc_tag):
    """Z follows commit order, so it can differ from the RC's Z. An RC older than an already-stable commit is
    refused as a downgrade.
    """
    m = re.fullmatch(r"((?:[a-z]+-)?)v(\d+)\.(\d+)\.(\d+)-rc\.\d+", rc_tag)
    if not m:
        raise ValueError(f"not an RC tag: {rc_tag}")
    p, x, y = m.group(1), m.group(2), m.group(3)
    commit = git(repo, "rev-parse", f"{rc_tag}^{{commit}}")
    stable, _ = _tags(repo, x, y, p)
    for z in sorted(stable):
        shipped = git(repo, "rev-parse", f"refs/tags/{p}v{x}.{y}.{z}^{{commit}}")
        if commit in (shipped, rc_commit(repo, shipped, p)):
            return f"{p}v{x}.{y}.{z}"
        if is_ancestor(repo, commit, shipped):
            raise ValueError(
                f"{rc_tag} is older than {p}v{x}.{y}.{z}: promoting it would be a downgrade"
            )
    return f"{p}v{x}.{y}.{max(stable) + 1 if stable else 0}"


def is_converged(repo, c_main, branch, main="main"):
    full = git(repo, "rev-parse", f"{c_main}^{{commit}}")
    if is_ancestor(repo, full, branch):
        return True
    return any(
        same_sha(o, full) for o in PICK_RE.findall(range_messages(repo, branch, main))
    )


def trailer_states(repo, branch, main="main"):
    """The newest commit per original wins: a pick after a decline ships the fix again (a reopened PR merged), a
    revert of a pick declines it.
    """
    state = {}
    for c in branch_range(repo, branch, main):
        kind = classify_commit(repo, c, main=main)
        if kind in ("cherry-pick", "declined"):
            for o in picked_from(repo, reverted_pick(repo, c, main) or c):
                state[o] = kind
    return state


def declined_originals(repo, branch, main="main"):
    return {
        o for o, kind in trailer_states(repo, branch, main).items() if kind == "declined"
    }


def decline_records(repo, branch, main="main"):
    rec = {}
    for c in branch_range(repo, branch, main):
        kind = classify_commit(repo, c, main=main)
        if kind in ("cherry-pick", "declined"):
            _record_decline(repo, c, kind, main, rec)
    return {o: r for o, r in rec.items() if r}


def _record_decline(repo, c, kind, main, rec):
    rp = reverted_pick(repo, c, main)
    body = message(repo, c)
    reasons = DECLINED_RE.findall(body)
    reason = reasons[-1].strip() if reasons and not rp else body.splitlines()[0]
    for o in picked_from(repo, rp or c):
        rec[o] = (c, reason) if kind == "declined" else None


def shipped_prs(repo, tags, main="main", lookup=None, line=None):
    """`line`'s own picks of a shipped original are dropped too, by `lookup(pick)` (a clean pick keeps the original's
    subject) and the pick's own `(#n)` (a conflict pick lands as the PR's squash).
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
    """Blocks iff any MISSING; RBO-ABSENT is report-only. Pass newer as a branch while in RC, or as its latest stable
    tag once GA with the branch as newer_branch (it need only carry a decline).
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
    if kind == "invalid":
        return "MISSING" if picked_from(repo, c) else "UNCLASSIFIABLE"
    if kind == "cherry-pick":
        return _pick_status(repo, c, newer, older_declined, newer_picks, declined)
    if kind == "release-branch-only":
        body = message(repo, c)
        if not set(RBO_RE.findall(body)) & newer_rbo:
            return "RBO-ABSENT"
    # declined on `older`: older does not carry the fix, so newer owes nothing.
    return None


def _same(o, names):
    return any(same_sha(o, d) for d in names)


def _pick_status(repo, c, newer, older_declined, newer_picks, declined):
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


def relevance(repo, fix_sha, branch):
    """Advisory only: are the line versions a main fix edits on branch? Pure additions read as unknown."""
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
    p = line[4:].rstrip("\t")  # git tab-suffixes paths with spaces
    if p.startswith('"'):  # C-quoted (", \, control chars): unquote to the raw bytes
        p = ast.literal_eval("b" + p).decode()
    return None if p == "/dev/null" else p[2:]


def _introducers(repo, fix_sha):
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


if __name__ == "__main__":  # for workflow inputs: relmgr.py line|vtag VALUE
    import sys

    try:
        print({"line": line, "vtag": vtag}[sys.argv[1]](sys.argv[2]))
    except ValueError as e:
        sys.exit(f"::error::{e}")
