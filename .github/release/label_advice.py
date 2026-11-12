"""Which backport label a PR into main needs, decided by the script where it can be and asked where it cannot.

Usage (from a clone of this repo, with gh logged in):
  label_advice.py --pr N [--answer hotfix=yes|no] [--json]
  label_advice.py --branch REF [--answer hotfix=yes|no] [--json]   a local branch with no PR yet
  label_advice.py --declare X.Y --pr N                               add `Backport-also: X.Y` to the PR body
  label_advice.py --owed [--author LOGIN] [--json]                   what your merged PRs still owe release lines

Results: `decided` (no judgement left; Lint PR warns on a different label; `label` is null for a Backport pick
PR, whose labels belong to the bot), `suggest` (a default the author may override) and `ask` (one question; `next`
holds the command to re-run for each answer). Exit 0 with advice, 1 when GitHub or git fails, 2 on bad input.
"""

import argparse
import contextlib
import io
import json
import os
import re
import sys
import urllib.parse

import backport as bp
import relmgr as rm
import relstate as rs

RC, GA, RBO = "backport/rc", "backport/ga", "release-branch-only"
MAIN_ONLY = rm.MAIN_ONLY
SELF = "python3 .github/release/label_advice.py"
CLOUD = "Zipstack/unstract-cloud"  # on-prem is promoted there, for both repos' lines
# Paths that never ship in a release image: docs, tests and repo tooling. A PR touching only these
# is decided main-only by design, though a release line may want a test or CI fix: the developer
# labels it backport/rc instead, which Lint PR only warns on. Below the root, .md/.mdx/.rst other
# than README.md can be a runtime prompt, so it counts as shipping.
NONCODE = re.compile(
    r"^[^/]*\.(md|mdx|rst)$|(^|/)README\.md$|^docs/|(^|/)tests?/|(^|/)test_[^/]*\.py$|_test\.py$|\.(test|spec)\.[jt]sx?$"
    r"|(^|/)__tests__/|(^|/)unittests/|^\.github/|^\.claude(-plugin)?/|^\.pre-commit-config\.yaml$"
)
PROMOTE_RE = re.compile(r"Promote v?(\d+\.\d+)\.\d+-rc\.\d+ · ([^(]*)")


class Usage(Exception):
    pass


def advise(base, paths, lines, hotfix=None, pr=None, head="", picks=False):
    """Pure core. lines: [{"line", "present", "ga", "onprem_ga"}] for the live release lines; present = some
    changed code path exists at the line's tip; ga = the line has a stable tag; onprem_ga = on-prem confirmed GA
    (None: unknown). picks: a commit of a PR into a release line carries a `cherry picked from` trailer.
    """
    out = {
        "result": "decided",
        "label": None,
        "reason": "",
        "question": None,
        "info": [],
        "next": None,
    }
    if base.startswith("release/") and rm.is_backport(head):
        return {**out, "reason": "a Backport pick PR: its labels belong to the bot"}
    if base.startswith("release/") and picks:
        return {
            **out,
            "result": "suggest",
            "label": RBO,
            "reason": f"a cherry-pick into {base}: {RBO} only if the change is not on main; a fix from main is "
            "Backport's to pick",
        }
    if base.startswith("release/"):
        return {**out, "label": RBO, "reason": f"a change made only on {base}"}
    if not code(paths):
        return {
            **out,
            "label": MAIN_ONLY,
            "reason": "only docs, tests or repo tooling change; none ships",
        }
    live = [l for l in lines if l["present"]]
    if not live:
        return {
            **out,
            "label": MAIN_ONLY,
            "reason": "the changed code is on no live release line",
        }
    rc = [f"release/{l['line']}" for l in live if not l["ga"]]
    ga = [f"release/{l['line']}" for l in live if l["ga"]]
    no = RC if rc else MAIN_ONLY
    if ga and hotfix is None:
        return {
            **out,
            "result": "ask",
            "reason": f"the changed code is on released line(s) {', '.join(ga)}",
            "question": {
                "key": "hotfix",
                "text": f"Is this a hotfix or vulnerability fix that {', '.join(ga)} must get as a patch release?",
                "answers": {"yes": GA, "no": no},
            },
            "info": _info(live, pr),
            "next": {
                a: f"{SELF} {_target(pr)} --answer hotfix={a}" for a in ("yes", "no")
            },
        }
    if ga and hotfix:
        return {
            **out,
            "result": "suggest",
            "label": GA,
            "reason": f"a hotfix for released line(s) {', '.join(ga)}; each pick there is confirmed before Promote",
        }
    reason = (
        f"the changed code is on {', '.join(rc)}, still awaiting GA"
        if rc
        else "not a hotfix, and every line with the code is released"
    )
    return {
        **out,
        "result": "suggest",
        "label": no,
        "reason": reason,
        "info": _info(live, pr),
    }


def code(paths):
    return [p for p in paths if not NONCODE.search(p)]


def _target(pr):
    return f"--pr {pr}" if isinstance(pr, int) else f"--branch {pr}"


def _info(live, pr):
    """A line GA for cloud and not yet for on-prem: the label cannot route a fix to on-prem alone, a declaration can.
    It needs backport/rc (or backport/ga): Backport never picks a main-only PR.
    """
    return [
        {
            "line": l["line"],
            "text": f"release/{l['line']} is GA, but "
            + (
                "on-prem GA is unknown (Promote runs unreadable)"
                if l["onprem_ga"] is None
                else "not confirmed GA for on-prem"
            )
            + f": if on-prem needs this fix there, label it `{RC}` and declare it (adds `Backport-also: "
            f"{l['line']}` to the PR body; the line's on-prem RC builds wait for it)",
            "command": f"{SELF} --declare {l['line']} {_target(pr)}"
            if isinstance(pr, int)
            else None,
        }
        for l in live
        if l["ga"] and l["onprem_ga"] is not True
    ]


def _gh(*args):
    return bp.gh(*args, retry=False)


def slug_from_origin():
    url = rm.git(".", "remote", "get-url", "origin")
    m = re.search(r"github\.com[:/]([^/]+/[^/]+?)(?:\.git)?/?$", url)
    if not m:
        raise Usage(f"origin is not a GitHub repo: {url}")
    return m[1]


def live_lines(slug):
    names = _gh(
        "api", "--paginate", f"repos/{slug}/branches?per_page=100", "--jq", ".[].name"
    ).split()
    return sorted(
        (
            n.removeprefix("release/")
            for n in names
            if re.fullmatch(r"release/\d+\.\d+", n)
        ),
        key=lambda v: tuple(map(int, v.split("."))),
        reverse=True,
    )


def tree(slug, line):
    t = json.loads(_gh("api", f"repos/{slug}/git/trees/release/{line}?recursive=1"))
    return None if t.get("truncated") else {e["path"] for e in t["tree"]}


def has_ga(slug, line):
    refs = json.loads(
        _gh("api", f"repos/{slug}/git/matching-refs/tags/{rs.PREFIX}v{line}.")
    )
    ver = rs.ver_re(rs.PREFIX)
    return any(
        (m := ver.fullmatch(r["ref"].removeprefix("refs/tags/"))) and m[4] is None
        for r in refs
    )


def onprem_ga_lines():
    """Lines with a successful on-prem Promote; None when the runs cannot be read (the note then says unknown)."""
    try:
        runs = json.loads(
            _gh(
                "run",
                "list",
                "-R",
                CLOUD,
                "-w",
                "promote.yaml",
                "-s",
                "success",
                "-L",
                "200",
                "--json",
                "displayTitle",
            )
        )
    except RuntimeError as e:
        print(
            f"note: could not read {CLOUD} Promote runs ({e}); on-prem GA unknown",
            file=sys.stderr,
        )
        return None
    return {
        m[1]
        for r in runs
        if (m := PROMOTE_RE.match(r["displayTitle"])) and "on-prem" in m[2]
    }


def line_facts(slug, paths, need_ga=True):
    onprem, read = None, False
    out = []
    for line in live_lines(slug):
        files = tree(slug, line)
        present = files is None or any(
            p in files for p in code(paths)
        )  # truncated: assume present
        ga = present and need_ga and has_ga(slug, line)
        if ga and not read:
            onprem, read = onprem_ga_lines(), True
        out.append(
            {
                "line": line,
                "present": present,
                "ga": ga,
                "onprem_ga": ga and (None if onprem is None else line in onprem),
            }
        )
    return out


def pr_facts(slug, n):
    pr = json.loads(_gh("api", f"repos/{slug}/pulls/{n}"))
    files = json.loads(
        _gh("api", "--paginate", "--slurp", f"repos/{slug}/pulls/{n}/files?per_page=100")
    )
    paths = sorted(
        {
            p
            for page in files
            for f in page
            for p in (f["filename"], f.get("previous_filename"))
            if p
        }
    )
    return pr, paths


def advise_pr(slug, n, hotfix=None, pr=None, paths=None, need_ga=True):
    """Advice for PR n. Lint PR passes need_ga=False on its success path: only the decided results matter there."""
    if pr is None:
        pr, paths = pr_facts(slug, n)
    base = pr["base"]["ref"]
    lines = (
        line_facts(slug, paths, need_ga)
        if code(paths) and not base.startswith("release/")
        else []
    )
    picks = base.startswith("release/") and any(
        "(cherry picked from commit " in c["commit"]["message"]
        for page in json.loads(
            _gh(
                "api",
                "--paginate",
                "--slurp",
                f"repos/{slug}/pulls/{n}/commits?per_page=100",
            )
        )
        for c in page
    )
    adv = advise(base, paths, lines, hotfix, n, pr["head"]["ref"], picks)
    have = {l["name"] for l in pr.get("labels", [])}
    if adv["label"] and adv["result"] != "ask" and adv["label"] not in have:
        others = sorted(have & {MAIN_ONLY, RBO, *rm.BACKPORT_LABELS})
        cmds = [
            f"gh api -X DELETE repos/{slug}/issues/{n}/labels/{urllib.parse.quote(o, safe='')}"
            for o in others
        ]
        adv["next"] = " && ".join(
            [*cmds, f"gh api repos/{slug}/issues/{n}/labels -f 'labels[]={adv['label']}'"]
        )
    return {"repo": slug, "pr": n, **adv}


def advise_branch(slug, ref, hotfix=None):
    base = rm.git(".", "merge-base", "origin/main", ref)
    paths = sorted(
        set(rm.git(".", "diff", "--name-only", "--no-renames", base, ref).split("\n"))
        - {""}
    )
    lines = line_facts(slug, paths) if code(paths) else []
    return {"repo": slug, "pr": None, **advise("main", paths, lines, hotfix, ref)}


def declare(slug, n, value):
    line = rm.line(value)
    try:
        _gh("api", f"repos/{slug}/branches/release/{line}")
    except RuntimeError as e:
        if "HTTP 404" not in str(e):
            raise
        raise Usage(f"release/{line} does not exist on {slug}")
    pr = json.loads(_gh("api", f"repos/{slug}/pulls/{n}"))
    body = pr["body"] or ""
    if line in rm.declared_lines(body):
        return f"#{n} already declares `Backport-also: {line}`"
    if MAIN_ONLY in {l["name"] for l in pr.get("labels", [])}:
        raise Usage(
            f"#{n} is {MAIN_ONLY}, which Backport never picks: label it `{RC}` first, then declare"
        )
    _gh(
        "api",
        "-X",
        "PATCH",
        f"repos/{slug}/pulls/{n}",
        "-f",
        f"body={body.rstrip()}\n\nBackport-also: {line}\n",
    )
    # GitHub has no conditional write: a concurrent body edit can drop the line, so check it landed.
    after = json.loads(_gh("api", f"repos/{slug}/pulls/{n}"))["body"] or ""
    if line not in rm.declared_lines(after):
        raise RuntimeError(
            f"#{n}'s body changed meanwhile and lost the declaration; run --declare again"
        )
    return (
        f"#{n} now declares `Backport-also: {line}`. Pick it: gh workflow run backport.yaml -R {slug} "
        f"-f commits={n} -f lines={line} -f patch_released_lines=true"
    )


def owed(slug, author):
    """[{line, pr, title, why, command}] for author's merged PRs that a live line still owes (needs origin fetched)."""
    login = author or _gh("api", "user", "--jq", ".login")
    rows = []
    for branch, ref in sorted(rs._branches(".").items()):
        if not ref.startswith("refs/remotes/"):
            continue  # a local branch left after origin deleted it: the line is retired
        line = branch.removeprefix("release/")
        base = rm.git(".", "merge-base", "origin/main", f"origin/{branch}")
        since = bp.search_since(".", base)
        mine = {
            f"#{p['number']}"
            for p in json.loads(
                _gh(
                    "pr",
                    "list",
                    "-R",
                    slug,
                    "--state",
                    "merged",
                    "--base",
                    "main",
                    "--author",
                    login,
                    "--search",
                    f"merged:>={since}",
                    "--limit",
                    "1000",
                    "--json",
                    "number",
                )
            )
        }
        if not mine:
            continue
        released = any(
            rs.ver_re(rs.PREFIX).fullmatch(t)[4] is None for t in rs.line_tags(".", line)
        )
        accept = bp.HELD if released else bp.OWED  # what Backport picks there on its own
        cmd = f"gh workflow run backport.yaml -R {slug} -f commits={{}} -f lines={line} -f patch_released_lines=true"
        # Backport's `held:` count: a developer reading the answer cannot act on it, but can on a warning.
        log = sys.stderr if os.environ.get("GITHUB_ACTIONS") else io.StringIO()
        try:
            with contextlib.redirect_stdout(log):
                held = bp.held(
                    slug, ".", branch, accept=accept, cache=bp.pr_classes(slug, since)
                )
                decl = bp.declared(slug, ".", branch)
        finally:
            if log is not sys.stderr:
                sys.stderr.writelines(
                    x
                    for x in log.getvalue().splitlines(True)
                    if not x.startswith("held: ")
                )
        for _, cls, pr, title in held:
            if pr in mine:
                rows.append(
                    {
                        "line": line,
                        "pr": pr,
                        "title": title,
                        "why": f"label class {cls}",
                        "command": cmd.format(pr[1:]),
                    }
                )
        listed = {r["pr"] for r in rows if r["line"] == line}
        for n, title in decl:
            if f"#{n}" in mine and f"#{n}" not in listed:  # one row per PR: same command
                rows.append(
                    {
                        "line": line,
                        "pr": f"#{n}",
                        "title": title,
                        "why": f"Backport-also: {line}",
                        "command": cmd.format(n),
                    }
                )
    return rows


def render(adv):
    where = f"#{adv['pr']}" if adv["pr"] else "this branch"
    if adv["result"] == "ask":
        q = adv["question"]
        text = (
            f"{where}: one question — {q['text']}\n  ({adv['reason']})\n"
            f"  yes: {q['answers']['yes']}, then: {adv['next']['yes']}\n"
            f"  no: {q['answers']['no']}, then: {adv['next']['no']}"
        )
    elif adv["label"] is None:
        text = f"{where}: no label — {adv['reason']}"
    else:
        text = f"{where}: {adv['result']} `{adv['label']}` — {adv['reason']}"
        if adv["next"]:
            text += f"\n  apply: {adv['next']}"
    for i in adv["info"]:
        text += f"\n  note: {i['text']}" + (
            f"\n    {i['command']}" if i["command"] else ""
        )
    return text


def main(argv=None):
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--pr", type=int)
    ap.add_argument("--branch")
    ap.add_argument("--owed", action="store_true")
    ap.add_argument("--declare", metavar="X.Y")
    ap.add_argument("--answer", action="append", default=[], metavar="hotfix=yes|no")
    ap.add_argument("--author")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)
    try:
        modes = [
            m
            for m, on in (
                ("--pr", a.pr is not None and not a.declare),
                ("--branch", a.branch),
                ("--owed", a.owed),
                ("--declare", a.declare),
            )
            if on
        ]
        if len(modes) != 1 or (a.declare and a.pr is None):
            raise Usage(
                "use one of --pr N, --branch REF, --owed, or --declare X.Y --pr N"
            )
        answers = dict(x.split("=", 1) for x in a.answer if "=" in x)
        if (
            len(answers) != len(a.answer)
            or set(answers) - {"hotfix"}
            or set(answers.values()) - {"yes", "no"}
        ):
            raise Usage(f"--answer takes hotfix=yes or hotfix=no, got {a.answer}")
        hotfix = None if "hotfix" not in answers else answers["hotfix"] == "yes"
        slug = slug_from_origin()
        rs.use(slug.split("/")[1].lower())
        if a.declare:
            print(declare(slug, a.pr, a.declare))
            return 0
        if a.pr is not None:
            adv = advise_pr(slug, a.pr, hotfix)
            print(json.dumps(adv, indent=2) if a.json else render(adv))
            return 0
        rm.git(
            ".",
            "fetch",
            "-q",
            "--prune",
            "origin",
            "main",
            "+refs/heads/release/*:refs/remotes/origin/release/*",
            "--tags",
        )
        if a.branch:
            adv = advise_branch(slug, a.branch, hotfix)
            print(json.dumps(adv, indent=2) if a.json else render(adv))
            return 0
        rows = owed(slug, a.author)
        print(
            json.dumps(rows, indent=2)
            if a.json
            else "\n".join(
                f"release/{r['line']} {r['pr']} {r['title']} ({r['why']})\n  {r['command']}"
                for r in rows
            )
            or "nothing owed"
        )
        return 0
    except json.JSONDecodeError as e:
        print(f"error: unreadable GitHub answer: {e}", file=sys.stderr)
        return 1
    except (Usage, ValueError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    except RuntimeError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
