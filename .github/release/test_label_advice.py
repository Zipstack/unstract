"""Tests for label_advice, the Backport-also declaration rule and backport.declared(). Run: python test_label_advice.py"""

import contextlib
import io
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
            "Backport-also: release/0.188\n"
            "1. Backport-also 0.188\n"
            "+ Backport-also: 0.186\n"
            "We could backport also later.\n"  # prose is not an attempt
        )
        self.assertEqual(
            rm.declaration_errors(body),
            [
                "Backport-also: release/0.188",
                "1. Backport-also 0.188",
                "+ Backport-also: 0.186",
            ],
        )

    def test_a_main_only_pr_cannot_declare(self):
        body = "x\n\nBackport-also: 0.186\n"
        [err] = rm.body_errors(body, ["main-only"])
        self.assertIn("Backport never picks a main-only PR", err)
        self.assertEqual(rm.body_errors(body, ["backport/rc"]), [])


class Repo(unittest.TestCase):
    """An origin with main and release/1.7 cut from it, and a clone."""

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.origin, self.repo = (
            os.path.join(tmp.name, "o.git"),
            os.path.join(tmp.name, "w"),
        )
        rm.git(tmp.name, "init", "-q", "--bare", "-b", "main", self.origin)
        rm.git(tmp.name, "clone", "-q", self.origin, self.repo)
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
        self.pr(14, self.commit("[FIX] declined (#14)"), "Declaration removed.")
        self.pr(16, None, "Backport-also: 1.7")  # no merge commit: never merged
        self.pr(
            17, self.before, "Backport-also: 1.7"
        )  # merged before the cut: already on the line
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
        got, _ = self.declared()
        self.assertEqual(got, [(11, "[FIX] fix 11")])

    def test_a_revert_counts_unless_itself_reverted(self):
        relanded = self.commit("[FIX] flaky (#11)")
        self.pr(11, relanded, "Backport-also: 1.7", "[FIX] flaky")
        self.commit('Revert "[FIX] flaky" (#12)')
        again = self.commit("[FIX] flaky (#13)")  # re-landed under the same title
        self.pr(13, again, "Backport-also: 1.7", "[FIX] flaky")
        back = self.commit("[FIX] back (#14)")
        self.pr(14, back, "Backport-also: 1.7", "[FIX] back")
        rev = self.commit(f'Revert "[FIX] back" (#15)\n\nThis reverts commit {back}.')
        self.commit(f'Revert "Revert "[FIX] back"" (#16)\n\nThis reverts commit {rev}.')
        twice = self.commit("[FIX] twice (#18)")
        self.pr(18, twice, "Backport-also: 1.7", "[FIX] twice")
        rev = self.commit(f'Revert "[FIX] twice" (#19)\n\nThis reverts commit {twice}.')
        self.commit(f'Revert "Revert "[FIX] twice"" (#20)\n\nThis reverts commit {rev}.')
        self.commit(f'Revert "[FIX] twice" (#21)\n\nThis reverts commit {twice}.')
        same = self.commit("[FIX] same title (#22)")
        self.pr(22, same, "Backport-also: 1.7", "[FIX] same title")
        other = self.commit("[FIX] same title (#23)")
        self.commit(f'Revert "[FIX] same title" (#24)\n\nThis reverts commit {other}.')
        # A revert that reaches main off its first-parent line (a merge-back) does not undo a main fix.
        side = self.commit("[FIX] kept (#17)")
        self.pr(17, side, "Backport-also: 1.7", "[FIX] kept")
        dev_git(self.repo, "checkout", "-q", "-b", "side", side)
        # Dated later, so only --first-parent, not log order, keeps it out.
        with mock.patch.dict(os.environ, GIT_COMMITTER_DATE="2099-01-01T00:00:00Z"):
            self.commit(f'Revert "[FIX] kept"\n\nThis reverts commit {side}.')
        dev_git(self.repo, "checkout", "-q", "main")
        dev_git(self.repo, "merge", "-q", "--no-ff", "-m", "merge back", "side")
        got, _ = self.declared()
        self.assertEqual(
            got,
            [
                (13, "[FIX] flaky"),
                (14, "[FIX] back"),
                (22, "[FIX] same title"),
                (17, "[FIX] kept"),
            ],
        )

    def test_a_commit_missing_from_the_fetched_main_fails_closed(self):
        self.pr(11, "f" * 40, "Backport-also: 1.7")
        with self.assertRaisesRegex(RuntimeError, "not in the fetched main"):
            self.declared()

    def test_search_starts_a_day_before_the_cut(self):
        """GitHub reads `merged:>=D` as UTC; a cut at 02:49 +0530 is the previous UTC day."""
        with mock.patch.dict(os.environ, GIT_COMMITTER_DATE="2026-10-31T02:49:30+05:30"):
            self.commit("cut")
        cut = rm.git(self.repo, "rev-parse", "HEAD")
        self.assertEqual(bp.search_since(self.repo, cut), "2026-10-30")

    def test_listing_failure_raises(self):
        self.pr(11, self.commit("[FIX] owed (#11)"), "Backport-also: 1.7")
        with self.assertRaises(RuntimeError):
            self.declared(fail=True)


class Owed(Repo):
    def owed(self, run_log=None):
        dev_git(self.repo, "fetch", "-q", "origin", "--tags")

        def default_log(*a, **k):
            print(
                "held: 26 main commit(s) since the cut of release/1.7, 1 fix_class lookup(s)"
            )
            return [
                ("a" * 40, "fix", "#11", "mine"),
                ("b" * 40, "fix", "#99", "theirs"),
            ]

        held = mock.Mock(side_effect=run_log or default_log)
        mine = json.dumps([{"number": 11}, {"number": 12}])
        old = os.getcwd()
        os.chdir(self.repo)
        try:
            with (
                mock.patch.object(bp, "held", held),
                mock.patch.object(bp, "pr_classes", return_value={"c": 1}),
                mock.patch.object(
                    bp,
                    "declared",
                    return_value=[(11, "mine"), (12, "declared"), (98, "theirs")],
                ),
                mock.patch.object(la, "_gh", return_value=mine) as gh,
            ):
                return la.owed("o/r", "dev"), held, gh
        finally:
            os.chdir(old)

    def test_only_the_authors_prs_and_what_backport_would_pick(self):
        dev_git(
            self.repo, "branch", "release/1.5", "main"
        )  # local only: origin has no 1.5
        rows, held, _ = self.owed()
        self.assertEqual(
            [(r["pr"], r["why"]) for r in rows],
            [("#11", "label class fix"), ("#12", "Backport-also: 1.7")],
        )
        self.assertEqual(
            rows[1]["command"],
            "gh workflow run backport.yaml -R o/r -f commits=12 -f lines=1.7 -f patch_released_lines=true",
        )
        self.assertEqual(held.call_args.kwargs["accept"], bp.OWED)
        dev_git(self.repo, "tag", "v1.7.0", "origin/release/1.7")
        dev_git(self.repo, "push", "-q", "origin", "v1.7.0")
        _, held, _ = self.owed()
        self.assertEqual(
            held.call_args.kwargs["accept"], bp.HELD
        )  # released: only held fixes are owed

    def test_backports_run_log_shows_only_under_actions(self):
        for env, shown in (({}, False), ({"GITHUB_ACTIONS": "true"}, True)):
            out, err = io.StringIO(), io.StringIO()
            with (
                mock.patch.dict(os.environ),
                contextlib.redirect_stdout(out),
                contextlib.redirect_stderr(err),
            ):
                os.environ.pop("GITHUB_ACTIONS", None)  # CI runs this suite under Actions
                os.environ.update(env)
                self.owed()
            self.assertEqual(out.getvalue(), "")
            self.assertEqual("held: 26 main commit(s)" in err.getvalue(), shown, env)

    def test_backports_warnings_show_even_when_it_fails(self):
        def fail(*a, **k):
            print("::warning::PR listing failed, classing commit by commit: HTTP 403")
            print("  second line of gh's stderr")
            raise RuntimeError("HTTP 403")

        err = io.StringIO()
        with (
            mock.patch.dict(os.environ),
            contextlib.redirect_stderr(err),
        ):
            os.environ.pop("GITHUB_ACTIONS", None)
            with self.assertRaisesRegex(RuntimeError, "HTTP 403"):
                self.owed(fail)
        self.assertIn("::warning::PR listing failed", err.getvalue())
        self.assertIn("second line of gh's stderr", err.getvalue())


def line(v, present=True, ga=False, onprem_ga=False):
    return {"line": v, "present": present, "ga": ga, "onprem_ga": onprem_ga}


class Advise(unittest.TestCase):
    def test_a_cherry_pick_into_a_release_line_is_only_suggested(self):
        a = la.advise("release/0.186", ["backend/x.py"], [], picks=True)
        self.assertEqual((a["result"], a["label"]), ("suggest", "release-branch-only"))

    def test_a_pr_with_a_pick_trailer_into_a_release_line_is_only_suggested(self):
        pr = {"base": {"ref": "release/0.186"}, "head": {"ref": "fix-x"}, "labels": []}
        for msg, result in (
            ("x\n\n(cherry picked from commit abc1234)", "suggest"),
            ("x", "decided"),
        ):
            commits = json.dumps([[{"commit": {"message": msg}}]])
            with mock.patch.object(la, "_gh", return_value=commits):
                a = la.advise_pr("o/r", 7, pr=pr, paths=["backend/x.py"])
            self.assertEqual((a["result"], a["label"]), (result, "release-branch-only"))

    def test_release_base_is_release_branch_only(self):
        a = la.advise("release/0.186", ["backend/x.py"], [])
        self.assertEqual((a["result"], a["label"]), ("decided", "release-branch-only"))
        a = la.advise(
            "release/0.186", ["backend/x.py"], [], head="backport/0.186/abcdef1"
        )
        self.assertEqual((a["result"], a["label"]), ("decided", None))

    def test_only_repo_tooling_docs_or_tests_is_main_only(self):
        paths = [".github/workflows/x.yaml", "docs/a.md", "backend/tests/test_x.py"]
        a = la.advise("main", paths, [line("0.186")])
        self.assertEqual((a["result"], a["label"]), ("decided", "main-only"))
        a = la.advise("main", paths + ["backend/x.py"], [line("0.186")])
        self.assertEqual(a["result"], "suggest")  # one shipped file: not decided

    def test_nested_markdown_ships_unless_it_is_a_readme(self):
        lines = [line("0.186", ga=True)]
        a = la.advise(
            "main", ["workers/plugins/agentic_table_engine/src/prompts/x.md"], lines
        )
        self.assertEqual(a["result"], "ask")
        a = la.advise("main", ["backend/global_search/README.md"], lines)
        self.assertEqual((a["result"], a["label"]), ("decided", "main-only"))

    def test_agent_tooling_and_root_markdown_are_main_only(self):
        for path in (
            ".claude/plugins/devkit/.claude-plugin/plugin.json",
            ".claude-plugin/marketplace.json",
            "CLAUDE.md",
        ):
            a = la.advise("main", [path], [line("0.186", ga=True)])
            self.assertEqual((a["result"], a["label"]), ("decided", "main-only"), path)

    def test_code_on_no_live_line_is_main_only(self):
        a = la.advise(
            "main",
            ["backend/new.py"],
            [line("0.186", present=False), line("0.188", present=False)],
        )
        self.assertEqual((a["result"], a["label"]), ("decided", "main-only"))

    def test_code_on_a_line_awaiting_ga_suggests_rc(self):
        a = la.advise(
            "main",
            ["backend/x.py"],
            [line("0.188"), line("0.186", present=False)],
        )
        self.assertEqual(
            (a["result"], a["label"], a["info"]), ("suggest", "backport/rc", [])
        )

    def test_released_line_asks_the_hotfix_question(self):
        lines = [line("0.188"), line("0.186", ga=True, onprem_ga=True)]
        a = la.advise("main", ["backend/x.py"], lines, pr=7)
        self.assertEqual(a["result"], "ask")
        self.assertEqual(
            a["question"]["answers"], {"yes": "backport/ga", "no": "backport/rc"}
        )
        # One runnable command per answer: no `yes|no` for a shell to read as a pipe.
        self.assertEqual(
            a["next"],
            {
                "yes": f"{la.SELF} --pr 7 --answer hotfix=yes",
                "no": f"{la.SELF} --pr 7 --answer hotfix=no",
            },
        )
        self.assertEqual(
            la.advise("main", ["backend/x.py"], lines, hotfix=True)["label"],
            "backport/ga",
        )

    def test_mixed_line_is_one_note_never_a_question(self):
        for onprem in (False, None):  # not GA for on-prem, or unknown
            lines = [line("0.186", ga=True, onprem_ga=onprem)]
            a = la.advise("main", ["backend/x.py"], lines, pr=7, hotfix=False)
            self.assertEqual(a["result"], "suggest")
            self.assertEqual(a["info"][0]["command"], f"{la.SELF} --declare 0.186 --pr 7")
            # Backport never picks main-only: the note routes through backport/rc.
            self.assertIn("label it `backport/rc` and declare it", a["info"][0]["text"])
            self.assertEqual("unknown" in a["info"][0]["text"], onprem is None, onprem)


class LineFacts(unittest.TestCase):
    """The facts advise() is fed, from mocked GitHub answers."""

    def gh(self, *args):
        url = next(a for a in args if a.startswith("repos/") or a == "list")
        if "branches?" in url:
            return "release/0.188\nrelease/0.186\nrelease/0.185\nmain"
        if "trees/release/0.188" in url:
            return json.dumps({"truncated": True, "tree": []})
        if "trees/" in url:
            return json.dumps({"truncated": False, "tree": [{"path": "backend/x.py"}]})
        if "tags/v0.186." in url:
            return json.dumps(
                [{"ref": "refs/tags/v0.186.0-rc.1"}, {"ref": "refs/tags/v0.186.0"}]
            )
        if "tags/v0.185." in url:
            return json.dumps([{"ref": "refs/tags/v0.185.0"}])
        if "tags/" in url:
            return json.dumps([{"ref": "refs/tags/v0.188.0-rc.3"}])
        if self.runs is None:
            raise RuntimeError("gh run (exit 1): HTTP 403")
        return json.dumps([{"displayTitle": t} for t in self.runs])

    def facts(self, runs):
        self.runs = runs
        with mock.patch.object(la, "_gh", side_effect=self.gh), mock.patch("sys.stderr"):
            return {f["line"]: f for f in la.line_facts("o/r", ["backend/x.py"])}

    def test_present_ga_and_onprem_ga(self):
        f = self.facts(
            [
                "Promote 0.186.0-rc.2 · cloud, on-prem (by dev)",  # dispatched without the v
                "Promote v0.185.0-rc.1 · cloud (by dev)",
            ]
        )
        self.assertTrue(f["0.188"]["present"])  # a truncated tree reads as present
        self.assertFalse(f["0.188"]["ga"])  # an RC tag is not GA
        self.assertEqual((f["0.186"]["ga"], f["0.186"]["onprem_ga"]), (True, True))
        self.assertEqual((f["0.185"]["ga"], f["0.185"]["onprem_ga"]), (True, False))
        f = self.facts(None)  # Promote runs unreadable
        self.assertIsNone(f["0.186"]["onprem_ga"])


class Declare(unittest.TestCase):
    """--declare: the one command that writes to GitHub."""

    def run_(self, body, labels=(), branch=None, after=None):
        self.patches = []

        def gh(*args):
            if "branches/release/1.7" in args[-1]:
                if branch:
                    raise RuntimeError(branch)
                return "{}"
            if "PATCH" in args:
                self.patches.append(args[-1])
                return "{}"
            reads = len(self.patches)
            b = (
                body
                if not reads
                else (after if after is not None else self.patches[-1][5:])
            )
            return json.dumps({"body": b, "labels": [{"name": l} for l in labels]})

        with (
            mock.patch.object(
                la, "slug_from_origin", return_value="Zipstack/unstract-cloud"
            ),
            mock.patch.object(la, "_gh", side_effect=gh),
            mock.patch("sys.stdout"),
            mock.patch("sys.stderr"),
        ):
            return la.main(["--declare", "1.7", "--pr", "5"])

    def test_appends_the_line_once(self):
        self.assertEqual(self.run_("Fixes x.\n\n"), 0)
        self.assertEqual(self.patches, ["body=Fixes x.\n\nBackport-also: 1.7\n"])
        self.assertEqual(self.run_("Fixes x.\n\nBackport-also: 1.7\n"), 0)
        self.assertEqual(self.patches, [])  # already declared: no write

    def test_refusals_and_failures(self):
        self.assertEqual(self.run_("x", labels=["main-only"]), 2)
        self.assertEqual(self.patches, [])
        self.assertEqual(
            self.run_("x", branch="gh api (exit 1): gh: Not Found (HTTP 404)"), 2
        )
        self.assertEqual(
            self.run_("x", after="someone else's edit"), 1
        )  # the write was lost


class Cli(unittest.TestCase):
    def test_bad_input_exits_2(self):
        for argv in ([], ["--pr", "1", "--answer", "hotfix=maybe"]):
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
