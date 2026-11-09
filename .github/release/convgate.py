"""Convergence gate: scan every other supported branch of a target, both directions, so an older branch
never ships a fix a newer one lacks.

- A newer line with a promoted stable tag for T is scanned at that tag (what ships next), not its tip. The branch
  being promoted is scanned at --promote-ref as the newer side, at its tip as the older side, so a fix picked after
  the RC still blocks.
- A decline on the newer line counts as converged; one on the older line owes the newer line nothing.
- RBO-ABSENT counts only after the newer line's latest promoted tag (else its cut), outside .github/.
Exit 2 iff any MISSING, 1 on error or bad usage (never a silent pass), else 0. Promote order (an older line not GA
yet) is listed, not counted: Promote enforces it, and Take RC builds of a newer line while an older one stabilizes.
"""

import argparse
import datetime as dt
import functools
import json
import os
import re
import sys
import traceback

import backport_merge as bm
import oss
import relmgr as rm
import relstate as rs

STATUSES = ("CONVERGED", "DECLINED", "MISSING", "UNCLASSIFIABLE", "RBO-ABSENT")
CLOSE_HOWTO = "resolve, get one approval and merge, or close the PR to decline (the close comment is the reason)."


def conflict_pr(head, slug=None):
    r = bm.run_gh(
        [
            "pr",
            "list",
            "-R",
            slug or os.environ["GITHUB_REPOSITORY"],
            "--head",
            head,
            "--state",
            "open",
            "--json",
            "number,url",
        ],
    )
    if r.returncode:  # never report "no PR found" when the lookup itself failed
        raise RuntimeError(f"gh pr list --head {head}: {r.stderr.strip()}")
    prs = json.loads(r.stdout or "[]")
    return (prs[0]["number"], prs[0]["url"]) if prs else None


def push_failure(number, branch, slug=None):
    r = bm.run_gh(
        [
            "api",
            "--paginate",
            f"repos/{slug or os.environ['GITHUB_REPOSITORY']}/issues/{number}/comments",
            "--jq",
            f'.[] | .body | split("\\n")[0] | select(startswith("Backport to {branch} failed:"))',
        ],
    )
    if r.returncode:  # never read a failed lookup as "no failure comment"
        raise RuntimeError(f"gh api issues/{number}/comments: {r.stderr.strip()}")
    m = re.search(r"\(run (\S+)\)", (r.stdout.strip().splitlines() or [""])[-1])
    return m and m[1]


def blocked(branch, target, annotate):
    return (
        f"Cannot promote {branch} for {target}"
        if annotate == "error"
        else f"Promote of {branch} for {target} will be blocked"
    )


def missing_message(
    repo, branch, target, older, newer, orig, pr, annotate, unshipped=None, failure=None
):
    """unshipped: the tag `newer` is scanned at, when the fix is on `newer`'s tip but not in that tag."""
    o7 = orig[:7]
    # orig may not be on main.
    n = rm.subject_pr(repo, orig, check=False)
    fix = f"fix {o7}" + (f" (PR #{n})" if n is not None else "")
    head = blocked(branch, target, annotate)
    # An RC of this line, cut before the fix.
    if unshipped and newer == branch and rs.VER_RE.fullmatch(unshipped)[4]:
        return f"{head}: {fix} is on {newer} but not in RC {unshipped}: take a new RC build first."
    if unshipped:
        return f"{head}: {fix} is on {newer} but not in its latest stable {unshipped}: promote a {newer} patch first."
    if branch == older:
        msg = (
            f"{head}: {fix} is not on newer {newer} yet; an older line never ships a fix its newer line lacks, "
            "even one picked after the RC being promoted."
        )
        act = f"Conflict PR #{pr[0]} on {newer}: {CLOSE_HOWTO}" if pr else None
    else:
        msg = f"{head}: {fix} is on older {older} but not on this line."
        act = f"Conflict PR #{pr[0]} is on this branch: {CLOSE_HOWTO}" if pr else None
    # The failure comment comes from backport.push_head.
    if not act and n is not None and failure and (url := failure(n, newer)):
        act = f"Backport for {o7} to {newer} failed: push rejected (run {url}). Rerun Backport for {o7} on {newer}."
    return f"{msg} {act or f'No Backport PR found for it: run Backport for {o7}, or decline it on {newer}.'}"


def _oss_pins_of(repo, oss_repo, names, ref):
    pins = {n: oss.pin(repo, ref(n)) for n in names}
    for p in set(pins.values()):
        if not rs._tag_commit(oss_repo, p):
            raise RuntimeError(f"no OSS tag {p} in {oss_repo}")
    return pins


def _oss_found(oss_repo, main, oss_refs, p_old, p_new, line_new):
    if p_old == p_new:
        return []
    return [
        r
        for r in rm.convergence_report(
            oss_repo,
            f"refs/tags/{p_old}",
            f"refs/tags/{p_new}",
            main=main,
            newer_branch=oss_refs.get(line_new),
        )
        if r[1] in ("CONVERGED", "MISSING")
    ]


def _oss_act(oss_repo, main, oss_refs, o, newer, line_new):
    n = rm.subject_pr(oss_repo, o)
    fix = f"OSS fix {o[:7]}" + (f" (OSS PR #{n})" if n is not None else "")
    on_line = line_new in oss_refs and rm.is_converged(
        oss_repo, o, oss_refs[line_new], main
    )
    act = (
        f"take a new RC of {newer} to pin OSS {line_new}'s tip"
        if on_line
        else f"pick it onto OSS {line_new} (OSS Backport), then take a new RC of {newer}"
    )
    return fix, act


def oss_pins(repo, oss_repo, branch, target, scope, ref, rows, annotate):
    """Each older line's pinned OSS tag scanned into the newer line's, so an upgrade never loses an OSS fix."""
    main, oss_refs = "refs/remotes/origin/main", rs._branches(oss_repo)
    pins = _oss_pins_of(repo, oss_repo, [branch, *scope], ref)
    head = blocked(branch, target, annotate)
    missing, lines, out = (
        0,
        [],
        [
            f"### OSS pins: {rm.branch_link(branch)} pins {rm.tag_link(pins[branch], oss.OSS)}",
            "",
        ],
    )
    for s in scope:
        older, newer = rs.older_newer(s, branch)
        p_old, p_new, line_new = pins[older], pins[newer], oss.line_of(pins[newer])
        found = _oss_found(oss_repo, main, oss_refs, p_old, p_new, line_new)
        n_miss = sum(st == "MISSING" for _, st in found)
        missing += n_miss
        summary = f"{len(found)} OSS picks, {len(found) - n_miss} in {p_new}" + (
            f", {n_miss} missing" if n_miss else ""
        )
        state_s = rows[s]["targets"].get(target, {}).get("state")
        line = _line_result(s, older, len(found), summary, state_s, oss=True)
        lines.append(line)
        out.append(
            f"**{rm.branch_link(s)}** ({line['side']}; {rm.branch_link(older)} pins {rm.tag_link(p_old, oss.OSS)}, "
            f"{rm.branch_link(newer)} pins {rm.tag_link(p_new, oss.OSS)}): {summary}"
        )
        for c, st in found:
            if st != "MISSING":
                continue
            for o in rm.picked_from(oss_repo, c):
                fix, act = _oss_act(oss_repo, main, oss_refs, o, newer, line_new)
                msg = f"{head}: {fix} is in {older}'s OSS pin {p_old} but not in {newer}'s pin {p_new}: {act}."
                print(f"::{annotate}::{msg}")
                out.append(
                    f"- {rm.commit_link(c, 12, oss.OSS)} MISSING original {rm.commit_link(o, 12, oss.OSS)}"
                )
                out.append(f"  - {msg}")
                line["todo"].append(act)
        out.append("")
    return missing, out, lines


def _line_result(s, older, picks, summary, state, oss=False):
    return {
        "line": s,
        "side": "older" if s == older else "newer",
        "picks": picks,
        "summary": summary,
        "todo": [],
        "rbo": [],
        "state": state,
        **({"oss": True} if oss else {}),
    }


def _tag_ref(repo, tag):
    if not rs._tag_commit(repo, tag):
        raise RuntimeError(f"no git tag {tag}")
    return f"refs/tags/{tag}"


def _ref(repo, refs, rows, branch, target, promote_ref, name):
    if name == branch and promote_ref:
        return _tag_ref(repo, promote_ref)
    p = rows[name]["targets"].get(target, {}).get("promoted")
    return _tag_ref(repo, p["tag"]) if p else refs[name]


def _since(repo, main, newer_tip, promoted):
    if promoted:
        return int(
            rm.git(
                repo,
                "for-each-ref",
                "--format=%(creatordate:unix)",
                f"refs/tags/{promoted['tag']}",
            )
        )
    return int(
        rm.git(
            repo,
            "log",
            "-1",
            "--format=%ct",
            rm.git(repo, "merge-base", main, newer_tip),
        )
    )


def _in_window(repo, c, since):
    return int(rm.git(repo, "log", "-1", "--format=%ct", c)) > since and any(
        not f.startswith(".github/")
        for f in rm.git(repo, "show", "--format=", "--name-only", c).split()
    )


def _scan(repo, main, refs, ref, older, newer, since):
    rows_out, n_picks = [], 0
    recs = rm.decline_records(repo, refs[newer], main)  # declines on newer's tip
    rec = lambda o, recs=recs: next(
        (v for k, v in recs.items() if rm.same_sha(k, o)), None
    )
    for c, status in rm.convergence_report(
        repo, refs[older], ref(newer), main=main, newer_branch=refs[newer]
    ):
        if status == "RBO-ABSENT" and not _in_window(repo, c, since):
            continue
        origs = rm.picked_from(repo, c)
        n_picks += bool(origs)
        decline = (
            rec(origs[0])
            if status == "CONVERGED" and origs and all(rec(o) for o in origs)
            else None
        )
        if decline:
            status = "DECLINED"
        rows_out.append((c, status, origs, decline))
    return rows_out, n_picks


def _counts(rows_out):
    return {st: sum(r[1] == st for r in rows_out) for st in STATUSES}


def _shipped(promoted, newer, branch, promote_ref):
    return (
        "the RC" if not promoted or newer == branch and promote_ref else promoted["tag"]
    )


def _summary(n, n_picks, shipped, newer):
    summary = f"{n_picks} picks, {n['CONVERGED']} in {shipped}" + "".join(
        f", {n[k]} {word}"
        for k, word in (
            ("DECLINED", f"declined on {newer}"),
            ("MISSING", "missing"),
            ("UNCLASSIFIABLE", "unclassifiable"),
        )
        if n[k]
    )
    if n["RBO-ABSENT"]:
        summary += f" · {n['RBO-ABSENT']} release-branch-only to check"
    return summary


def _rbo_what(repo, c):
    body = rm.git(repo, "log", "-1", "--format=%s%n%n%b", c)
    tickets, title = (
        list(dict.fromkeys(rm.RBO_RE.findall(body))),
        body.splitlines()[0],
    )
    lead = "" if title.split(" ", 1)[0] in tickets else ", ".join(tickets) + " "
    return f"{lead}{title} ({rm.commit_link(c)})"


def _unshipped(repo, main, refs, ref, newer, o, pr):
    shipped = ref(newer)
    return (
        shipped.removeprefix("refs/tags/")
        if not pr
        and shipped != refs[newer]
        and rm.is_converged(repo, o, refs[newer], main)
        else None
    )


def _todo(pr, newer, branch, msg):
    if not pr:
        return msg.split(": ", 1)[1]
    then = ", then Take RC again" if newer == branch else f" on `{newer}`"
    return f"merge or close conflict PR {rm.pr_link(pr[0])}" + then


def _row_out(
    repo, main, refs, ref, lookup, message, annotate, branch, older, newer, row, out, line
):
    c, status, origs, decline = row
    if status == "DECLINED":
        d, why = decline
        out.append(
            f"- {rm.commit_link(c, 12)} DECLINED on {rm.branch_link(newer)} original {', '.join(o[:12] for o in origs)}: {why} ({rm.commit_link(d)})"
        )
    elif status == "RBO-ABSENT":
        what = _rbo_what(repo, c)
        out.append(f"- {rm.commit_link(c, 12)} RBO-ABSENT {what}")
        line["rbo"].append(f"on `{older}`: {what}, not on `{newer}`")
    elif status != "CONVERGED":
        out.append(
            f"- {rm.commit_link(c, 12)} {status} original {', '.join(o[:12] for o in origs) or '-'}"
        )
        if status == "MISSING":
            for o in origs:
                pr = lookup(f"backport/{newer.split('/', 1)[1]}/{o[:7]}")
                unshipped = _unshipped(repo, main, refs, ref, newer, o, pr)
                msg = message(o, pr, unshipped=unshipped)
                print(f"::{annotate}::{msg}")
                out.append(f"  - {msg}")
                line["todo"].append(_todo(pr, newer, branch, msg))


def gate(
    repo,
    branch,
    target,
    state,
    promote_ref=None,
    annotate="warning",
    lookup=conflict_pr,
    failure=push_failure,
    oss_repo=None,
):
    """oss_repo: a clone of rs.PINS, for the OSS pins."""
    refs = rs._branches(repo)
    main = rs._main(repo)
    rows = {b["branch"]: b for b in state["branches"]}
    if branch not in refs or branch not in rows:
        raise RuntimeError(f"{branch} not found")

    # a promoted branch ships its latest stable tag for T, not its tip
    ref = functools.partial(_ref, repo, refs, rows, branch, target, promote_ref)
    scope = [s for s in state["supported"][target] if s != branch]
    out = [
        f"### Convergence gate: {rm.branch_link(branch)} for {target} at {rm.ref_link(ref(branch))}",
        "",
    ]
    if not scope:
        out.append("scanned branches: none")
    missing, lines = 0, []
    for s in scope:
        older, newer = rs.older_newer(s, branch)
        promoted = rows[newer]["targets"].get(target, {}).get("promoted")
        since = _since(repo, main, refs[newer], promoted)
        rows_out, n_picks = _scan(repo, main, refs, ref, older, newer, since)
        n = _counts(rows_out)
        missing += n["MISSING"]
        state_s = rows[s]["targets"].get(target, {}).get("state")
        summary = _summary(
            n, n_picks, _shipped(promoted, newer, branch, promote_ref), newer
        )
        line = _line_result(s, older, n_picks, summary, state_s)
        lines.append(line)
        out.append(
            f"**{rm.branch_link(s)}** ({line['side']}, {state_s or 'not enabled'} for {target}; "
            f"{rm.ref_link(refs[older])} into {rm.ref_link(ref(newer))}): {summary}"
        )
        message = functools.partial(
            missing_message,
            repo,
            branch,
            target,
            older,
            newer,
            annotate=annotate,
            failure=failure,
        )
        for row in rows_out:
            _row_out(
                repo,
                main,
                refs,
                ref,
                lookup,
                message,
                annotate,
                branch,
                older,
                newer,
                row,
                out,
                line,
            )
        out.append("")
    if oss_repo:
        n, o_out, o_lines = oss_pins(
            repo, oss_repo, branch, target, scope, ref, rows, annotate
        )
        missing, out, lines = missing + n, out + o_out, lines + o_lines
    return (2 if missing else 0), out, lines


def next_steps(lines, order):
    """No closing full stop: callers join the items."""
    return list(
        dict.fromkeys(
            [t.removesuffix(".") for x in lines for t in x["todo"]]
            + [
                f"promote or retire `{o.split(' is not GA')[0]}` (Retire one shipped line now; Abandon a line that never shipped when it has no GA)"
                for o in order
            ]
        )
    )


def _cell(parts, none="-"):
    return "<br>".join(parts).replace("|", "\\|") or none


def _fixes(name, ls):
    # An UNCLASSIFIABLE-only line has no todo, so its row reads ✅; the detail still counts it.
    named = [x for x in ls if x["state"] == "stabilizing" or x["todo"] or x["rbo"]]
    rest = [x for x in ls if x not in named]
    counts = [f"`{x['line']}` {x['summary']}" for x in named]
    if rest:
        side = rest[0]["side"] if len({x["side"] for x in rest}) == 1 else "other"
        counts.append(
            f"{len(rest)} {side} line{'s' * (len(rest) > 1)} converged ({sum(x['picks'] for x in rest)} picks)"
        )
    todo = next_steps(ls, [])
    return (
        "⛔" if todo else "✅",
        name,
        _cell(counts, "no other supported line"),
        _cell(todo),
    )


def _order_row(order):
    return (
        "⛔" if order else "✅",
        "promote order",
        _cell([o.split(":")[0] for o in order], "no older line is waiting to go GA"),
        _cell(next_steps([], order)),
    )


def _rbo_row(lines):
    rbo = [r for x in lines for r in x["rbo"]]
    return (
        "⚠" if rbo else "✅",
        "release-branch-only to check",
        _cell(rbo, "none"),
        "check whether the newer line needs its own equivalent" if rbo else "-",
    )


def checks(lines, order, out, split=False):
    """split: one fixes row per direction instead of one for every other line."""
    own, pinned = (
        [x for x in lines if not x.get("oss")],
        [x for x in lines if x.get("oss")],
    )
    if split:
        rows = [
            _fixes(f"fixes match {side} lines", [x for x in own if x["side"] == side])
            for side in ("newer", "older")
        ]
    else:
        rows = [_fixes("fixes match the other lines", own)]
    if pinned:
        rows.append(_fixes("OSS pins match the other lines", pinned))
    rows.append(_order_row(order))
    rows.append(_rbo_row(lines))
    table = ["| check | result | do this |", "|---|---|---|"] + [
        f"| {i} {c} | {r} | {d} |" for i, c, r, d in rows
    ]
    return table, ["<details><summary>Gate detail</summary>", "", *out, "</details>"]


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--branch", type=rm.option_free, required=True)
    p.add_argument("--target", required=True)
    p.add_argument(
        "--promote-ref",
        type=rm.option_free,
        help="the RC being built or promoted; default: the branch's own reference",
    )
    p.add_argument("--state", help="relstate JSON; default: derive it now")
    p.add_argument("--repo", default=".")
    p.add_argument(
        "--slug",
        default=os.environ.get("GITHUB_REPOSITORY"),
        help="owner/name of --repo on GitHub, for its backport PRs; default: $GITHUB_REPOSITORY",
    )
    p.add_argument(
        "--oss-repo",
        default=os.environ.get("OSS_REPO"),
        help="clone of the repo this one pins (relstate PINS); required when PINS is set. Default: $OSS_REPO",
    )
    p.add_argument(
        "--annotate",
        choices=("warning", "error"),
        default="warning",
        help="annotation level of MISSING rows: error where they block (Promote), warning where not",
    )
    p.add_argument(
        "--out",
        default=os.environ.get("GITHUB_STEP_SUMMARY"),
        help="file the checks table and gate detail are appended to; default: the step summary",
    )
    try:
        a = p.parse_args(argv)
    except SystemExit as e:  # argparse exits 2 on bad usage, which reads as MISSING picks
        return 1 if e.code else 0
    try:
        out_file = a.out and rm.local_path(a.out)
        if not a.slug:
            raise RuntimeError("--slug (or GITHUB_REPOSITORY) is required")
        os.environ["GITHUB_REPOSITORY"] = a.slug  # relmgr's link helpers read it
        if (name := a.slug.lower().split("/")[-1]) != rs.SLUG:
            rs.use(name)  # relstate chose its config from the env at import
        if rs.PINS and not a.oss_repo:
            raise RuntimeError(
                f"--oss-repo (or OSS_REPO) is required: this repo pins {rs.PINS}"
            )
        if a.state:
            with open(rm.local_path(a.state)) as f:
                state = json.load(f)
        else:
            state = rs.derive(a.repo, dt.datetime.now(dt.UTC))
        code, out, lines = gate(
            a.repo,
            a.branch,
            a.target,
            state,
            a.promote_ref,
            annotate=a.annotate,
            lookup=functools.partial(conflict_pr, slug=a.slug),
            failure=functools.partial(push_failure, slug=a.slug),
            oss_repo=a.oss_repo if rs.PINS else None,
        )
        order = rs.promote_blockers(state, a.branch, a.target)
    except Exception as e:  # git, registry or input failure: an error, never a pass
        traceback.print_exc()
        print(f"::error::convgate: {type(e).__name__}: {e}")
        return 1
    print("\n".join(out + order))
    if out_file:
        table, detail = checks(lines, order, out)
        with open(out_file, "a") as f:
            f.write("\n".join(table + [""] + detail) + "\n\n")
    return 2 if code else 0


if __name__ == "__main__":
    sys.exit(main())
