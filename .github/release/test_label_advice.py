"""Tests for label_advice, the Backport-also declaration rule and backport.declared(). Run: python test_label_advice.py"""

import json
import os
import tempfile
import unittest
from unittest import mock

os.environ["GITHUB_REPOSITORY"] = (
    "Zipstack/unstract-cloud"  # pin relstate to the cloud config
)
import backport as bp
import label_advice as la
import relmgr as rm


def dev_git(repo, *a):
    return rm.git(repo, "-c", "user.name=Dev", "-c", "user.email=dev@example.com", *a)


class Declaration(unittest.TestCase):
    def test_well_formed_lines_only(self):
        body = "Fixes the parser.\r\n\r\nBackport-also: 0.186\r\nBackport-also: 0.188  \nBackport-also: 0.19x\n"
        self.assertEqual(rm.declared_lines(body), {"0.186", "0.188"})
        self.assertEqual(rm.declared_lines(None), set())

    def test_malformed_lines_are_errors(self):
        body = (
            "Backport-also: 0.186\n"
            "backport-also: 0.188\n"
            "Backport-also: release/0.188\n"
            "- Backport also: 0.188\n"
            "Backport-also: 0.186, 0.188\n"
            "We could backport also later.\n"  # prose without a colon is not an attempt
        )
        self.assertEqual(
            rm.declaration_errors(body),
            [
                "backport-also: 0.188",
                "Backport-also: release/0.188",
                "- Backport also: 0.188",
                "Backport-also: 0.186, 0.188",
            ],
        )
        self.assertEqual(rm.declaration_errors("Backport-also: 0.186\r\n"), [])


class Repo(unittest.TestCase):
    """An origin with main and release/1.7 cut from it, and a clone."""

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        origin, self.repo = os.path.join(tmp.name, "o.git"), os.path.join(tmp.name, "w")
        rm.git(tmp.name, "init", "-q", "--bare", "-b", "main", origin)
        rm.git(tmp.name, "clone", "-q", origin, self.repo)
        self.before = self.commit("before the cut")
        dev_git(self.repo, "push", "-q", "origin", "main", "main:refs/heads/release/1.7")
        self.prs = []

    def commit(self, msg):
        dev_git(self.repo, "commit", "-q", "--allow-empty", "-m", msg)
        return rm.git(self.repo, "rev-parse", "HEAD")

    def pr(self, n, sha, body, title=None):
        self.prs.append(
            {
                "number": n,
                "title": title or f"[FIX] fix {n}",
                "body": body,
                "mergeCommit": {"oid": sha} if sha else None,
            }
        )


class Declared(Repo):
    """Real git; the gh PR listing is mocked with `gh pr list --json number,title,body,mergeCommit` rows."""

    def declared(self, fail=False):
        dev_git(self.repo, "push", "-q", "origin", "main")
        dev_git(self.repo, "fetch", "-q", "origin")
        gh = mock.Mock(
            side_effect=RuntimeError("gh pr list (exit 1): HTTP 502") if fail else None,
            return_value=json.dumps(self.prs),
        )
        with mock.patch.object(bp, "gh", gh):
            return bp.declared("o/r", self.repo, "release/1.7", token="t"), gh

    def test_only_owed_well_formed_declarations_for_this_line(self):
        owed = self.commit("[FIX] owed (#11)")
        self.pr(11, owed, "x\r\n\r\nBackport-also: 1.7\r\n")
        picked = self.commit("[FIX] picked (#12)")
        self.pr(12, picked, "Backport-also: 1.7")
        self.pr(13, self.commit("[FIX] other line (#13)"), "Backport-also: 1.9")
        self.pr(14, self.commit("[FIX] retired line (#14)"), "Backport-also: 1.5")
        self.pr(15, self.commit("[FIX] malformed (#15)"), "Backport-also: release/1.7")
        self.pr(16, None, "Backport-also: 1.7")  # no merge commit: never merged
        self.pr(
            17, self.before, "Backport-also: 1.7"
        )  # merged before the cut: already on the line
        copied = self.commit("[FIX] body copied from #11 (#18)")
        self.pr(18, copied, "x\n\nBackport-also: 1.7\n")
        by_sha = self.commit("[FIX] reverted by sha (#19)")
        self.pr(19, by_sha, "Backport-also: 1.7")
        self.commit(
            f'Revert "[FIX] reverted by sha" (#20)\n\n* Revert\n\nThis reverts commit {by_sha}.'
        )
        self.pr(
            21,
            self.commit("[FIX] reverted by title (#21)"),
            "Backport-also: 1.7",
            "[FIX] reverted by title",
        )
        self.commit(
            'Revert "[FIX] reverted by title" (#22)\n\nReverts Zipstack/unstract-cloud#21'
        )
        dev_git(self.repo, "push", "-q", "origin", "main")
        line = os.path.join(os.path.dirname(self.repo), "line")
        rm.git(
            os.path.dirname(self.repo),
            "clone",
            "-q",
            "-b",
            "release/1.7",
            os.path.join(os.path.dirname(self.repo), "o.git"),
            line,
        )
        dev_git(line, "cherry-pick", "-x", "--allow-empty", picked)
        dev_git(line, "push", "-q", "origin", "release/1.7")
        got, gh = self.declared()
        # A copied body declares for the PR that carries it: the documented way out is removing the line.
        self.assertEqual(got, [(11, "[FIX] fix 11"), (18, "[FIX] fix 18")])
        args = gh.call_args
        self.assertEqual(args.kwargs, {"token": "t"})
        self.assertIn("--state", args.args)
        self.assertEqual(args.args[args.args.index("--state") + 1], "merged")

    def test_listing_failure_raises(self):
        self.pr(11, self.commit("[FIX] owed (#11)"), "Backport-also: 1.7")
        with self.assertRaises(RuntimeError):
            self.declared(fail=True)

    def test_content_without_a_trailer_still_blocks(self):
        """A fix that reached the line by hand, without `-x`, has no trailer: it stays declared until the line goes."""
        sha = self.commit("[FIX] hand-copied (#11)")
        self.pr(11, sha, "Backport-also: 1.7")
        got, _ = self.declared()
        self.assertEqual(got, [(11, "[FIX] fix 11")])


class Owed(Repo):
    def owed(self):
        dev_git(self.repo, "fetch", "-q", "origin", "--tags")
        held = mock.Mock(
            return_value=[
                ("a" * 40, "fix", "#11", "mine"),
                ("b" * 40, "fix", "#99", "theirs"),
            ]
        )
        mine = json.dumps([{"number": 11}, {"number": 12}])
        old = os.getcwd()
        os.chdir(self.repo)
        try:
            with (
                mock.patch.object(bp, "held", held),
                mock.patch.object(bp, "pr_classes", return_value={"c": 1}),
                mock.patch.object(
                    bp, "declared", return_value=[(12, "declared"), (98, "theirs")]
                ),
                mock.patch.object(la, "_gh", return_value=mine) as gh,
            ):
                return la.owed("o/r", "dev"), held, gh
        finally:
            os.chdir(old)

    def test_only_the_authors_prs_and_what_backport_would_pick(self):
        rows, held, gh = self.owed()
        self.assertEqual(
            [(r["pr"], r["why"]) for r in rows],
            [("#11", "label class fix"), ("#12", "Backport-also: 1.7")],
        )
        self.assertEqual(
            rows[1]["command"],
            "gh workflow run backport.yaml -R o/r -f commits=12 -f lines=1.7 -f patch_released_lines=true",
        )
        self.assertEqual(held.call_args.kwargs, {"accept": bp.OWED, "cache": {"c": 1}})
        self.assertIn("--author", gh.call_args.args)
        self.assertEqual(
            gh.call_args.args[gh.call_args.args.index("--author") + 1], "dev"
        )
        dev_git(self.repo, "tag", "v1.7.0", "origin/release/1.7")
        dev_git(self.repo, "push", "-q", "origin", "v1.7.0")
        _, held, _ = self.owed()
        self.assertEqual(
            held.call_args.kwargs["accept"], bp.HELD
        )  # released: only held fixes are owed


def line(v, present=True, ga=False, onprem_ga=False):
    return {"line": v, "present": present, "ga": ga, "onprem_ga": onprem_ga}


class Advise(unittest.TestCase):
    def test_release_base_is_release_branch_only(self):
        a = la.advise("release/0.186", ["backend/x.py"], [])
        self.assertEqual((a["result"], a["label"]), ("decided", "release-branch-only"))
        a = la.advise(
            "release/0.186", ["backend/x.py"], [], head="backport/0.186/abcdef1"
        )
        self.assertEqual((a["result"], a["label"]), ("decided", None))

    def test_only_repo_tooling_docs_or_tests_is_main_only(self):
        for paths in (
            [".github/workflows/x.yaml"],
            ["docs/a.md", "backend/tests/test_x.py", "README.md"],
            [".github/release/relmgr.py", "frontend/src/a.test.js"],
        ):
            a = la.advise("main", paths, [line("0.186")])
            self.assertEqual((a["result"], a["label"]), ("decided", "main-only"), paths)

    def test_code_on_no_live_line_is_main_only(self):
        a = la.advise(
            "main",
            ["backend/new.py"],
            [line("0.186", present=False), line("0.188", present=False)],
        )
        self.assertEqual((a["result"], a["label"]), ("decided", "main-only"))
        self.assertEqual(la.advise("main", ["backend/new.py"], [])["label"], "main-only")

    def test_code_on_a_line_awaiting_ga_suggests_rc(self):
        a = la.advise(
            "main",
            ["backend/x.py"],
            [line("0.188"), line("0.186", present=False)],
            "[FIX] x",
        )
        self.assertEqual(
            (a["result"], a["label"], a["info"]), ("suggest", "backport/rc", [])
        )
        a = la.advise("main", ["backend/x.py"], [line("0.188")], "UN-1 [FEAT] x")
        self.assertIn("a FEAT usually stays main-only", a["reason"])

    def test_released_line_asks_the_hotfix_question(self):
        lines = [line("0.188"), line("0.186", ga=True, onprem_ga=True)]
        a = la.advise("main", ["backend/x.py"], lines, "[FIX] x", pr=7)
        self.assertEqual(a["result"], "ask")
        self.assertEqual(
            a["question"]["answers"], {"yes": "backport/ga", "no": "backport/rc"}
        )
        self.assertEqual(a["next"], f"{la.SELF} --pr 7 --answer hotfix=yes|no")
        self.assertEqual(a["info"], [])  # on-prem GA confirmed: nothing mixed
        self.assertEqual(
            la.advise("main", ["backend/x.py"], lines, hotfix=True)["label"],
            "backport/ga",
        )
        self.assertEqual(
            la.advise("main", ["backend/x.py"], lines, hotfix=False)["label"],
            "backport/rc",
        )
        only_ga = [line("0.186", ga=True, onprem_ga=True)]
        self.assertEqual(
            la.advise("main", ["backend/x.py"], only_ga)["question"]["answers"]["no"],
            "main-only",
        )
        self.assertEqual(
            la.advise("main", ["backend/x.py"], only_ga, hotfix=False)["label"],
            "main-only",
        )

    def test_mixed_line_is_one_note_never_a_question(self):
        for onprem in (False, None):  # not GA for on-prem, or unknown
            lines = [line("0.186", ga=True, onprem_ga=onprem)]
            a = la.advise("main", ["backend/x.py"], lines, pr=7, hotfix=False)
            self.assertEqual(a["result"], "suggest")
            self.assertEqual(len(a["info"]), 1)
            self.assertEqual(a["info"][0]["line"], "0.186")
            self.assertEqual(a["info"][0]["command"], f"{la.SELF} --declare 0.186 --pr 7")
        a = la.advise(
            "main", ["backend/x.py"], [line("0.186", ga=True)], pr=7, hotfix=True
        )
        self.assertEqual(a["info"], [])  # backport/ga already reaches the line
        a = la.advise(
            "main", ["backend/x.py"], [line("0.186", present=False, ga=True)], pr=7
        )
        self.assertEqual(
            (a["label"], a["info"]), ("main-only", [])
        )  # code not there: nothing to declare


class AdvisePr(unittest.TestCase):
    def test_next_applies_the_label_and_drops_the_others(self):
        pr = {
            "base": {"ref": "main"},
            "head": {"ref": "dev"},
            "title": "[DOCS] x",
            "labels": [{"name": "backport/rc"}, {"name": "bug"}],
        }
        a = la.advise_pr("o/r", 5, pr=pr, paths=["docs/x.md"])
        self.assertEqual(a["label"], "main-only")
        self.assertEqual(
            a["next"],
            "gh api -X DELETE repos/o/r/issues/5/labels/backport%2Frc && "
            "gh api repos/o/r/issues/5/labels -f 'labels[]=main-only'",
        )
        pr["labels"] = [{"name": "main-only"}]
        self.assertIsNone(la.advise_pr("o/r", 5, pr=pr, paths=["docs/x.md"])["next"])


class Cli(unittest.TestCase):
    def test_bad_input_exits_2(self):
        for argv in (
            [],
            ["--pr", "1", "--owed"],
            ["--declare", "0.186"],
            ["--pr", "1", "--answer", "hotfix=maybe"],
            ["--pr", "1", "--answer", "mixed=yes"],
        ):
            with mock.patch("sys.stderr"):
                self.assertEqual(la.main(argv), 2, argv)

    def test_lookup_failure_exits_1(self):
        with (
            mock.patch.object(
                la, "slug_from_origin", return_value="Zipstack/unstract-cloud"
            ),
            mock.patch.object(
                la, "_gh", side_effect=RuntimeError("gh api (exit 1): HTTP 502")
            ),
            mock.patch("sys.stderr"),
        ):
            self.assertEqual(la.main(["--pr", "1"]), 1)


if __name__ == "__main__":
    unittest.main()
