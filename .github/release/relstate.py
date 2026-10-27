"""Branch and target state for the V2 release workflows, derived from git + the target registries.

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

# On-prem support window from the line's latest stable chart push, so each patch restarts it.
WINDOW = dt.timedelta(days=184)  # 184 days covers the longest 6-month span
WINDOW_LINES = (
    6  # and only the newest 6 on-prem GA lines are supported, whichever ends first
)
# Per repo, so both repos run this same file: (targets, targets where only the latest GA line is supported,
# targets supported while the branch exists: retired only when another repo's Retire names the line, repo whose
# tags this repo's lines pin in pyproject.toml or None, tag prefix of this repo's lines).
# Artifacts are <kind>/<package> in Artifact Registry; RELSTATE_AR_<KIND> names the repository (ar_repository).
# TARGETS: target -> (artifact holding RC / promoted builds, GA anchor artifact). Cloud GA = the vX.Y.Z retag
# of the build artifact; on-prem GA = the chart push. GIT instead of an artifact: the line's own git tags, the stable
# tag's date as the GA date (OSS lines: cloud builds them from source, so they have no artifact).
# OSS lines are tagged ee-vX.Y.Z(-rc.N); plain vX.Y.Z tags there are community releases from main, never a line's.
GIT = "git"
REPOS = {
    # Cloud: each target's build artifact is backend, since every build pushes it (all services share one tag).
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


def taken_tags(reg=None, registry=registry_tags):
    """Every tag on every registry artifact of TARGETS: an RC there is never allocated again (rc_version taken).
    reg: {artifact: tags} already read; artifacts missing from it are read.
    """
    reg = reg or {}
    return {
        t
        for a in sorted({a for pair in TARGETS.values() for a in pair} - {GIT})
        for t in (reg[a] if a in reg else registry(a))
    }


def _ts(s):
    return dt.datetime.fromisoformat(s.replace("Z", "+00:00"))


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
    r = rm.git(
        repo, "rev-parse", "-q", "--verify", f"refs/tags/{tag}^{{commit}}", check=False
    )
    return r.stdout.strip() if r.returncode == 0 else None


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
    """State of target t on an enabled branch. The one place the GA/supported convention lives.

    On-prem: stabilized for WINDOW after the line's latest stable chart push (a patch restarts it), and only while
    among the newest WINDOW_LINES lines with an on-prem GA. A LATEST_ONLY target (cloud): only the latest GA branch
    for it stays stabilized; older GA branches are past-eos for it. A KEPT target (OSS): stabilized from its GA
    while the branch exists; the cloud lines pinning it decide its retirement, and cloud Retire names it.
    """
    ga = rows[name]["targets"][t]["ga"]
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
    """One minor past the highest release/X.Y line, shipped retired line or stable vX.Y.Z on main, so a cut never
    reuses a minor shipped by this flow. A line retired early before any GA (retired/X.Y-<sha7>, its RCs deleted) is
    reused.

    With no release/X.Y branch yet (cutover) only the tags count. A stable tag that is not on main does not count
    (that keeps strays such as v100.0.x out), so an old-flow release not yet merged back can be proposed again:
    check the proposal against `git tag -l` before the first cut.
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


def derive(repo, now, registry=registry_tags, rc=None):
    t0 = time.monotonic()
    reg = {
        a: git_tags(repo) if a == GIT else registry(a)
        for a in sorted({a for pair in TARGETS.values() for a in pair})
    }
    print(
        f"relstate: registry read {len(reg)} artifacts in {time.monotonic() - t0:.2f}s",
        file=sys.stderr,
    )  # registry read cost
    refs = _branches(repo)
    rows, anomalies = {}, []
    taken = taken_tags(reg)
    for name, ref in refs.items():
        tip = rm.rc_version(
            repo, ref, PREFIX, taken
        )  # the tip's RC tag if built (one RC per commit), else the next one
        built = tip in rm.git(repo, "tag", "--points-at", ref).split()
        rows[name] = {
            "branch": name,
            "line": name.split("/", 1)[1],
            "state": None,
            "enabled": [],
            "next_rc": None if built else tip,
            "tip_rc": tip if built else None,
            "ahead_of_ga": ahead_of_ga(repo, ref, name.split("/", 1)[1]),
            "targets": {},
        }
        if built and (url := rc_slack(repo, tip)):  # only when the RC has a link
            rows[name]["tip_rc_slack"] = url
    # A line with no branch but a git stable tag was promoted and then retired: its registry tags are
    # history, not anomalies, and are skipped before any per-tag git call. A line that never
    # promoted (RC-only) stays an anomaly. Retire only lists lines that were GA, so this is exact.
    shipped = {}

    # enabled: a build tag of T whose git commit is on the branch (derived, never recorded).
    for t, (builds, anchor) in TARGETS.items():
        for tag in sorted(reg[builds]):
            m = VER_RE.fullmatch(tag)
            if not m:
                continue  # not a release version (e.g. smoke tags)
            name = f"release/{m[1]}.{m[2]}"
            if name not in refs:
                if name not in shipped:  # one git tag read per line, not per registry tag
                    shipped[name] = bool(rm._tags(repo, m[1], m[2], PREFIX)[0])
                if shipped[name]:
                    continue
            sha = _tag_commit(repo, tag)
            if name not in refs or not sha or not rm.is_ancestor(repo, sha, refs[name]):
                why = (
                    "no branch"
                    if name not in refs
                    else "no git tag"
                    if not sha
                    else "commit not on branch"
                )
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
        for name, row in rows.items():
            tt = row["targets"].get(t)
            if not tt:
                continue
            tt["rcs"].sort(key=_vkey)
            # On-prem GA reads the chart artifact: RC chart pushes are tagged 0.0.0-rc.N and match no line; the
            # stable chart push is tagged vX.Y.Z (push-charts-to-gcr.yaml checks it against the release tag).
            stable = re.compile(rf"{re.escape(PREFIX)}v{re.escape(row['line'])}\.\d+")
            # ga anchors state and the support window; promoted (the build artifact's latest stable) is what ships next
            for key, artifact in (("ga", anchor), ("promoted", builds)):
                if tags := sorted(
                    (g for g in reg[artifact] if stable.fullmatch(g)), key=_vkey
                ):
                    tt[key] = {"tag": tags[-1], **reg[artifact][tags[-1]]}

    for name, row in rows.items():
        for t, tt in row["targets"].items():
            tt["state"] = target_state(t, name, rows, now)
        row["enabled"] = sorted(row["targets"])
        states = {tt["state"] for tt in row["targets"].values()}
        # No enabled target (cut, nothing built yet) is stabilizing: every line builds cloud by default.
        row["state"] = (
            "stabilizing"
            if not states or "stabilizing" in states
            else "stabilized"
            if "stabilized" in states
            else "past-eos"
        )

    ordered = sorted(rows.values(), key=lambda r: _key(r["line"]), reverse=True)
    out = {
        "now": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "branches": ordered,
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
    row = next((b for b in state["branches"] if b["branch"] == branch), None)
    if not row:
        return "no such branch"
    held = [t for t, tt in sorted(row["targets"].items()) if tt["state"] == "stabilized"]
    if "cloud" in held:
        return "cloud is production (newest cloud GA); it retires once a newer line is promoted"
    if held and not force:
        return f"{', '.join(held)} still supported (stabilized); force to retire it inside the window"
    return None


def abandon_plan(repo, branch, registry=registry_tags):
    """What Retire `abandon` deletes for an existing release/X.Y line that never shipped (cut by mistake, or built only as RCs).

    {"ga": [...], "used": [...], "rc_tags": [...], "versions": {artifact: [{id, digest, tags}]}, "kept": [...]}.
    A non-empty ga (git stable tag or GA-anchor registry tag) or used (commits that are not bot, pick or
    decline) refuses the abandon. A registry version is deleted only when every tag on it is an RC of
    this line. An artifact's last tagged version is kept and listed, so an abandon never empties an artifact.
    """
    x, y = rm._line(branch)
    rc_re = re.compile(rf"{re.escape(PREFIX)}v{x}\.{y}\.\d+-rc\.\d+")
    reg = {
        a: registry(a)
        for a in sorted({a for pair in TARGETS.values() for a in pair} - {GIT})
    }
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
    versions, kept = {}, []
    for a, tags in reg.items():
        by_digest = {}
        for t, info in sorted(tags.items()):
            by_digest.setdefault(
                info["digest"],
                {"id": info.get("id"), "digest": info["digest"], "tags": []},
            )["tags"].append(t)
        drop = [
            v for v in by_digest.values() if all(rc_re.fullmatch(t) for t in v["tags"])
        ]
        # ponytail: untagged versions are invisible here, so "last" is counted over tagged ones (conservative).
        if drop and len(drop) == len(by_digest):
            kept.append(f"{a}:{','.join(drop[-1]['tags'])}")
            drop = drop[:-1]
        if drop:
            versions[a] = drop
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
    """Older lines not GA for `target` yet, one refusal line each: Promote of `branch` for `target` waits for them.

    An older line blocks only where `target` is enabled on it and it has no GA for `target`; GA is the cloud
    promote retag or the on-prem chart push. A retired line is gone from the state, so it never blocks.
    """
    # Not applied to a KEPT target (OSS). The order protects customers who stay on a line and upgrade later
    # (on-prem windows). OSS community users run only :latest, which moves only on the newest line, so an older
    # line shipping after a newer one reaches nobody. Each OSS line goes GA with its cloud line, so the order
    # would hold a community release on the newest line until the previous cloud line is GA.
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
    row = next((b for b in state["branches"] if b["branch"] == branch), None)
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

    out = [
        f"| branch | state | {' | '.join(TARGETS)} | tip_rc | next_rc | ahead_of_ga |",
        "|---|---|" + "---|" * (len(TARGETS) + 3),
    ]
    out += [
        f"| {b['branch']} | {b['state']} | {' | '.join(cell(b['targets'].get(t)) for t in TARGETS)} "
        f"| {b['tip_rc'] or '-'}{f' ([Slack]({u}))' if (u := b.get('tip_rc_slack')) else ''} | {b['next_rc'] or '-'} | {'-' if b['ahead_of_ga'] is None else b['ahead_of_ga']} |"
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
    p.add_argument("--rc", help="also report the stable tag promoting this RC would get")
    a = p.parse_args(argv)
    try:
        state = derive(a.repo, a.now or dt.datetime.now(dt.UTC), registry, a.rc)
    except (
        Exception
    ) as e:  # registry or git failure: no JSON, never a silently empty state
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
