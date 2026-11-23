#!/usr/bin/env python3
"""One-time switch from `backport/rc` and `backport/ga` to line labels. Prints the plan; --apply runs it.

  relabel_line_labels.py --rc X.Y --ga X.Y --since YYYY-MM-DD [--repo SLUG ...] [--apply]

--rc: the oldest line in RC (stabilizing) at switch time, or main-only when no line is in RC. --ga: the oldest
supported line (stabilizing or stabilized). --since: a day before the cut of the oldest supported line; the State
run classes every PR merged into main since then from its labels, read live, so those PRs and every open PR into
main are relabelled. Creates `backport/X.Y` for each active line first, and re-describes the retired labels
rather than deleting them. A PR that already has a line label only loses its old ones. If adding a PR's new label
fails, its old ones stay.

Order: create the line labels by hand, merge this code in both repos, then run --apply at once. The old code
refuses `backport/X.Y` and the new code refuses the old labels, so rescans and State runs fail in between; re-run
them after --apply.
"""

import argparse
import json
import shlex
import subprocess
import sys

import relmgr as rm

REPOS = ("Zipstack/unstract-cloud", "Zipstack/unstract")
RETIRED_DESC = (
    "Retired: label the oldest release line that needs the fix, as backport/X.Y"
)


def gh(*args):
    r = subprocess.run(["gh", *args], capture_output=True, text=True)
    if r.returncode:
        raise RuntimeError(f"gh {' '.join(args)}: {r.stderr.strip()}")
    return r.stdout


def prs(slug, search):
    out = gh(
        "pr",
        "list",
        "-R",
        slug,
        "--base",
        "main",
        "--state",
        "all",
        "--search",
        search,
        "--limit",
        "1000",
        "--json",
        "number,title,state,labels",
    )
    return json.loads(out)


def plan(slug, mapping, since):
    """[(argv, why)] for one repo."""
    steps, active = [], rm.active_lines(slug, gh)
    stray = sorted(set(mapping.values()) - set(active) - {rm.MAIN_ONLY})
    if stray:
        raise SystemExit(
            f"{', '.join(stray)} is not an active line in {slug} ({', '.join(active)})"
        )
    for line in active:
        steps.append(
            (
                (
                    "label",
                    "create",
                    f"backport/{line}",
                    "-R",
                    slug,
                    "--color",
                    "0e8a16",
                    "--description",
                    f"Also copy to release/{line} and every newer active line",
                ),
                "line label",
            )
        )
    seen = set()
    for search in ("is:open", f"is:merged merged:>={since}"):
        for p in prs(slug, search):
            names = {l["name"] for l in p["labels"]}
            old = sorted(names & set(mapping))
            if not old or p["number"] in seen:
                continue
            seen.add(p["number"])
            why = f"{p['state'].lower()} #{p['number']} {p['title']}"
            if not any(rm.LINE_LABEL_RE.fullmatch(n) for n in names):
                # Both old labels: the oldest line either names wins, since a label covers every newer line.
                lines = [mapping[o] for o in old if mapping[o] != rm.MAIN_ONLY]
                new = f"backport/{min(lines, key=rm._vkey)}" if lines else rm.MAIN_ONLY
                # REST, not `gh pr edit`: that one fails on these repos' deprecated project cards.
                steps.append(
                    (
                        (
                            "api",
                            f"repos/{slug}/issues/{p['number']}/labels",
                            "-f",
                            f"labels[]={new}",
                        ),
                        why,
                    )
                )
            for o in old:
                steps.append(
                    (
                        (
                            "api",
                            "-X",
                            "DELETE",
                            f"repos/{slug}/issues/{p['number']}/labels/{o.replace('/', '%2F')}",
                        ),
                        why,
                    )
                )
    for old in mapping:
        steps.append(
            (
                ("label", "edit", old, "-R", slug, "--description", RETIRED_DESC),
                "retired label",
            )
        )
    return steps


def main(argv=None):
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--rc", required=True, metavar="X.Y|main-only")
    ap.add_argument("--ga", required=True, metavar="X.Y")
    ap.add_argument("--since", required=True, metavar="YYYY-MM-DD")
    ap.add_argument("--repo", action="append", help="default: both repos")
    ap.add_argument("--apply", action="store_true")
    a = ap.parse_args(argv)
    if not rm.LINE_RE.fullmatch(a.ga) or not (
        rm.LINE_RE.fullmatch(a.rc) or a.rc == rm.MAIN_ONLY
    ):
        ap.error("--rc takes X.Y or main-only, --ga takes X.Y")
    mapping = {"backport/rc": a.rc, "backport/ga": a.ga}
    failed, unlabelled = 0, set()
    for slug in a.repo or REPOS:
        for args, why in plan(slug, mapping, a.since):
            print(f"{shlex.join(['gh', *args])}  # {why}")
            if not a.apply:
                continue
            if "DELETE" in args and why in unlabelled:
                print(
                    "  skipped: the new label was not added, so the old one stays",
                    file=sys.stderr,
                )
                continue
            try:
                gh(*args)
            except RuntimeError as e:
                if "already exists" not in str(e):
                    print(f"  failed: {e}", file=sys.stderr)
                    failed += 1
                    unlabelled.add(why)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
