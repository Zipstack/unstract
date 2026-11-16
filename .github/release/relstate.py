"""Branch and target state for the release-branch workflows, derived from git and the target registries.

Usage: relstate.py [--repo DIR] [--now 2026-09-29T00:00:00Z] [--rc vX.Y.Z-rc.N]

Prints one JSON document. Nothing is stored: state is re-derived on every run.
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

# On-prem support window, from the line's first stable chart push.
WINDOW = dt.timedelta(days=184)
WINDOW_LINES = 6
# Per repo, so both repos run this file. Entry: (TARGETS, LATEST_ONLY: only the latest GA line is supported,
# KEPT: supported while the branch exists, PINS: repo whose tags pyproject.toml pins, PREFIX: tag prefix).
# TARGETS: target -> (build artifact, GA anchor artifact), each <kind>/<package>; GIT: the line's own git tags stand
# in for an artifact (OSS lines).
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
    global SLUG, TARGETS, LATEST_ONLY, KEPT, PINS, PREFIX, VER_RE
    if slug not in REPOS:
        raise RuntimeError(
            f"relstate has no config for repo {slug!r}; known: {', '.join(REPOS)}"
        )
    SLUG = slug
    TARGETS, LATEST_ONLY, KEPT, PINS, PREFIX = REPOS[slug]
    VER_RE = ver_re(PREFIX)


use(SLUG)

# The images Retag gives a promoted version, in the build kind of each target (retag-docker-images.yaml's matrix).
IMAGES = (
    "backend",
    "frontend",
    "platform-service",
    "runner",
    "x2text-service",
    "tool-sidecar",
    "worker-unified",
)


def missing_images(target, tag):
    """The images of a target that lack tag: Promote needs the RC on each, Publish the stable version."""
    kind = TARGETS[target][0].split("/")[0]
    return [a for a in (f"{kind}/{i}" for i in IMAGES) if tag not in registry_tags(a)]


AR_API = "https://artifactregistry.googleapis.com/v1"


def ar_repository(kind):
    """The calling workflow sets RELSTATE_AR_<KIND>, so no registry location lives in this file."""
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


def ar_repositories(kind):
    """Stable repository, then the _RC one when set and different. Both are read because Retag promotes an RC into
    the stable repository, which then holds the GA tag.
    """
    stable = ar_repository(kind)
    rc = os.environ.get("RELSTATE_AR_" + kind.upper().replace("-", "_") + "_RC")
    return [stable, *([rc] if rc and rc != stable else [])]


def _ar_versions(repo, package, artifact):
    """Every version of package in repo with its tags, or None when its first page answers 404."""
    url = f"{AR_API}/{repo}/packages/{urllib.parse.quote(package, safe='')}/versions"
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


def _ar_packages(repo):
    """Every package name in repo. Raises on any read failure, a missing repository included."""
    out, page = [], ""
    while True:
        q = {"pageSize": 1000, **({"pageToken": page} if page else {})}
        body = _ar_get(f"{AR_API}/{repo}/packages?{urllib.parse.urlencode(q)}", repo)
        if body is None:
            raise RuntimeError(f"registry read {repo}: HTTP 404")
        out += [
            urllib.parse.unquote(p["name"].rsplit("/packages/", 1)[1])
            for p in body.get("packages", [])
        ]
        if not (page := body.get("nextPageToken")):
            return out


def rc_service_tags():
    """{<kind>/<package>: tags} of every non-TARGETS package in the RC repositories. Take RC pushes every service
    there, and an RC tag left on one collides with the next cut of the same minor, so abandon deletes them all.
    """
    own, out = _artifacts(), {}
    for kind in sorted({a.split("/", 1)[0] for a in own}):
        for rc in ar_repositories(kind)[1:]:
            for package in _ar_packages(rc):
                if (a := f"{kind}/{package}") not in own:
                    out[a] = registry_tags(a, [rc])
    return out


def registry_tags(artifact, repos=None):
    """{tag: {id, digest, pushed_at}} for one artifact (<kind>/<package>), over every repository of its kind or repos.

    A 404 means "not pushed yet" only when the repository itself reads; otherwise it may be a wrong
    RELSTATE_AR_<KIND>, and an empty registry would read as "nothing enabled". A tag at two digests raises: which
    copy was tested is for a person to decide, not a guess.
    """
    kind, package = artifact.split("/", 1)
    out = {}
    for repo in repos or ar_repositories(kind):
        versions = _ar_versions(repo, package, artifact)
        if versions is None:
            if _ar_get(f"{AR_API}/{repo}", artifact) is None:
                raise RuntimeError(
                    f"registry read {artifact}: 404 and repository {repo} not found"
                )
            continue
        for v in versions:
            pushed = re.sub(
                r"\.\d+(?=Z$)", "", v["createTime"]
            )  # AR returns up to 9 fraction digits
            for t in v.get("relatedTags") or []:
                tag = t["name"].rsplit("/tags/", 1)[1]
                info = {
                    "id": v["name"],
                    "digest": v["name"].rsplit("/versions/", 1)[1],
                    "pushed_at": pushed,
                }
                if tag in out and out[tag]["digest"] != info["digest"]:
                    raise RuntimeError(
                        f"registry read {artifact}: tag {tag} is {out[tag]['id']} (pushed {out[tag]['pushed_at']})"
                        f" and {info['id']} (pushed {pushed}); Retag promotes the RC repository's copy. Check"
                        " which one was tested, delete the other (Artifact Registry console) and rerun"
                    )
                out.setdefault(tag, info)
    return out


def _read(artifact, registry):
    """registry(artifact), with chart tags X.Y.Z read as vX.Y.Z (some charts were pushed without the v)."""
    tags = registry(artifact)
    if not artifact.startswith("chart/"):
        return tags
    return {
        ("v" + t if re.fullmatch(r"\d+\.\d+\.\d+", t) else t): info
        for t, info in tags.items()
    }


def taken_tags(reg=None, registry=registry_tags):
    """An RC tagged on any TARGETS artifact is never allocated again."""
    reg = reg or {}
    return {t for a in _artifacts() for t in (reg[a] if a in reg else registry(a))}


RC_CHART = "on-prem/unstract-platform"


def rc_chart_tags(registry=registry_tags):
    """The on-prem RC chart's versions, as vX.Y.Z-rc.N. Abandon can keep the chart's last version, so an RC number
    it holds is never allocated again: the chart push would otherwise find that old chart and keep it.
    """
    if "on-prem" not in TARGETS:
        return set()
    # Some RC charts were pushed without the v.
    return {
        "v" + t.removeprefix("v")
        for t in registry(RC_CHART)
        if re.fullmatch(r"v?\d+\.\d+\.\d+-rc\.\d+", t)
    }


def used_tags(repo, line, registry=registry_tags):
    """Cut refuses a line with these: its tags would read as the new line's builds or GA.
    Registry RCs do not count: an abandon keeps a package's last one, and a re-cut skips it.
    """
    ver = re.compile(rf"{re.escape(PREFIX)}v{re.escape(line)}\.\d+")
    tags = set(line_tags(repo, line)) | {
        t for a in _artifacts() for t in _read(a, registry) if ver.fullmatch(t)
    }
    return sorted(tags, key=_vkey)


def _artifacts(git=False):
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
    prefix = PREFIX if prefix is None else prefix
    ver = ver_re(prefix)
    return [
        t
        for t in rm.git(repo, "tag", *args, "-l", f"{prefix}v{line}.*").split()
        if (m := ver.fullmatch(t)) and f"{m[1]}.{m[2]}" == line
    ]


def older_newer(a, b):
    return tuple(sorted((a, b), key=lambda n: _key(n.split("/", 1)[1])))


def moved_archive(repo, line, sha):
    """An earlier archive tag on an ancestor of sha: the line moved after archiving, so a second tag would split its
    record. A tag off sha's history (an earlier line of a reused minor) is not one.
    """
    for t in rm.git(repo, "tag", "-l", f"retired/{line}-*").split():
        if t != f"retired/{line}-{sha[:7]}" and rm.is_ancestor(
            repo, _tag_commit(repo, t), sha
        ):
            return t
    return None


def git_tags(repo):
    """The GIT stand-in for a registry artifact."""
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
    for it stays stabilized; older GA branches are past-eos for it. A KEPT target (OSS): stabilized from its GA
    (the paired cloud line's first Promote, of either product, tags it) while the branch exists; the cloud lines pinning it
    decide its retirement, and cloud Retire names it.
    """
    ga = rows[name]["targets"][t]["ga"]
    # Known limit: a target never GA stays stabilizing. Its line goes by Retire one shipped line now (force when the
    # target is late; not while its cloud is production), or by Abandon when no target has a GA.
    if not ga:
        return "stabilizing"
    if t in KEPT:
        return "stabilized"
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
    if built and (url := rc_slack(repo, tip)):
        row["tip_rc_slack"] = url
    return row


def _anomaly_reason(repo, name, refs, sha):
    if name not in refs:
        return "no branch"
    if not sha:
        return "no git tag"
    if not rm.is_ancestor(repo, rm.rc_commit(repo, sha, PREFIX), refs[name]):
        return "commit not on branch"
    return None


def _shipped(repo, name, m, shipped):
    if name not in shipped:  # one git tag read per line, not per registry tag
        shipped[name] = bool(rm._tags(repo, m[1], m[2], PREFIX)[0])
    return shipped[name]


def _enable(repo, t, builds, reg, refs, rows, shipped, anomalies):
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


def _fill_ga(repo, t, builds, anchor, reg, refs, rows):
    for row in rows.values():
        tt = row["targets"].get(t)
        if not tt:
            continue
        tt["rcs"].sort(key=_vkey)
        # ga: the anchor's first stable (state, window). promoted: the build artifact's latest stable (ships next).
        stable = re.compile(rf"{re.escape(PREFIX)}v{re.escape(row['line'])}\.\d+")
        for key, artifact, pick in (("ga", anchor, 0), ("promoted", builds, -1)):
            if tags := sorted(
                (
                    g
                    for g in reg[artifact]
                    if stable.fullmatch(g)
                    and (c := _tag_commit(repo, g))
                    and rm.is_ancestor(
                        repo, rm.rc_commit(repo, c, PREFIX), refs[row["branch"]]
                    )
                ),
                key=_vkey,
            ):
                tt[key] = {"tag": tags[pick], **reg[artifact][tags[pick]]}


def _line_state(states):
    if not states or "stabilizing" in states:
        return "stabilizing"
    if "stabilized" in states:
        return "stabilized"
    return "past-eos"


def _ga_time(repo, ga):
    """When ga was promoted. The registry time alone is the RC's push when the RC and stable repositories are one, so
    the later of it and Promote's annotated tag (a lightweight tag has no tagger date) counts.
    """
    tagged = rm.git(
        repo,
        "for-each-ref",
        "--format=%(taggerdate:iso-strict)",
        f"refs/tags/{ga['tag']}",
    )
    return max([_ts(ga["pushed_at"]), *([_ts(tagged)] if tagged else [])])


def _late(repo, row, t, reg):
    """Whether t's first RC on the line came after another target's GA there (on-prem enabled after cloud GA)."""
    rcs = row["targets"][t]["rcs"]
    # t's own GA follows its RCs, so every GA on the line counts.
    gas = [_ga_time(repo, u["ga"]) for u in row["targets"].values() if u["ga"]]
    # Push times, not git tags: a late target may build the tip's RC tag, made before that GA.
    return bool(rcs and gas) and _ts(reg[TARGETS[t][0]][rcs[0]]["pushed_at"]) > min(gas)


def _set_states(rows, now):
    for name, row in rows.items():
        for t, tt in row["targets"].items():
            tt["state"] = target_state(t, name, rows, now)
        row["enabled"] = sorted(row["targets"])
        # No enabled target (cut, nothing built yet) is stabilizing: every line builds cloud by default.
        # The line's first GA, for any target, ends its auto-picks: a target with no GA yet then counts as stabilized,
        # so it takes backport/rc fixes only by a named Backport. Its own state stays stabilizing: it keeps its target
        # supported and blocks that target's Promote on newer lines; Retire needs force for it only when it is late.
        any_ga = any(tt["ga"] for tt in row["targets"].values())
        row["state"] = _line_state(
            {
                "stabilized" if any_ga and not tt["ga"] else tt["state"]
                for tt in row["targets"].values()
            }
        )


def _sets(ordered):
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
            "rc": [r["branch"] for r in ordered if r["state"] == "stabilizing"],
            "ga": [
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
    taken = taken_tags(reg) | rc_chart_tags(registry)
    rows = {name: _row(repo, name, ref, taken) for name, ref in refs.items()}
    # A branchless line with a stable tag was retired after GA: its registry tags are history, not anomalies.
    shipped = {}

    # enabled: a build tag of T whose git commit is on the branch (derived, never recorded).
    for t, (builds, anchor) in TARGETS.items():
        _enable(repo, t, builds, reg, refs, rows, shipped, anomalies)
        _fill_ga(repo, t, builds, anchor, reg, refs, rows)
    for row in rows.values():
        for t, tt in row["targets"].items():
            tt["late"] = _late(repo, row, t, reg)

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
    """Why Retire one shipped line now refuses branch, or None. A stabilizing target (RCs, no GA: an on-prem line never
    promoted, say) may go. A stabilized on-prem target (chart in its window), or a late target with no GA, goes only
    with force. Stabilized cloud is production and never goes: relstate would make the next older cloud GA production
    again.
    """
    row = _branch_row(state, branch)
    if not row:
        return "no such branch"
    held = retire_line_held(state, branch)
    if row["targets"].get("cloud", {}).get("state") == "stabilized":
        return "cloud is production (newest cloud GA); it retires once a newer line is promoted"
    if held and not force:
        return f"{', '.join(held)} still supported (stabilized, or late with no GA yet); to retire it inside the window, rerun with force"
    return None


def retire_line_held(state, branch):
    """Targets that keep branch supported: stabilized, or late with no GA."""
    return [
        t
        for t, tt in sorted(_branch_row(state, branch)["targets"].items())
        if tt["state"] == "stabilized" or (tt["late"] and not tt["ga"])
    ]


def _branch_row(state, branch):
    return next((b for b in state["branches"] if b["branch"] == branch), None)


def _repo_of(version):
    return (version["id"] or "").split("/packages/", 1)[0]


def _by_version(tags):
    """{id or digest: {id, digest, tags}}: one digest in two repositories is two versions."""
    by_version = {}

    # Version order, so the last version is the newest RC (rc.10 after rc.9); other tags first. Some chart versions
    # carry no "v".
    def key(kv):
        t = kv[0] if VER_RE.fullmatch(kv[0]) else f"{PREFIX}v{kv[0]}"
        return (_vkey(t) if VER_RE.fullmatch(t) else (-1, -1), kv[0])

    for t, info in sorted(tags.items(), key=key):
        by_version.setdefault(
            info.get("id") or info["digest"],
            {"id": info.get("id"), "digest": info["digest"], "tags": []},
        )["tags"].append(t)
    return by_version


def _abandon_versions(reg, rc_re):
    """Per repository, when every tagged version would go, the last is kept, so no package is emptied.
    Known limits: untagged versions are not listed, so "last" counts tagged ones only; one tag at one digest in
    both repositories reads as the stable copy only, so the RC repository's copy is not deleted.
    """
    versions, kept = {}, []
    for a, tags in reg.items():
        by_version, drop = _by_version(tags), []
        for where in sorted({_repo_of(v) for v in by_version.values()}):
            mine = [v for v in by_version.values() if _repo_of(v) == where]
            d = [v for v in mine if all(rc_re.fullmatch(t) for t in v["tags"])]
            if d and len(d) == len(mine):
                kept.append(f"{a}:{','.join(d[-1]['tags'])}")
                d = d[:-1]
            drop += d
        if drop:
            versions[a] = drop
    return versions, kept


def abandon_plan(repo, branch, registry=registry_tags, services=rc_service_tags):
    """What Abandon a line that never shipped deletes for release/X.Y (cut by mistake, or built only as RCs).

    {"ga": [...], "used": [...], "rc_tags": [...], "versions": {artifact: [{id, digest, tags}]}, "kept": [...]}.
    A non-empty ga refuses the abandon. used (commits that are not bot, pick or decline) are listed; the archive tag
    keeps them. A registry version is deleted only when every tag on it is an RC of this line.
    """
    x, y = rm._line(branch)
    # The on-prem RC chart's versions have no "v".
    rc_re = re.compile(rf"(?:{re.escape(PREFIX)}v)?{x}\.{y}\.\d+-rc\.\d+")
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
    versions, kept = _abandon_versions({**reg, **services()}, rc_re)
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


def promote_blockers(state, branch, target):
    """Older lines not GA for `target` yet: Promote of `branch` waits for them.

    Not applied to KEPT targets: each OSS line goes GA with its cloud line.
    """
    if target in KEPT:
        return []
    line = _key(branch.split("/", 1)[1])
    return [
        f"{b['branch']} is not GA for {target} yet: promote and publish it first, or retire it (Retire one shipped line now; Abandon a line that never shipped when it has no GA); to override, rerun with force and a reason"
        for b in state["branches"]
        if _key(b["line"]) < line
        and target in b["targets"]
        and not b["targets"][target]["ga"]
    ]


def enable_blockers(state, branch, target):
    """Newer lines already GA for `target`. Enabling only past every GA line keeps an older line from waiting to go
    GA behind a newer GA line whose patches the promote order would then hold.
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
            return f"stabilized (GA {rm.tag_link(tt['ga']['tag'])})"
        if tt["state"] == "stabilizing" and tt["rcs"]:
            return f"stabilizing (rc.{VER_RE.fullmatch(tt['rcs'][-1])[4]}{', late' * tt['late']})"
        return tt["state"]

    def slack(b):
        u = b.get("tip_rc_slack")
        return f" ([Slack]({u}))" if u else ""

    out = [
        f"| branch | state | {' | '.join(TARGETS)} | tip_rc | next_rc | ahead_of_ga |",
        "|---|---|" + "---|" * (len(TARGETS) + 3),
    ]
    out += [
        f"| {rm.branch_link(b['branch'])} | {b['state']} | {' | '.join(cell(b['targets'].get(t)) for t in TARGETS)} "
        f"| {rm.tag_link(b['tip_rc']) if b['tip_rc'] else '-'}{slack(b)} | {b['next_rc'] or '-'} | {'-' if b['ahead_of_ga'] is None else b['ahead_of_ga']} |"
        for b in state["branches"]
    ]
    return (
        "\n".join(
            out
            + [
                "",
                "- supported: "
                + "; ".join(f"{t} {v}" for t, v in state["supported"].items()),
                f"- backport_targets.rc: {state['backport_targets']['rc']}",
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
