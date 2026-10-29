"""Branch and target state for the release-branch workflows, derived from git and the target registries.

Usage: relstate.py [--repo DIR] [--now 2026-09-29T00:00:00Z] [--rc vX.Y.Z-rc.N]

Prints one JSON document: every release/X.Y branch with its per-target state (enabled, GA, support window),
plus the derived sets later workflows need. Nothing is stored. Version allocation, commit
classification and convergence stay in relmgr.py.
"""

import argparse
import datetime as dt
import http.client
import json
import os
import re
import sys
import time
import traceback
import urllib.error
import urllib.parse
import urllib.request

import relmgr as rm

# On-prem support: 184 days (longest 6 months) from the line's first stable chart push, and only the newest 6 GA
# lines.
WINDOW = dt.timedelta(days=184)
WINDOW_LINES = 6
# Per repo, so both repos run this file; use() loads an entry as (TARGETS, LATEST_ONLY: only the latest GA line is
# supported, KEPT: supported while the branch exists, PINS: repo whose tags pyproject.toml pins, PREFIX: tag prefix).
# TARGETS: target -> (build artifact, GA anchor artifact), each <kind>/<package>; RELSTATE_AR_<KIND> names its
# repository. GIT: the line's own git tags stand in for an artifact (OSS lines). OSS lines are tagged
# ee-vX.Y.Z(-rc.N).
GIT = "git"
REPOS = {
    # backend: every build pushes it, and all services share one tag.
    "unstract-cloud": (
        {
            "cloud": ("cloud/backend", "cloud/backend"),
            "on-prem": ("on-prem/backend", "chart/unstract-platform"),
        },
        {"cloud"},
        set(),
        "Zipstack/unstract",
        "",
    ),
    "unstract": ({"oss": (GIT, GIT)}, set(), {"oss"}, None, "ee-"),
}
SLUG = (
    os.environ.get("GITHUB_REPOSITORY", "zipstack/unstract-cloud").lower().split("/")[1]
)


def ver_re(prefix):
    return re.compile(rf"{re.escape(prefix)}v(\d+)\.(\d+)\.(\d+)(?:-rc\.(\d+))?")


def use(slug):
    """Load the REPOS config of slug (a repo name) into the module globals."""
    global TARGETS, LATEST_ONLY, KEPT, PINS, PREFIX, VER_RE
    if slug not in REPOS:
        raise RuntimeError(
            f"relstate has no config for repo {slug!r} (GITHUB_REPOSITORY); known: {', '.join(REPOS)}"
        )
    TARGETS, LATEST_ONLY, KEPT, PINS, PREFIX = REPOS[slug]
    VER_RE = ver_re(PREFIX)


use(SLUG)


AR_API = "https://artifactregistry.googleapis.com/v1"
# OSS tag stabilized/X.Y: every enabled target of the paired cloud line reached GA. OSS git cannot see the cloud
# registry, so cloud Promote writes it.
STABILIZED = "stabilized/"


def ar_repository(kind):
    """The Artifact Registry repository resource (projects/<p>/locations/<l>/repositories/<r>) of an artifact kind,
    from RELSTATE_AR_<KIND>: the calling workflow sets it, so no registry location lives in this file.
    """
    var = "RELSTATE_AR_" + kind.upper().replace("-", "_")
    if not (repo := os.environ.get(var)):
        raise RuntimeError(
            f"registry read {kind}/*: set {var} to projects/<p>/locations/<l>/repositories/<r>"
        )
    return repo


def _ar_get(url, what):
    """GET an Artifact Registry API url as JSON, or None when it answers 404. Raises on any other failure."""
    if not (token := os.environ.get("RELSTATE_AR_TOKEN")):
        raise RuntimeError(
            f"registry read {what}: set RELSTATE_AR_TOKEN to an access token"
        )
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}"})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return None
        try:
            detail = e.read().decode(errors="replace")[:300]
        except (OSError, http.client.HTTPException) as r:  # the error body itself cut off
            detail = repr(r)
        raise RuntimeError(f"registry read {what}: HTTP {e.code}: {detail}") from e
    except (
        OSError,
        http.client.HTTPException,
        ValueError,
    ) as e:  # network (URLError), timeout, a cut-off response, bad JSON
        raise RuntimeError(f"registry read {what}: {e!r}") from e


def _ar_versions(artifact):
    """Every version of artifact (<kind>/<package>) with its tags, or None when its first page answers 404."""
    kind, package = artifact.split("/", 1)
    url = f"{AR_API}/{ar_repository(kind)}/packages/{urllib.parse.quote(package, safe='')}/versions"
    out, page = [], ""
    while True:
        q = {"view": "FULL", "pageSize": 1000, **({"pageToken": page} if page else {})}
        if (body := _ar_get(f"{url}?{urllib.parse.urlencode(q)}", artifact)) is None:
            if page:  # a later page vanished: the list is incomplete, not empty
                raise RuntimeError(f"registry read {artifact}: HTTP 404 on page {page}")
            return None
        out += body.get("versions", [])
        if not (page := body.get("nextPageToken")):
            return out


def registry_tags(artifact):
    """{tag: {id, digest, pushed_at}} for one Artifact Registry artifact (<kind>/<package>). Raises on any read
    failure. pushed_at is the version's createTime, to the second.

    A 404 is only read as "artifact not pushed yet" when the artifact's own repository reads; otherwise it may be
    a wrong RELSTATE_AR_<KIND>, and an empty registry would read as "nothing enabled".
    """
    versions = _ar_versions(artifact)
    if versions is None:
        repo = ar_repository(artifact.split("/", 1)[0])
        if _ar_get(f"{AR_API}/{repo}", artifact) is None:
            raise RuntimeError(
                f"registry read {artifact}: 404 and repository {repo} not found"
            )
        return {}
    out = {}
    for v in versions:
        pushed = re.sub(
            r"\.\d+(?=Z$)", "", v["createTime"]
        )  # AR returns up to 9 fraction digits
        for t in v.get("relatedTags") or []:
            tag = t["name"].rsplit("/tags/", 1)[1]
            out[tag] = {
                "id": v["name"],
                "digest": v["name"].rsplit("/versions/", 1)[1],
                "pushed_at": pushed,
            }
    return out


def _read(artifact, registry):
    """registry(artifact), with chart tags X.Y.Z read as vX.Y.Z (charts are tagged without the v)."""
    tags = registry(artifact)
    if not artifact.startswith("chart/"):
        return tags
    return {
        ("v" + t if re.fullmatch(r"\d+\.\d+\.\d+", t) else t): info
        for t, info in tags.items()
    }


def taken_tags(reg=None, registry=registry_tags):
    """Every tag on every registry artifact of TARGETS: an RC there is never allocated again (rc_version taken).
    reg: {artifact: tags} already read; artifacts missing from it are read.
    """
    reg = reg or {}
    return {t for a in _artifacts() for t in (reg[a] if a in reg else registry(a))}


def _artifacts(git=False):
    """Sorted registry artifacts of TARGETS; GIT too when git."""
    return sorted(
        {a for pair in TARGETS.values() for a in pair} - (set() if git else {GIT})
    )


_ts = rm.ts


def _key(line):
    return tuple(int(p) for p in line.split("."))


def _vkey(tag):
    m = re.fullmatch(r"(?:[a-z]+-)?" + ver_re("").pattern, tag)
    return int(m[3]), int(m[4] or 0)


def _branches(repo):
    """{"release/X.Y": ref}; origin's copy wins over a local one. Legacy release/vX.Y.Z heads are ignored."""
    out = {}
    for ref in rm.git(
        repo,
        "for-each-ref",
        "--format=%(refname)",
        "refs/heads/release/",
        "refs/remotes/origin/release/",
    ).split():
        name = re.sub(r"^refs/(heads|remotes/origin)/", "", ref)
        if re.fullmatch(r"release/\d+\.\d+", name) and (
            name not in out or ref.startswith("refs/remotes/")
        ):
            out[name] = ref
    return out


def ahead_of_ga(repo, ref, line):
    """Commits on ref after the line's latest stable git tag (what a rebuild would ship); None before GA."""
    stable, _ = rm._tags(repo, *line.split("."), PREFIX)
    return (
        int(rm.git(repo, "rev-list", "--count", f"{PREFIX}v{line}.{max(stable)}..{ref}"))
        if stable
        else None
    )


def _tag_commit(repo, tag):
    return rm.resolve(repo, f"refs/tags/{tag}")


def line_tags(repo, line, *args, prefix=None):
    """Version tags of line X.Y from `git tag <args> -l`; prefix: the tag prefix, this repo's by default."""
    prefix = PREFIX if prefix is None else prefix
    ver = ver_re(prefix)
    return [
        t
        for t in rm.git(repo, "tag", *args, "-l", f"{prefix}v{line}.*").split()
        if (m := ver.fullmatch(t)) and f"{m[1]}.{m[2]}" == line
    ]


def older_newer(a, b):
    """(older, newer) of two release/X.Y branches."""
    return tuple(sorted((a, b), key=lambda n: _key(n.split("/", 1)[1])))


def moved_archive(repo, line, sha):
    """An archive tag retired/<line>-* that an earlier run put on an ancestor of sha: the line moved after it was
    archived, so a second tag would split its record. None otherwise. A tag off sha's history (an earlier line of a
    reused minor) is not one.
    """
    for t in rm.git(repo, "tag", "-l", f"retired/{line}-*").split():
        if t != f"retired/{line}-{sha[:7]}" and rm.is_ancestor(
            repo, _tag_commit(repo, t), sha
        ):
            return t
    return None


def git_tags(repo):
    """{tag: {digest: commit, pushed_at}} of the repo's version tags: the GIT stand-in for a registry artifact."""
    out = {}
    for row in rm.git(
        repo,
        "for-each-ref",
        "--format=%(refname:short) %(creatordate:iso-strict) %(objectname) %(*objectname)",
        f"refs/tags/{PREFIX}v*",
    ).splitlines():
        tag, date, obj, peeled = (row.split() + [""])[:4]
        if VER_RE.fullmatch(tag):
            out[tag] = {"id": None, "digest": peeled or obj, "pushed_at": date}
    return out


def rc_slack(repo, tag):
    """The `Slack: <url>` line of an annotated RC tag's message (Take RC build slack_url), else None."""
    m = re.search(
        r"^Slack: (\S+)$", rm.git(repo, "tag", "-l", tag, "--format=%(contents)"), re.M
    )
    return m[1] if m else None


def target_state(t, name, rows, now):
    """State of target t on an enabled branch. Single source of the GA/support rules.

    On-prem: stabilized for WINDOW after the line's first stable chart push (a patch does not extend it), and only while
    among the newest WINDOW_LINES lines with an on-prem GA. A LATEST_ONLY target (cloud): only the latest GA branch
    for it stays stabilized; older GA branches are past-eos for it. A KEPT target (OSS): stabilizing until every
    enabled target of its paired cloud line is GA (the STABILIZED tag, which `oss.py promote --stabilized` writes),
    then stabilized while the branch exists; the cloud lines pinning it decide its retirement, and cloud Retire names it.
    """
    ga = rows[name]["targets"][t]["ga"]
    # Known limit: a target never GA stays stabilizing; retire it with Retire retire_line.
    if not ga:
        return "stabilizing"
    if t in KEPT:
        return "stabilized" if rows[name]["targets"][t]["stabilized"] else "stabilizing"
    t_ga = sorted(
        (n for n, r in rows.items() if r["targets"].get(t, {}).get("ga")),
        key=lambda n: _key(rows[n]["line"]),
        reverse=True,
    )
    if t in LATEST_ONLY:
        return "stabilized" if name == t_ga[0] else "past-eos"
    return (
        "stabilized"
        if now < _ts(ga["pushed_at"]) + WINDOW and name in t_ga[:WINDOW_LINES]
        else "past-eos"
    )


def _main(repo):
    return (
        "origin/main"
        if rm.git(
            repo, "rev-parse", "-q", "--verify", "refs/remotes/origin/main", check=False
        ).returncode
        == 0
        else "main"
    )


def _next_minor(repo, ordered):
    """One minor past the highest release line, shipped retired line or stable tag merged into main (a stable tag
    off main, e.g. a release not merged back, does not count). A line retired before GA is reused.
    """
    main = _main(repo)
    lines = [
        (int(m[1]), int(m[2]))
        for t in rm.git(repo, "tag", "--merged", main, "-l", f"{PREFIX}v*").split()
        if (m := VER_RE.fullmatch(t)) and not m[4]
    ] + [_key(r["line"]) for r in ordered]
    lines += [
        (int(m[1]), int(m[2]))
        for t in rm.git(repo, "tag", "-l", "retired/*").split()
        if (m := re.fullmatch(r"retired/(\d+)\.(\d+)-[0-9a-f]+", t))
        and rm._tags(repo, m[1], m[2], PREFIX)[0]
    ]
    return f"{max(lines)[0]}.{max(lines)[1] + 1}" if lines else None


def _row(repo, name, ref, taken):
    """The derive() row of one release/X.Y branch, before its targets are filled in."""
    # The tip's RC tag if built, else the next one.
    tip = rm.rc_version(repo, ref, PREFIX, taken)
    built = tip in rm.git(repo, "tag", "--points-at", ref).split()
    line = name.split("/", 1)[1]
    row = {
        "branch": name,
        "line": line,
        "state": None,
        "enabled": [],
        "next_rc": None if built else tip,
        "tip_rc": tip if built else None,
        "ahead_of_ga": ahead_of_ga(repo, ref, line),
        "targets": {},
    }
    if built and (url := rc_slack(repo, tip)):  # only when the RC has a link
        row["tip_rc_slack"] = url
    return row


def _anomaly_reason(repo, name, refs, sha):
    """Why a build tag enables nothing on its line, or None when its commit is on the branch."""
    if name not in refs:
        return "no branch"
    if not sha:
        return "no git tag"
    if not rm.is_ancestor(repo, sha, refs[name]):
        return "commit not on branch"
    return None


def _shipped(repo, name, m, shipped):
    """Whether the branchless line name (version match m) has a git stable tag, cached in shipped."""
    if name not in shipped:  # one git tag read per line, not per registry tag
        shipped[name] = bool(rm._tags(repo, m[1], m[2], PREFIX)[0])
    return shipped[name]


def _enable(repo, t, builds, reg, refs, rows, shipped, anomalies):
    """Mark target t enabled on each branch holding one of its build tags; anomalies get the rest."""
    for tag in sorted(reg[builds]):
        m = VER_RE.fullmatch(tag)
        if not m:
            continue  # not a release version (e.g. smoke tags)
        name = f"release/{m[1]}.{m[2]}"
        if name not in refs and _shipped(repo, name, m, shipped):
            continue
        sha = _tag_commit(repo, tag)
        if why := _anomaly_reason(repo, name, refs, sha):
            anomalies.append(
                {
                    "target": t,
                    "artifact": builds,
                    "tag": tag,
                    "branch": name,
                    "reason": why,
                }
            )
            continue
        tt = rows[name]["targets"].setdefault(
            t, {"state": None, "rcs": [], "ga": None, "promoted": None}
        )
        if m[4]:
            tt["rcs"].append(tag)


def _fill_ga(repo, t, builds, anchor, reg, rows):
    """Sort target t's RCs and set its ga / promoted (and KEPT stabilized) on every branch it is enabled on."""
    for row in rows.values():
        tt = row["targets"].get(t)
        if not tt:
            continue
        tt["rcs"].sort(key=_vkey)
        # ga: the anchor's first stable (state, window). promoted: the build artifact's latest stable (ships next).
        # Charts are read as vX.Y.Z (_read).
        stable = re.compile(rf"{re.escape(PREFIX)}v{re.escape(row['line'])}\.\d+")
        for key, artifact, pick in (("ga", anchor, 0), ("promoted", builds, -1)):
            if tags := sorted(
                (g for g in reg[artifact] if stable.fullmatch(g)), key=_vkey
            ):
                tt[key] = {"tag": tags[pick], **reg[artifact][tags[pick]]}
        if t in KEPT:
            tt["stabilized"] = bool(_tag_commit(repo, STABILIZED + row["line"]))


def _line_state(states):
    """A line's state from its targets' states."""
    if not states or "stabilizing" in states:
        return "stabilizing"
    if "stabilized" in states:
        return "stabilized"
    return "past-eos"


def _set_states(rows, now):
    """Set every target's and line's state and enabled list on rows."""
    for name, row in rows.items():
        for t, tt in row["targets"].items():
            tt["state"] = target_state(t, name, rows, now)
        row["enabled"] = sorted(row["targets"])
        # No enabled target (cut, nothing built yet) is stabilizing: every line builds cloud by default.
        row["state"] = _line_state({tt["state"] for tt in row["targets"].values()})


def _sets(ordered):
    """The supported, backport_targets and retire sets of derive() over the ordered rows."""
    return {
        "supported": {
            t: [
                r["branch"]
                for r in ordered
                if r["targets"].get(t, {}).get("state") in ("stabilizing", "stabilized")
            ]
            for t in TARGETS
        },
        "backport_targets": {
            "fix": [r["branch"] for r in ordered if r["state"] == "stabilizing"],
            "security_critical": [
                {
                    "branch": r["branch"],
                    "needs_rm_confirmation": r["state"] == "stabilized",
                }
                for r in ordered
                if r["state"] in ("stabilizing", "stabilized")
            ],
        },
        "retire": [
            r["branch"]
            for r in ordered
            if r["state"] == "past-eos" and any(tt["ga"] for tt in r["targets"].values())
        ],
    }


def derive(repo, now, registry=registry_tags, rc=None):
    t0 = time.monotonic()
    reg = {
        a: git_tags(repo) if a == GIT else _read(a, registry)
        for a in _artifacts(git=True)
    }
    print(
        f"relstate: registry read {len(reg)} artifacts in {time.monotonic() - t0:.2f}s",
        file=sys.stderr,
    )
    refs = _branches(repo)
    anomalies = []
    taken = taken_tags(reg)
    rows = {name: _row(repo, name, ref, taken) for name, ref in refs.items()}
    # A branchless line with a stable tag was retired after GA: its registry tags are history, not anomalies.
    shipped = {}

    # enabled: a build tag of T whose git commit is on the branch (derived, never recorded).
    for t, (builds, anchor) in TARGETS.items():
        _enable(repo, t, builds, reg, refs, rows, shipped, anomalies)
        _fill_ga(repo, t, builds, anchor, reg, rows)

    _set_states(rows, now)

    ordered = sorted(rows.values(), key=lambda r: _key(r["line"]), reverse=True)
    out = {
        "now": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "branches": ordered,
        **_sets(ordered),
        "next_minor": _next_minor(repo, ordered),
        "anomalies": anomalies,
    }
    if rc:
        out["promote"] = {"rc": rc, "stable": rm.promote_version(repo, rc)}
    return out


def retire_line_refusal(state, branch, force=False):
    """Why Retire `retire_line` refuses branch, or None. A stabilizing target (RCs, no GA: an on-prem line never
    promoted, say) may go. A stabilized on-prem target (chart in its window) goes only with force. Stabilized cloud
    is production and never goes: relstate would make the next older cloud GA production again.
    """
    row = _branch_row(state, branch)
    if not row:
        return "no such branch"
    held = [t for t, tt in sorted(row["targets"].items()) if tt["state"] == "stabilized"]
    if "cloud" in held:
        return "cloud is production (newest cloud GA); it retires once a newer line is promoted"
    if held and not force:
        return f"{', '.join(held)} still supported (stabilized); force to retire it inside the window"
    return None


def _branch_row(state, branch):
    """The row of branch in state, or None."""
    return next((b for b in state["branches"] if b["branch"] == branch), None)


def _by_digest(tags):
    """{digest: {id, digest, tags}} of an artifact's {tag: info}."""
    by_digest = {}
    # Version order, so the last version is the newest RC (rc.10 after rc.9); other tags first.
    for t, info in sorted(
        tags.items(),
        key=lambda kv: (_vkey(kv[0]) if VER_RE.fullmatch(kv[0]) else (-1, -1), kv[0]),
    ):
        by_digest.setdefault(
            info["digest"],
            {"id": info.get("id"), "digest": info["digest"], "tags": []},
        )["tags"].append(t)
    return by_digest


def _abandon_versions(reg, rc_re):
    """abandon_plan's versions to delete per artifact and the last versions kept."""
    versions, kept = {}, []
    for a, tags in reg.items():
        by_digest = _by_digest(tags)
        drop = [
            v for v in by_digest.values() if all(rc_re.fullmatch(t) for t in v["tags"])
        ]
        # Known limit: untagged versions are not listed, so "last" counts tagged ones only.
        if drop and len(drop) == len(by_digest):
            kept.append(f"{a}:{','.join(drop[-1]['tags'])}")
            drop = drop[:-1]
        if drop:
            versions[a] = drop
    return versions, kept


def abandon_plan(repo, branch, registry=registry_tags):
    """What Retire `abandon` deletes for an existing release/X.Y line that never shipped (cut by mistake, or built only as RCs).

    {"ga": [...], "used": [...], "rc_tags": [...], "versions": {artifact: [{id, digest, tags}]}, "kept": [...]}.
    A non-empty ga (git stable tag or GA-anchor registry tag) or used (commits that are not bot, pick or
    decline) refuses the abandon. A registry version is deleted only when every tag on it is an RC of
    this line. An artifact's last tagged version is kept and listed, so an abandon never empties an artifact.
    """
    x, y = rm._line(branch)
    rc_re = re.compile(rf"{re.escape(PREFIX)}v{x}\.{y}\.\d+-rc\.\d+")
    reg = {a: _read(a, registry) for a in _artifacts()}
    main = _main(repo)
    ga = [f"{PREFIX}v{x}.{y}.{z}" for z in sorted(rm._tags(repo, x, y, PREFIX)[0])]
    ga += [
        f"{a}:{t}"
        for a in sorted({anchor for _, anchor in TARGETS.values()} - {GIT})
        for t in sorted(reg[a])
        if re.fullmatch(rf"v{x}\.{y}\.\d+", t)
    ]
    used = [
        c[:12]
        for c in rm.branch_range(repo, _branches(repo)[branch], main)
        if rm.classify_commit(repo, c, main=main)
        not in ("build-generated", "cherry-pick", "declined")
    ]
    versions, kept = _abandon_versions(reg, rc_re)
    rc_tags = sorted(
        (
            t
            for t in rm.git(repo, "tag", "-l", f"{PREFIX}v{x}.{y}.*").split()
            if rc_re.fullmatch(t)
        ),
        key=_vkey,
    )
    return {
        "ga": ga,
        "used": used,
        "rc_tags": rc_tags,
        "versions": versions,
        "kept": kept,
    }


def stabilizes(row, target, done=()):
    """Whether promoting target leaves every enabled target of the line row GA: each is target, in done (promoted
    earlier in the same run), or already GA. Cloud Promote then marks the pinned OSS line stabilized.
    """
    return all(
        u == target or u in done or row["targets"][u]["ga"] for u in row["enabled"]
    )


def reopens(row, targets):
    """Whether an RC for targets reopens the line row: one of them has no GA on it yet (on-prem enabled after cloud
    GA, say), so the line is no longer GA on every enabled target and its OSS line's STABILIZED tag goes.
    """
    return not all(row["targets"].get(t, {}).get("ga") for t in targets)


def promote_blockers(state, branch, target):
    """Older lines not GA for `target` yet, one refusal line each: Promote of `branch` for `target` waits for them.

    An older line blocks only where `target` is enabled on it and it has no GA for `target`; GA is the cloud
    promote retag or the on-prem chart push. A retired line is gone from the state, so it never blocks.
    Not applied to KEPT targets: each OSS line goes GA with its cloud line.
    """
    if target in KEPT:
        return []
    line = _key(branch.split("/", 1)[1])
    return [
        f"{b['branch']} is not GA for {target} yet: promote and publish it first, retire it, or force with a reason"
        for b in state["branches"]
        if _key(b["line"]) < line
        and target in b["targets"]
        and not b["targets"][target]["ga"]
    ]


def enable_blockers(state, branch, target):
    """Newer lines already GA for `target`, one refusal line each: `target` may not be enabled on `branch`.

    A target is enabled only on a line newer than every line already GA for it, so an older line can never
    wait to go GA behind a newer GA line whose patches the promote order would then hold. A target already
    enabled on `branch` is not affected (a patch RC on an old line still builds).
    """
    row = _branch_row(state, branch)
    if row and target in row["targets"]:
        return []
    line = _key(branch.split("/", 1)[1])
    return [
        f"{branch} is older than {b['branch']}, already GA for {target}: enable {target} on a newer line instead"
        for b in state["branches"]
        if _key(b["line"]) > line
        and target in b["targets"]
        and b["targets"][target]["ga"]
    ]


def summary(state):
    """Markdown table of derive()'s output for $GITHUB_STEP_SUMMARY; the JSON stays the machine input."""

    def cell(tt):
        if not tt:
            return "-"
        if tt["state"] == "stabilized":
            return f"stabilized (GA {tt['ga']['tag']})"
        if tt["state"] == "stabilizing" and tt["rcs"]:
            return f"stabilizing (rc.{VER_RE.fullmatch(tt['rcs'][-1])[4]})"
        return tt["state"]

    def slack(b):
        u = b.get("tip_rc_slack")
        return f" ([Slack]({u}))" if u else ""

    out = [
        f"| branch | state | {' | '.join(TARGETS)} | tip_rc | next_rc | ahead_of_ga |",
        "|---|---|" + "---|" * (len(TARGETS) + 3),
    ]
    out += [
        f"| {b['branch']} | {b['state']} | {' | '.join(cell(b['targets'].get(t)) for t in TARGETS)} "
        f"| {b['tip_rc'] or '-'}{slack(b)} | {b['next_rc'] or '-'} | {'-' if b['ahead_of_ga'] is None else b['ahead_of_ga']} |"
        for b in state["branches"]
    ]
    return (
        "\n".join(
            out
            + [
                "",
                "- supported: "
                + "; ".join(f"{t} {v}" for t, v in state["supported"].items()),
                f"- backport_targets.fix: {state['backport_targets']['fix']}",
                f"- retire: {state['retire']}",
                f"- next_minor: {state['next_minor']}",
                f"- anomalies: {len(state['anomalies'])}",
            ]
        )
        + "\n"
    )


def main(argv=None, registry=registry_tags):
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--repo", default=".")
    p.add_argument("--now", type=_ts, default=None, help="ISO-8601 UTC; default: now")
    p.add_argument(
        "--rc",
        type=rm.option_free,
        help="also report the stable tag promoting this RC would get",
    )
    a = p.parse_args(argv)
    try:
        state = derive(a.repo, a.now or dt.datetime.now(dt.UTC), registry, a.rc)
    except Exception as e:  # never print a silently empty state
        traceback.print_exc()
        print(f"relstate: {e}", file=sys.stderr)
        return 1
    print(json.dumps(state, indent=2))
    if os.environ.get("GITHUB_OUTPUT"):
        with open(os.environ["GITHUB_OUTPUT"], "a") as f:
            f.write(f"state={json.dumps(state, separators=(',', ':'))}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
