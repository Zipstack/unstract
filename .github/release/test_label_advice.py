"""Tests for label_advice. Run: python test_label_advice.py"""

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


class SearchSince(Repo):
    def test_search_starts_a_day_before_the_cut(self):
        """GitHub reads `merged:>=D` as UTC; a cut at 02:49 +0530 is the previous UTC day."""
        with mock.patch.dict(os.environ, GIT_COMMITTER_DATE="2026-10-31T02:49:30+05:30"):
            self.commit("cut")
        cut = rm.git(self.repo, "rev-parse", "HEAD")
        self.assertEqual(bp.search_since(self.repo, cut), "2026-10-30")


class Owed(Repo):
    def owed(self, run_log=None):
        dev_git(self.repo, "fetch", "-q", "origin", "--tags")

        def default_log(*a, **k):
            print(
                "held: 26 main commit(s) since the cut of release/1.7, 1 fix_class lookup(s)"
            )
            return [
                ("a" * 40, "1.7", "#11", "mine"),
                ("b" * 40, "1.7", "#99", "theirs"),
                ("c" * 40, bp.UNCLASSIFIABLE, "#12", "mine, unlabelled"),
            ]

        held = mock.Mock(side_effect=run_log or default_log)
        mine = json.dumps([{"number": 11}, {"number": 12}])
        old = os.getcwd()
        os.chdir(self.repo)
        try:
            with (
                mock.patch.object(bp, "held", held),
                mock.patch.object(bp, "pr_classes", return_value={"c": 1}),
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
            [("#11", "label backport/1.7"), ("#12", bp.UNCLASSIFIABLE)],
        )
        self.assertEqual(
            rows[0]["command"],
            "gh workflow run backport.yaml -R o/r -f commits=11 -f lines=1.7 -f patch_released_lines=true",
        )
        held.assert_called_once()
        self.assertEqual(held.call_args.args[2], "release/1.7")
        self.assertEqual(held.call_args.kwargs, {"cache": {"c": 1}})
        # Released or not, the line owes what its label covers: held() alone decides.
        dev_git(self.repo, "tag", "v1.7.0", "origin/release/1.7")
        dev_git(self.repo, "push", "-q", "origin", "v1.7.0")
        rows2, held, _ = self.owed()
        self.assertEqual(rows2, rows)
        self.assertEqual(held.call_args.kwargs, {"cache": {"c": 1}})

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

    def test_the_cli_fetches_origin_before_reading_it(self):
        dev_git(
            self.repo, "update-ref", "-d", "refs/remotes/origin/release/1.7"
        )  # a stale clone
        held = mock.Mock(return_value=[])
        old = os.getcwd()
        os.chdir(self.repo)
        try:
            with (
                mock.patch.object(
                    la, "slug_from_origin", return_value="o/unstract-cloud"
                ),
                mock.patch.object(bp, "held", held),
                mock.patch.object(bp, "pr_classes", return_value={}),
                mock.patch.object(la, "_gh", return_value=json.dumps([{"number": 11}])),
                mock.patch("sys.stdout"),
            ):
                self.assertEqual(la.main(["--owed", "--author", "dev"]), 0)
        finally:
            os.chdir(old)
        held.assert_called_once()
        self.assertEqual(held.call_args.args[2], "release/1.7")

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


def line(v, present=True, ga=False):
    return {"line": v, "present": present, "ga": ga}


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
                a = la.advise_pr("o/r", 7, pr=pr, patches={"backend/x.py": "@@ -1 +1 @@"})
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

    def test_code_on_a_line_awaiting_ga_suggests_its_line(self):
        a = la.advise(
            "main",
            ["backend/x.py"],
            [line("0.188"), line("0.186", present=False)],
        )
        self.assertEqual(
            (a["result"], a["label"], a["info"]), ("suggest", "backport/0.188", [])
        )

    def test_released_line_asks_the_hotfix_question(self):
        lines = [line("0.188"), line("0.186", ga=True)]
        a = la.advise("main", ["backend/x.py"], lines, pr=7)
        self.assertEqual(a["result"], "ask")
        self.assertEqual(
            a["question"]["answers"], {"yes": "backport/0.186", "no": "backport/0.188"}
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
            "backport/0.186",
        )

    def test_not_a_hotfix_on_released_lines_only_is_main_only(self):
        a = la.advise(
            "main", ["backend/x.py"], [line("0.186", ga=True)], pr=7, hotfix=False
        )
        self.assertEqual((a["result"], a["label"]), ("suggest", "main-only"))
        self.assertEqual(a["info"], [])

    def test_cannot_tell_asks_for_the_line(self):
        lines = [line("0.188", None), line("0.187", True), line("0.186", False)]
        a = la.advise(
            "main", ["backend/x.py"], lines, pr=7, how="by file path: blame failed (x)"
        )
        self.assertEqual(a["result"], "ask")
        q = a["question"]
        self.assertEqual(q["key"], "line")
        self.assertEqual(
            list(q["answers"]),
            ["backport/0.188", "backport/0.187", "backport/0.186", "main-only"],
        )
        self.assertIn(
            "cannot tell whether the changed code is on release/0.188", a["reason"]
        )
        self.assertTrue(a["next"]["backport/0.187"].endswith("--answer line=0.187"))
        self.assertTrue(a["next"]["main-only"].endswith("--answer line=main-only"))
        for ans, label in (("0.186", "backport/0.186"), ("main-only", "main-only")):
            b = la.advise("main", ["backend/x.py"], lines, pr=7, line=ans)
            self.assertEqual((b["result"], b["label"]), ("suggest", label))
        self.assertIn(
            "main-only: main-only, then:", la.render({**a, "pr": 7, "info": []})
        )

    def test_oldest_line_with_the_code_in_the_oss_state(self):
        """The OSS repo when line labels started: 0.188 and 0.187 in RC, 0.186 released."""

        def lines(*present):
            return [
                line("0.188", "0.188" in present),
                line("0.187", "0.187" in present),
                line("0.186", "0.186" in present, ga="0.186" in present),
            ]

        how = "blame: 2 commit(s) behind the changed lines"
        a = la.advise("main", ["backend/x.py"], lines("0.188"), pr=7, how=how)
        self.assertEqual((a["result"], a["label"]), ("suggest", "backport/0.188"))
        self.assertIn(how, a["reason"])
        a = la.advise("main", ["backend/x.py"], lines("0.188", "0.187"), pr=7, how=how)
        self.assertEqual((a["result"], a["label"]), ("suggest", "backport/0.187"))
        self.assertIn("release/0.187", a["reason"])
        self.assertIn(how, a["reason"])
        every = lines("0.188", "0.187", "0.186")
        a = la.advise("main", ["backend/x.py"], every, pr=7, how=how)
        self.assertEqual(a["result"], "ask")
        self.assertEqual(
            a["question"]["answers"], {"yes": "backport/0.186", "no": "backport/0.187"}
        )
        self.assertIn(how, a["reason"])
        for hotfix, want in ((True, "backport/0.186"), (False, "backport/0.187")):
            a = la.advise("main", ["backend/x.py"], every, hotfix=hotfix, how=how)
            self.assertEqual((a["result"], a["label"]), ("suggest", want), hotfix)
            self.assertIn(how, a["reason"])
        a = la.advise("main", ["backend/x.py"], lines(), how=how)
        self.assertEqual(a["label"], "main-only")
        # Two released lines with the code: a hotfix names the older one.
        two = [
            line("0.188", True),
            line("0.187", True, ga=True),
            line("0.186", True, ga=True),
        ]
        b = la.advise("main", ["backend/x.py"], two, pr=7)
        self.assertEqual(
            b["question"]["answers"], {"yes": "backport/0.186", "no": "backport/0.188"}
        )
        self.assertIn(how, a["reason"])


class OldRanges(unittest.TestCase):
    def test_old_side_ranges(self):
        self.assertEqual(la.old_ranges("@@ -5,3 +5,4 @@ def f():\n-a\n+b"), [(5, 7)])
        self.assertEqual(la.old_ranges("@@ -5 +5 @@\n-a\n+b"), [(5, 5)])
        self.assertEqual(
            la.old_ranges("@@ -1,2 +1,2 @@\n x\n@@ -40,0 +41,3 @@\n+new"), [(1, 2)]
        )
        self.assertEqual(la.old_ranges("@@ -0,0 +1,9 @@\n+new file"), [])  # pure addition
        self.assertEqual(la.old_ranges(None), [])  # GitHub omits the patch of a binary


class LineFacts(unittest.TestCase):
    """The facts advise() is fed, from mocked GitHub answers."""

    def gh(self, *args):
        url = next(a for a in args if a.startswith("repos/") or a == "graphql")
        if url == "graphql":
            self.blamed.append(next(a for a in args if a.startswith("path=")))
            if self.blame_fails:
                raise RuntimeError("gh api graphql (exit 1): HTTP 502")
            rows = [
                {"startingLine": 1, "endingLine": 9, "commit": {"oid": "old"}},
                {"startingLine": 10, "endingLine": 20, "commit": {"oid": "new"}},
            ]
            return json.dumps(
                {"data": {"repository": {"object": {"blame": {"ranges": rows}}}}}
            )
        if "matching-refs/heads/release/" in url:
            return "refs/heads/release/0.188\nrefs/heads/release/0.186\nrefs/heads/release/0.185\nrefs/heads/release/v0.148.1001"
        if "/compare/" in url:
            # "old" is on every line, "new" only on 0.188.
            on = "/compare/release/0.188..." in url or url.endswith("...old")
            return json.dumps({"status": "behind" if on else "diverged"})
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
        raise AssertionError(args)

    def facts(self, patches, blame_fails=False):
        self.blamed, self.blame_fails = [], blame_fails
        with mock.patch.object(la, "_gh", side_effect=self.gh):
            lines, how = la.line_facts("o/r", "b" * 40, patches)
        return {f["line"]: f for f in lines}, how

    def test_blame_decides_presence(self):
        f, how = self.facts(
            {"backend/x.py": "@@ -12,2 +12,2 @@", "docs/a.md": "@@ -1 +1 @@"}
        )
        self.assertEqual(
            self.blamed, ["path=backend/x.py"]
        )  # only shipped code is blamed
        self.assertEqual(how, "blame: 1 commit(s) behind the changed lines")
        self.assertEqual(
            {l: (x["present"], x["ga"]) for l, x in f.items()},
            {"0.188": (True, False), "0.186": (False, False), "0.185": (False, False)},
        )
        f, how = self.facts({"backend/x.py": "@@ -5,6 +5,6 @@"})  # both commits
        self.assertEqual(how, "blame: 2 commit(s) behind the changed lines")
        self.assertTrue(f["0.186"]["present"])
        self.assertTrue(f["0.186"]["ga"])  # stable tag
        self.assertFalse(f["0.188"]["ga"])  # an RC tag is not GA

    def test_path_fallback_says_why(self):
        f, how = self.facts({"backend/x.py": "@@ -0,0 +1,3 @@"})
        self.assertEqual(
            how, "by file path: the change only adds lines, so blame cannot tell"
        )
        self.assertEqual(self.blamed, [])
        self.assertIsNone(f["0.188"]["present"])  # a truncated tree cannot tell
        self.assertTrue(f["0.186"]["present"])  # the file exists there
        self.assertEqual((f["0.186"]["ga"], f["0.185"]["ga"]), (True, True))
        f, _ = self.facts({"backend/new.py": "@@ -0,0 +1,3 @@"})
        self.assertFalse(f["0.186"]["present"])
        self.assertFalse(f["0.186"]["ga"])  # GA is looked up only where the code is

        many = {f"backend/m{i}.py": "@@ -1 +1 @@" for i in range(la.BLAME_MAX + 1)}
        _, how = self.facts(many)
        self.assertEqual(
            how,
            f"by file path: {la.BLAME_MAX + 1} files is past the blame limit of {la.BLAME_MAX}",
        )
        self.assertEqual(self.blamed, [])
        _, how = self.facts(
            {f"backend/m{i}.py": "@@ -1 +1 @@" for i in range(la.BLAME_MAX)}
        )
        self.assertTrue(how.startswith("blame: "))  # at the limit, still blamed

        f, how = self.facts({"backend/x.py": "@@ -12 +12 @@"}, blame_fails=True)
        self.assertTrue(how.startswith("by file path: blame failed ("), how)
        self.assertIn("HTTP 502", how)
        self.assertTrue(f["0.186"]["present"])


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
