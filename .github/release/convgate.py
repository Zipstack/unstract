"""Convergence gate: scan every other supported branch of a target, both directions, so an older branch
never ships a fix a newer one lacks.

Usage: convgate.py --branch release/X.Y --target T [--promote-ref vX.Y.Z-rc.N] [--state state.json] [--repo DIR]
                   [--oss-repo DIR] [--annotate warning|error] [--out FILE]

Wraps relmgr.convergence_report and adds:
- scope: relstate `supported[T]` minus the branch. Retired and not-enabled branches are out by construction.
- direction: an older branch's picks are checked against the newer branch, whichever side is being promoted.
- reference: a newer branch with a promoted stable tag for T is scanned at that tag (what ships next), not at its tip,
  even before it is GA (on-prem: promoted, chart not published yet). The branch being promoted is scanned at
  --promote-ref where it is the newer side. As the older side it is scanned at its tip, so a fix picked after the
  RC still blocks.
- declines shown: an older line's pick the newer line declined prints as DECLINED, with the reason and the decline
  commit (relmgr.decline_records). It counts as converged. A decline on the older line owes the newer line nothing.
- release-branch-only window: RBO-ABSENT is kept only for commits after the newer line's latest promoted tag (else
  its cut) that touch paths outside .github/.
- OSS pins (a repo whose lines pin an OSS tag, relstate PINS): the same scan in a clone of the OSS repo, the older
  line's pinned OSS tag into the newer line's, so an upgrade never loses an OSS fix. Each line is read at the same
  reference as above. A MISSING row names where to act: the OSS line (OSS Backport) or a new RC of the newer line.
Exit 2 iff any MISSING or an older line is not GA yet (promote order), 0 otherwise, 1 on error (never a silent
pass). Take RC build warns on 2; Promote blocks.
checks() turns a gate result into the checks table both summaries lead with, and the full rows folded below it.
"""

import argparse
import datetime as dt
import functools
import json
import os
import re
import subprocess
import sys
import traceback

import oss
import relmgr as rm
import relstate as rs

STATUSES = ("CONVERGED", "DECLINED", "MISSING", "UNCLASSIFIABLE", "RBO-ABSENT")
CLOSE_HOWTO = "resolve, get one approval and merge, or close the PR to decline (the close comment is the reason)."


def conflict_pr(head):
    """(number, url) of the open Backport conflict PR on `head`, or None."""
    r = subprocess.run(
        [
            "gh",
            "pr",
            "list",
            "-R",
            os.environ["GITHUB_REPOSITORY"],
            "--head",
            head,
            "--state",
            "open",
            "--json",
            "number,url",
        ],
        capture_output=True,
        text=True,
    )
    if r.returncode:  # never report "no PR found" when the lookup itself failed
        raise RuntimeError(f"gh pr list --head {head}: {r.stderr.strip()}")
    prs = json.loads(r.stdout or "[]")
    return (prs[0]["number"], prs[0]["url"]) if prs else None


def push_failure(number, branch):
    """Run URL in the newest `Backport to <branch> failed:` comment Backport left on PR #number, or None."""
    r = subprocess.run(
        [
            "gh",
            "api",
            "--paginate",
            f"repos/{os.environ['GITHUB_REPOSITORY']}/issues/{number}/comments",
            "--jq",
            f'.[] | .body | split("\\n")[0] | select(startswith("Backport to {branch} failed:"))',
        ],
        capture_output=True,
        text=True,
    )
    if r.returncode:  # never read a failed lookup as "no failure comment"
        raise RuntimeError(f"gh api issues/{number}/comments: {r.stderr.strip()}")
    m = re.search(r"\(run (\S+)\)", (r.stdout.strip().splitlines() or [""])[-1])
    return m and m[1]


def blocked(branch, target, annotate):
    """The lead of every MISSING message: an error where it blocks (Promote), a warning where it will (Take RC)."""
    return (
        f"Cannot promote {branch} for {target}"
        if annotate == "error"
        else f"Promote of {branch} for {target} will be blocked"
    )


def missing_message(
    repo, branch, target, older, newer, orig, pr, annotate, unshipped=None, failure=None
):
    """What blocks the promote of `branch` and where to act: the fix `orig` is on `older` but not on `newer`.
    unshipped: the tag `newer` is scanned at (its latest stable, or the RC being promoted when `newer` is
    `branch`) when the fix is on `newer`'s tip but not in that tag.
    failure(pr number, newer): the run URL of Backport's push-failure comment on the source PR, or None.
    """
    o7 = orig[:7]
    # orig may not be on main.
    n = rm.subject_pr(repo, orig, check=False)
    fix = f"fix {o7}" + (f" (PR #{n})" if n is not None else "")
    head = blocked(branch, target, annotate)
    # An RC of this line, cut before the fix.
    if unshipped and newer == branch and rs.VER_RE.fullmatch(unshipped)[4]:
        return f"{head}: {fix} is on {newer} but not in RC {unshipped}: take a new RC build first."
    if unshipped:  # nothing to pick or decline: the fix only waits for newer's next patch
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
    """{line: its pinned OSS tag}, each tag checked present in oss_repo."""
    pins = {n: oss.pin(repo, ref(n)) for n in names}
    for p in set(pins.values()):
        if not rs._tag_commit(oss_repo, p):
            raise RuntimeError(f"no OSS tag {p} in {oss_repo}")
    return pins


def _oss_found(oss_repo, main, oss_refs, p_old, p_new, line_new):
    """The CONVERGED and MISSING rows of the OSS picks between two pins."""
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
        # Accepted: a pin counts only CONVERGED and MISSING rows.
        if r[1] in ("CONVERGED", "MISSING")
    ]


def _oss_act(oss_repo, main, oss_refs, o, newer, line_new):
    """(fix, act) for the OSS original o missing from newer's pin."""
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
    """(missing, report lines, per-line results): each older line's pinned OSS tag scanned into the newer line's."""
    main, oss_refs = "refs/remotes/origin/main", rs._branches(oss_repo)
    pins = _oss_pins_of(repo, oss_repo, [branch, *scope], ref)
    head = blocked(branch, target, annotate)
    missing, lines, out = 0, [], [f"### OSS pins: `{branch}` pins `{pins[branch]}`", ""]
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
            f"**{s}** ({line['side']}; `{older}` pins `{p_old}`, `{newer}` pins `{p_new}`): {summary}"
        )
        for c, st in found:
            if st != "MISSING":
                continue
            for o in rm.picked_from(oss_repo, c):
                fix, act = _oss_act(oss_repo, main, oss_refs, o, newer, line_new)
                msg = f"{head}: {fix} is in {older}'s OSS pin {p_old} but not in {newer}'s pin {p_new}: {act}."
                print(f"::{annotate}::{msg}")
                out.append(f"- `{c[:12]}` MISSING original {o[:12]}")
                out.append(f"  - {msg}")
                line["todo"].append(act)
        out.append("")
    return missing, out, lines


def _line_result(s, older, picks, summary, state, oss=False):
    """The per-line result checks() reads, for line s scanned against branch."""
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
    """refs/tags/<tag>, after checking the tag exists."""
    if not rs._tag_commit(repo, tag):
        raise RuntimeError(f"no git tag {tag}")
    return f"refs/tags/{tag}"


def _ref(repo, refs, rows, branch, target, promote_ref, name):
    """The ref gate() scans line `name` at."""
    if name == branch and promote_ref:
        return _tag_ref(repo, promote_ref)
    p = rows[name]["targets"].get(target, {}).get("promoted")
    return _tag_ref(repo, p["tag"]) if p else refs[name]


def _since(repo, main, newer_tip, promoted):
    """Unix time the release-branch-only window opens: the promoted stable tag, else the cut."""
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
    """Whether release-branch-only commit c is dated after since and touches a path outside .github/."""
    return int(rm.git(repo, "log", "-1", "--format=%ct", c)) > since and any(
        not f.startswith(".github/")
        for f in rm.git(repo, "show", "--format=", "--name-only", c).split()
    )


def _scan(repo, main, refs, ref, older, newer, since):
    """(rows, picks): each (commit, status, originals, decline) of older scanned into newer."""
    rows_out, n_picks = [], 0
    recs = rm.decline_records(repo, refs[newer], main)  # declines on newer's tip
    rec = lambda o, recs=recs: next(
        (v for k, v in recs.items() if rm.same_sha(k, o)), None
    )
    for c, status in rm.convergence_report(
        repo, refs[older], ref(newer), main=main, newer_branch=refs[newer]
    ):
        if status == "RBO-ABSENT" and not _in_window(repo, c, since):
            continue  # outside the window, or nothing outside .github/ (an empty commit included)
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
    """{status: number of rows_out with it}."""
    return {st: sum(r[1] == st for r in rows_out) for st in STATUSES}


def _shipped(promoted, newer, branch, promote_ref):
    """The summary's name for newer's reference: what newer is scanned at."""
    return (
        "the RC" if not promoted or newer == branch and promote_ref else promoted["tag"]
    )


def _summary(n, n_picks, shipped, newer):
    """A line's counts, from the per-status counts n."""
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
    """The ticket(s), title and link of release-branch-only commit c."""
    body = rm.git(repo, "log", "-1", "--format=%s%n%n%b", c)
    tickets, title = (
        list(dict.fromkeys(rm.RBO_RE.findall(body))),
        body.splitlines()[0],
    )
    # Skip the ticket when the title starts with it.
    lead = "" if title.split(" ", 1)[0] in tickets else ", ".join(tickets) + " "
    return f"{lead}{title} ({rm.commit_link(c)})"


def _unshipped(repo, main, refs, ref, newer, o, pr):
    """The tag newer is scanned at when the fix o, with no conflict PR, is on newer's tip but not in it, else None."""
    shipped = ref(newer)
    return (
        shipped.removeprefix("refs/tags/")
        if not pr
        and shipped != refs[newer]
        and rm.is_converged(repo, o, refs[newer], main)
        else None
    )


def _todo(pr, newer, branch, msg):
    """The do-this item for one MISSING original."""
    if not pr:
        return msg.split(": ", 1)[1]
    then = ", then Take RC again" if newer == branch else f" on `{newer}`"
    return f"merge or close conflict PR {rm.pr_link(pr[0])}" + then


def _row_out(
    repo, main, refs, ref, lookup, message, annotate, branch, older, newer, row, out, line
):
    """Append one scanned row's detail to out and its do-this or to-check item to line."""
    c, status, origs, decline = row
    if status == "DECLINED":
        d, why = decline
        out.append(
            f"- `{c[:12]}` DECLINED on {newer} original {', '.join(o[:12] for o in origs)}: {why} ({d[:7]})"
        )
    # RBO-ABSENT has no original: name the ticket and commit.
    elif status == "RBO-ABSENT":
        what = _rbo_what(repo, c)
        out.append(f"- `{c[:12]}` RBO-ABSENT {what}")
        line["rbo"].append(f"on `{older}`: {what}, not on `{newer}`")
    elif status != "CONVERGED":
        out.append(
            f"- `{c[:12]}` {status} original {', '.join(o[:12] for o in origs) or '-'}"
        )
        if status == "MISSING":
            # the developer's next step, on the run page and in the summary
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
    """(exit code, report lines, per-line results for checks()). oss_repo: a clone of rs.PINS, for the OSS pins."""
    refs = rs._branches(repo)
    main = rs._main(repo)
    rows = {b["branch"]: b for b in state["branches"]}
    if branch not in refs or branch not in rows:
        raise RuntimeError(f"{branch} not found")

    # a promoted branch ships its latest stable tag for T, not its tip
    ref = functools.partial(_ref, repo, refs, rows, branch, target, promote_ref)
    scope = [s for s in state["supported"][target] if s != branch]
    out = [f"### Convergence gate: `{branch}` for {target} at `{ref(branch)}`", ""]
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
            f"**{s}** ({line['side']}, {state_s or 'not enabled'} for {target}; "
            f"`{refs[older]}` into `{ref(newer)}`): {summary}"
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
    """The do-this items in checks-table order, each once and without a closing full stop (the Next line joins them):
    every line's todo, then each promote-order blocker.
    """
    return list(
        dict.fromkeys(
            [t.removesuffix(".") for x in lines for t in x["todo"]]
            + [f"promote or retire `{o.split(' is not GA')[0]}`" for o in order]
        )
    )


def _cell(parts, none="-"):
    """A table cell: the parts on separate lines, pipes escaped."""
    return "<br>".join(parts).replace("|", "\\|") or none


def _fixes(name, ls):
    """A fixes row of the checks table for the lines ls."""
    # Accepted: an UNCLASSIFIABLE-only line has no todo, so its row reads ✅ (the detail still counts it).
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
    """The promote order row of the checks table."""
    return (
        "⛔" if order else "✅",
        "promote order",
        _cell([o.split(":")[0] for o in order], "no older line is waiting to go GA"),
        _cell(next_steps([], order)),
    )


def _rbo_row(lines):
    """The release-branch-only row of the checks table."""
    rbo = [r for x in lines for r in x["rbo"]]
    return (
        "⚠" if rbo else "✅",
        "release-branch-only to check",
        _cell(rbo, "none"),
        "check whether the newer line needs its own equivalent" if rbo else "-",
    )


def checks(lines, order, out, split=False):
    """(checks table, folded gate detail) from gate()'s lines and out and relstate.promote_blockers' order.
    split: one fixes row per direction (Promote) instead of one for every other line (the Take RC preview).
    Blocking and to-check rows name what to do; healthy rows show counts only. A line is named only when it is
    stabilizing for the target or has something to do or check; the rest are one trailing count.
    """
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
    a = p.parse_args(argv)
    try:
        out_file = a.out and rm.local_path(a.out)
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
    return 2 if code or order else 0


if __name__ == "__main__":
    sys.exit(main())
