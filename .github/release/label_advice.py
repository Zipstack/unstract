"""Which backport label a PR into main needs, decided by the script where it can be and asked where it cannot.

Usage (from a clone of this repo, with gh logged in):
  label_advice.py --pr N [--answer hotfix=yes|no | --answer line=X.Y|main-only] [--json]
  label_advice.py --branch REF [--answer hotfix=yes|no | --answer line=X.Y|main-only] [--json]   no PR yet
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

RBO = "release-branch-only"
MAIN_ONLY = rm.MAIN_ONLY
SELF = "python3 .github/release/label_advice.py"
# Paths that never ship in a release image: docs, tests and repo tooling. A PR touching only these
# is decided main-only by design, though a release line may want a test or CI fix: the developer
# labels it backport/X.Y instead, which Lint PR only warns on. Below the root, .md/.mdx/.rst other
# than README.md can be a runtime prompt, so it counts as shipping.
NONCODE = re.compile(
    r"^[^/]*\.(md|mdx|rst)$|(^|/)README\.md$|^docs/|(^|/)tests?/|(^|/)test_[^/]*\.py$|_test\.py$|\.(test|spec)\.[jt]sx?$"
    r"|(^|/)__tests__/|(^|/)unittests/|^\.github/|^\.claude(-plugin)?/|^\.pre-commit-config\.yaml$"
)
HUNK_RE = re.compile(r"^@@ -(\d+)(?:,\d+)? .*$", re.M)
BLAME_MAX = 20  # files blamed per PR; past it, presence is judged by path


class Usage(Exception):
    pass


def advise(
    base, paths, lines, hotfix=None, pr=None, head="", picks=False, how="", line=None
):
    """Pure core. lines: [{"line", "present", "ga"}] for the live release lines, newest first; present = the changed
    code is on the line; ga = the line has a stable tag. picks: a commit of a PR into a release line carries a
    `cherry picked from` trailer. how: the evidence behind present, quoted in the reason.
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
    why = f" ({how})" if how else ""
    if line:  # the developer's answer to the line question
        if line != MAIN_ONLY and line not in [l["line"] for l in lines]:
            raise Usage(
                f"line={line} is not a live release line ({', '.join(l['line'] for l in lines) or 'none'})"
            )
        label = MAIN_ONLY if line == MAIN_ONLY else f"backport/{line}"
        return {
            **out,
            "result": "suggest",
            "label": label,
            "reason": "your answer to the line question",
        }
    unknown = [l["line"] for l in lines if l["present"] is None]
    if unknown:
        options = [*(f"backport/{l['line']}" for l in lines), MAIN_ONLY]
        return {
            **out,
            "result": "ask",
            "reason": f"cannot tell whether the changed code is on {_rel(unknown)}{why}",
            "question": {
                "key": "line",
                "text": "Which is the oldest release line that needs this fix?",
                "answers": {o: o for o in options},
            },
            "next": {
                o: f"{SELF} {_target(pr)} --answer line={o.removeprefix('backport/')}"
                for o in options
            },
        }
    live = [l for l in lines if l["present"]]
    if not live:
        return {
            **out,
            "label": MAIN_ONLY,
            "reason": f"the changed code is on no live release line{why}",
        }
    rc = [l["line"] for l in live if not l["ga"]]
    ga = [l["line"] for l in live if l["ga"]]
    # Fixes flow forward, so the label names the oldest line; lines come newest first.
    no = f"backport/{rc[-1]}" if rc else MAIN_ONLY
    yes = f"backport/{ga[-1]}" if ga else None
    if ga and hotfix is None:
        return {
            **out,
            "result": "ask",
            "reason": f"the changed code is on released line(s) {_rel(ga)}{why}",
            "question": {
                "key": "hotfix",
                "text": f"Is this a hotfix or vulnerability fix that {_rel(ga)} must get as a patch release?",
                "answers": {"yes": yes, "no": no},
            },
            "next": {
                a: f"{SELF} {_target(pr)} --answer hotfix={a}" for a in ("yes", "no")
            },
        }
    if ga and hotfix:
        return {
            **out,
            "result": "suggest",
            "label": yes,
            "reason": f"a hotfix for released line(s) {_rel(ga)}; each pick there is confirmed before Promote{why}",
        }
    reason = (
        f"the changed code is on {_rel(rc)}, still awaiting GA; the oldest is release/{rc[-1]}{why}"
        if rc
        else f"not a hotfix, and every line with the code is released{why}"
    )
    return {**out, "result": "suggest", "label": no, "reason": reason}


def _rel(lines):
    return ", ".join(f"release/{l}" for l in lines)


def code(paths):
    return [p for p in paths if not NONCODE.search(p)]


def _target(pr):
    return f"--pr {pr}" if isinstance(pr, int) else f"--branch {pr}"


def _gh(*args):
    return bp.gh(*args, retry=False)


def slug_from_origin():
    url = rm.git(".", "remote", "get-url", "origin")
    m = re.search(r"github\.com[:/]([^/]+/[^/]+?)(?:\.git)?/?$", url)
    if not m:
        raise Usage(f"origin is not a GitHub repo: {url}")
    return m[1]


def live_lines(slug):
    return rm.active_lines(slug, _gh)


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


def old_ranges(patch):
    """Old-side lines a unified diff changes: each removed or replaced line, and for an insertion, which has no old
    line of its own, the unchanged line on each side of it. A new file gives none.
    """
    lines = set()
    parts = HUNK_RE.split(patch or "")[1:]
    for n, body in zip(parts[::2], parts[1::2], strict=True):
        n, prev = int(n), ""
        for row in body.split("\n"):
            tag = row[:1]
            if tag == "-":
                lines.add(n)
            elif tag == "+" and prev != "-":
                lines.update(i for i in (n - 1, n) if i > 0)
            if tag in (" ", "-"):
                n, prev = n + 1, tag
    out = []
    for i in sorted(lines):
        if out and out[-1][1] == i - 1:
            out[-1] = (out[-1][0], i)
        else:
            out.append((i, i))
    return out


BLAME_Q = """query($owner: String!, $name: String!, $oid: GitObjectID!, $path: String!) {
  repository(owner: $owner, name: $name) { object(oid: $oid) { ... on Commit { blame(path: $path) {
    ranges { startingLine endingLine commit { oid } } } } } } }"""


def blame(slug, base, path, ranges):
    """Commits behind the old-side lines ranges of path at base."""
    owner, name = slug.split("/")
    data = json.loads(
        _gh(
            "api",
            "graphql",
            "-f",
            f"query={BLAME_Q}",
            "-f",
            f"owner={owner}",
            "-f",
            f"name={name}",
            "-f",
            f"oid={base}",
            "-f",
            f"path={path}",
        )
    )
    rows = data["data"]["repository"]["object"]["blame"]["ranges"]
    return {
        r["commit"]["oid"]
        for r in rows
        for a, b in ranges
        if r["startingLine"] <= b and a <= r["endingLine"]
    }


def on_line(slug, sha, line):
    cmp = json.loads(
        _gh("api", f"repos/{slug}/compare/release/{line}...{sha}", "--jq", "{status}")
    )
    return cmp["status"] in ("behind", "identical")


def picks(slug, line):
    """SHAs that Backport picked onto release/X.Y since its cut: a picked commit has a new SHA, so ancestry misses it."""
    out = _gh(
        "api",
        "--paginate",
        f"repos/{slug}/compare/main...release/{line}",
        "--jq",
        ".commits[].commit.message | @json",
    )
    msgs = [json.loads(m) for m in out.splitlines()]
    # A decline is an empty commit that keeps the pick's trailer: the code never landed.
    return {
        s for m in msgs if not rm.DECLINED_RE.search(m) for s in rm.PICK_RE.findall(m)
    }


def line_facts(slug, base, patches, need_ga=True):
    """(lines, how). Blame the lines a change touches at its base and test whether those commits are on each line;
    when it cannot, fall back to whether a changed file exists there, and say so.
    """
    changed = {p: t for p, t in patches.items() if p in code(patches)}
    touched = {p: r for p, t in changed.items() if (r := old_ranges(t))}
    commits, how = None, ""
    # GitHub sends no patch for a large or binary file, so blame cannot see what it changes.
    if nodiff := sorted(p for p, t in changed.items() if t is None):
        how = f"by file path: GitHub sends no diff for {nodiff[0]}"
    elif not touched:
        how = "by file path: the change only adds new files, so blame cannot tell"
    elif len(touched) > BLAME_MAX:
        how = f"by file path: {len(touched)} files is past the blame limit of {BLAME_MAX}"
    else:
        try:
            commits = set().union(*(blame(slug, base, p, r) for p, r in touched.items()))
            how = f"blame: {len(commits)} commit(s) behind the changed lines"
        except (
            RuntimeError,
            KeyError,
            TypeError,
            ValueError,
        ) as e:  # ValueError: unreadable JSON
            how = f"by file path: blame failed ({e})"
    out = []
    for line in live_lines(slug):
        if commits is not None:
            # ponytail: one compare per (commit, line) where the code is absent; cap commits if Lint's API budget bites.
            # A trailer may be abbreviated; blame gives full SHAs.
            done = tuple(picks(slug, line))
            present = any(c.startswith(done) for c in commits) or any(
                on_line(slug, c, line) for c in commits
            )
        else:
            files = tree(slug, line)
            present = (
                None if files is None else any(p in files for p in changed)
            )  # truncated: cannot tell
        out.append(
            {
                "line": line,
                "present": present,
                "ga": present and need_ga and has_ga(slug, line),
            }
        )
    return out, how


def pr_facts(slug, n):
    pr = json.loads(_gh("api", f"repos/{slug}/pulls/{n}"))
    files = json.loads(
        _gh("api", "--paginate", "--slurp", f"repos/{slug}/pulls/{n}/files?per_page=100")
    )
    patches = {}
    for page in files:
        for f in page:
            prev = f.get("previous_filename")
            # A renamed file's patch is blamed at its old path: the new one is not at the base.
            patches[f["filename"]] = "" if prev else f.get("patch")
            if prev:
                patches.setdefault(prev, f.get("patch"))
    return pr, patches


def advise_pr(slug, n, hotfix=None, pr=None, patches=None, need_ga=True, line=None):
    """Advice for PR n. Lint PR passes need_ga=False on its success path: only the decided results matter there."""
    if pr is None:
        pr, patches = pr_facts(slug, n)
    base = pr["base"]["ref"]
    lines, how = [], ""
    if code(patches) and not base.startswith("release/"):
        # The PR's patch line numbers are relative to its merge base.
        mb = _gh(
            "api",
            f"repos/{slug}/compare/{pr['base']['sha']}...{pr['head']['sha']}",
            "--jq",
            ".merge_base_commit.sha",
        ).strip()
        lines, how = line_facts(slug, mb, patches, need_ga)
    paths = sorted(patches)
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
    adv = advise(base, paths, lines, hotfix, n, pr["head"]["ref"], picks, how, line)
    have = {l["name"] for l in pr.get("labels", [])}
    if adv["label"] and adv["result"] != "ask" and adv["label"] not in have:
        others = sorted(
            l
            for l in have
            if l in (MAIN_ONLY, RBO, *rm.RETIRED_LABELS) or rm.LINE_LABEL_RE.fullmatch(l)
        )
        cmds = [
            f"gh api -X DELETE repos/{slug}/issues/{n}/labels/{urllib.parse.quote(o, safe='')}"
            for o in others
        ]
        adv["next"] = " && ".join(
            [*cmds, f"gh api repos/{slug}/issues/{n}/labels -f 'labels[]={adv['label']}'"]
        )
    return {"repo": slug, "pr": n, **adv}


def advise_branch(slug, ref, hotfix=None, line=None):
    base = rm.git(".", "merge-base", "origin/main", ref)
    patches = {}
    for chunk in rm.git(".", "diff", "-U0", "--no-renames", base, ref).split(
        "diff --git "
    )[1:]:
        path = chunk.split("\n", 1)[0].split(" b/", 1)[-1]
        patches[path] = chunk
    lines, how = line_facts(slug, base, patches) if code(patches) else ([], "")
    return {
        "repo": slug,
        "pr": None,
        **advise("main", sorted(patches), lines, hotfix, ref, how=how, line=line),
    }


def owed(slug, author):
    """[{line, pr, title, why, command}] for author's merged PRs that a live line still owes, from local origin refs: main() fetches them first."""
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
        cmd = f"gh workflow run backport.yaml -R {slug} -f commits={{}} -f lines={line} -f patch_released_lines=true"
        # Backport's `held:` count: a developer reading the answer cannot act on it, but can on a warning.
        log = sys.stderr if os.environ.get("GITHUB_ACTIONS") else io.StringIO()
        try:
            with contextlib.redirect_stdout(log):
                held = bp.held(slug, ".", branch, cache=bp.pr_classes(slug, since))
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
                        "why": f"label backport/{cls}"
                        if cls != bp.UNCLASSIFIABLE
                        else cls,
                        "command": cmd.format(pr[1:]),
                    }
                )
    return rows


def render(adv):
    where = f"#{adv['pr']}" if adv["pr"] else "this branch"
    if adv["result"] == "ask":
        q = adv["question"]
        text = f"{where}: one question — {q['text']}\n  ({adv['reason']})" + "".join(
            f"\n  {k}: {v}, then: {adv['next'][k]}" for k, v in q["answers"].items()
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
    ap.add_argument(
        "--answer",
        action="append",
        default=[],
        metavar="hotfix=yes|no|line=X.Y|main-only",
    )
    ap.add_argument("--author")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)
    try:
        modes = [
            m
            for m, on in (
                ("--pr", a.pr is not None),
                ("--branch", a.branch),
                ("--owed", a.owed),
            )
            if on
        ]
        if len(modes) != 1:
            raise Usage("use one of --pr N, --branch REF, --owed")
        answers = dict(x.split("=", 1) for x in a.answer if "=" in x)
        if (
            len(answers) != len(a.answer)
            or set(answers) - {"hotfix", "line"}
            or answers.get("hotfix", "yes") not in ("yes", "no")
            or not (
                answers.get("line", MAIN_ONLY) == MAIN_ONLY
                or rm.LINE_RE.fullmatch(answers["line"])
            )
        ):
            raise Usage(
                f"--answer takes hotfix=yes|no or line=X.Y|main-only, got {a.answer}"
            )
        hotfix = None if "hotfix" not in answers else answers["hotfix"] == "yes"
        line = answers.get("line")
        slug = slug_from_origin()
        rs.use(slug.split("/")[1].lower())
        if a.pr is not None:
            adv = advise_pr(slug, a.pr, hotfix, line=line)
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
            adv = advise_branch(slug, a.branch, hotfix, line)
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
