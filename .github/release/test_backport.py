"""Tests for backport helpers, and pick() against real git. Run: python test_backport.py"""

import contextlib
import io
import json
import os
import re
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

os.environ["GITHUB_REPOSITORY"] = (
    "Zipstack/unstract-cloud"  # pin relstate to the cloud config
)
os.environ["GITHUB_SERVER_URL"] = (
    "https://github.com"  # CI sets it, and summaries link only with it
)
os.environ["RELEASE_BOT_APP_SLUG"] = "zipstack-push-to-main"
BOT = {
    "login": "app/zipstack-push-to-main",
    "is_bot": True,
}
import backport as bp
import relmgr as rm
from test_backport_merge import (  # noqa: F401
    BAD_GATEWAY,
    NOT_FOUND,
    FakeGh,
    queue,
    setUpModule,
)


def dev_git(repo, *a):
    return rm.git(repo, "-c", "user.name=Dev", "-c", "user.email=dev@example.com", *a)


class Held(unittest.TestCase):
    def test_held_filter(self):
        a, b, c, d, e = (ch * 40 for ch in "abcde")
        classes = {
            a: ("ga", "#1"),
            b: ("ga", "#2"),
            c: ("rc", "#3"),
            d: (None, "no PR"),
            e: ("ga", "#5"),
        }
        # a picked (abbreviated trailer), e declined (same trailer): only b is held; fix and non-fix never are.
        self.assertEqual(
            bp.held_filter([a, b, c, d, e], classes, {a[:7], e}), [(b, "ga", "#2")]
        )
        classes[d] = (bp.UNCLASSIFIABLE, "no PR")
        self.assertEqual(
            bp.held_filter([a, b, c, d, e], classes, {a[:7], e}),
            [(b, "ga", "#2"), (d, bp.UNCLASSIFIABLE, "no PR")],
        )
        self.assertEqual(
            bp.held_filter([a, b, c, d, e], classes, {a[:7], e}, accept=bp.OWED),
            [(b, "ga", "#2"), (c, "rc", "#3"), (d, bp.UNCLASSIFIABLE, "no PR")],
        )
        rows = [
            (a, "release/0.189", "ga", "#1"),
            (a, "release/0.182", "ga", "#1"),
            (b, "release/0.182", "ga", "#2"),
        ]
        self.assertEqual(
            bp.held_warnings(rows),
            [
                "::warning::release/0.189: 1 held backport/ga fix, confirm with Backport and patch_released_lines",
                "::warning::release/0.182: 2 held backport/ga fixes, confirm with Backport and patch_released_lines",
            ],
        )
        self.assertEqual(
            bp.held_line(b, "ga", "#2", "release/0.182"),
            "::warning::bbbbbbb (ga, PR #2) held for release/0.182: stabilized, needs patch_released_lines",
        )

        self.assertIsNone(bp.held_note([], "release/0.182"))
        with mock.patch.dict(
            os.environ, {"GITHUB_SERVER_URL": "", "GITHUB_REPOSITORY": ""}
        ):
            self.assertEqual(
                bp.held_note(
                    [(b, "ga", "#2", "t"), (d, bp.UNCLASSIFIABLE, "no PR", "t")],
                    "release/0.182",
                ),
                f"⚠ Held for confirmation on `release/0.182` (stabilized; Promote blocks unless forced): #2 ga. "
                "Pick with `gh workflow run backport.yaml -f commits=#2 -f lines=0.182 -f patch_released_lines=true` "
                f"{bp.UNCLASSIFIABLE}, add a backport label or fix its PR title, or record a decline: `{d[:7]}` (no PR) t",
            )
            note = bp.held_note(
                [(d, bp.UNCLASSIFIABLE, "#42", "x (no backport label: y)")],
                "release/0.182",
            )
            self.assertNotIn("commits=", note)
            self.assertIn("add a backport label", note)
            self.assertIn("#42 x (no backport label: y)", note)

    def test_unclassifiable_held_line_names_the_error_not_confirm(self):
        line = bp.held_line(
            "a" * 40,
            bp.UNCLASSIFIABLE,
            "#42",
            "release/0.186",
            "error",
            None,
            "x (no backport label: y)",
        )
        self.assertEqual(
            line,
            f"::error::aaaaaaa ({bp.UNCLASSIFIABLE}, PR #42, x (no backport label: y)) held for release/0.186: "
            "add a backport label or fix its PR title, or record a decline",
        )

    def test_warn_held_passes_the_title(self):
        rows = [("a" * 40, bp.UNCLASSIFIABLE, "#42", "x (no backport label: y)")]
        out = io.StringIO()
        with (
            mock.patch.object(bp, "held", return_value=rows),
            mock.patch.dict(
                os.environ, {"GITHUB_SERVER_URL": "", "GITHUB_REPOSITORY": ""}
            ),
            contextlib.redirect_stdout(out),
        ):
            note = bp.warn_held("o/r", ".", "release/0.186", "error")
        self.assertIn("PR #42, x (no backport label: y)) held", out.getvalue())
        self.assertNotIn("patch_released_lines", out.getvalue() + note)


class Rescan(unittest.TestCase):
    """Push mode over held_filter output for nested ranges: 0.190 (stabilizing, cut after a) inside 0.187."""

    def test_plan(self):
        a, b, c, d, e, u = (ch * 40 for ch in "abcdeu")
        classes = {
            a: ("rc", "#1", "A"),
            b: ("rc", "#2", "B"),
            c: ("ga", "#3", "C"),
            d: ("rc", "#4", "D"),
            e: ("rc", "#5", "E"),
            u: (bp.UNCLASSIFIABLE, "no PR", "U"),
        }
        targets = {
            "rc": ["release/0.190"],
            "ga": [
                {"branch": "release/0.190", "needs_rm_confirmation": False},
                {"branch": "release/0.187", "needs_rm_confirmation": True},
            ],
        }
        scan, others = bp.rescan_targets(targets, [])
        self.assertEqual(
            (scan, others), ({"release/0.190": bp.OWED, "release/0.187": bp.HELD}, [])
        )
        # 0.190: b picked, e declined (a decline carries the pick trailer). 0.187 (stabilized): nothing yet.
        held = {
            "release/0.190": bp.held_filter(
                [b, c, d, e, u], classes, {b[:7], e}, scan["release/0.190"]
            ),
            "release/0.187": bp.held_filter(
                [a, b, c, d, e, u], classes, set(), scan["release/0.187"]
            ),
        }
        plan, awaiting, unclassifiable = bp.rescan_plan(targets, held, confirm=False)
        self.assertEqual(
            plan,
            [
                ("release/0.190", c, "ga", "#3", "C"),
                ("release/0.190", d, "rc", "#4", "D"),
            ],
        )
        self.assertEqual(awaiting, [(c, "release/0.187", "ga", "#3")])
        self.assertEqual(
            unclassifiable,
            [(u, "release/0.190", "no PR", "U"), (u, "release/0.187", "no PR", "U")],
        )
        plan, awaiting, _ = bp.rescan_plan(targets, held, confirm=True)
        self.assertEqual(
            (plan[-1], awaiting), (("release/0.187", c, "ga", "#3", "C"), [])
        )

    def test_listed_branches(self):
        self.assertEqual(
            bp.listed_branches(" 0.186, release/0.188 ,"),
            ["release/0.186", "release/0.188"],
        )
        self.assertEqual(bp.listed_branches(""), [])
        with self.assertRaisesRegex(ValueError, "'0.186.1'"):
            bp.listed_branches("0.185,0.186.1")

    def test_cli_refuses_a_bad_line(self):
        with tempfile.TemporaryDirectory() as d:
            state = os.path.join(d, "state.json")
            with open(state, "w") as fh:
                json.dump({"backport_targets": {"rc": [], "ga": []}}, fh)
            r = subprocess.run(
                [
                    sys.executable,
                    bp.__file__,
                    "--state",
                    state,
                    "--rescan",
                    "--lines",
                    "0.185,0.186.1",
                ],
                env={
                    **os.environ,
                    "RUNNER_TEMP": d,
                    "GITHUB_REPOSITORY": "Zipstack/unstract-cloud",
                },
                capture_output=True,
                text=True,
            )
        self.assertEqual(
            (r.returncode, r.stderr),
            (1, "::error::lines: not a release line X.Y (e.g. 0.186): '0.186.1'\n"),
        )

    def test_branches_narrow(self):
        targets = {
            "rc": ["release/0.190"],
            "ga": [{"branch": "release/0.187", "needs_rm_confirmation": True}],
        }
        self.assertEqual(
            bp.rescan_targets(targets, ["release/0.187", "release/0.1"]),
            ({"release/0.187": bp.HELD}, ["release/0.1"]),
        )


class Listing(unittest.TestCase):
    def test_classes_and_fallback(self):
        with tempfile.TemporaryDirectory() as repo:
            git = lambda *a: dev_git(repo, *a)
            git("init", "-q", "-b", "main")
            shas = []
            for i in range(6):  # cut, fix, security, misc, bad title, no PR
                git("commit", "-q", "--allow-empty", "-m", f"c{i}")
                shas.append(git("rev-parse", "HEAD"))
            cut, fix, sec, misc, bad, nopr = shas
            # Not held: the bot's direct commit, and a merge-back with the old release commit it brings in.
            rm.git(
                repo,
                "-c",
                "user.name=bot",
                "-c",
                f"user.email={rm.BOT_EMAIL}",
                "commit",
                "-q",
                "--allow-empty",
                "-m",
                "Update Helm files for RC rc.1",
            )
            git("checkout", "-q", "-b", "old", cut)
            git("commit", "-q", "--allow-empty", "-m", "old release fix")
            git("checkout", "-q", "main")
            git(
                "merge", "-q", "--no-ff", "old", "-m", "Merge release v0.0.1 back to main"
            )
            git("update-ref", "refs/remotes/origin/main", "HEAD")
            git("update-ref", "refs/remotes/origin/release/0.1", cut)
            pr = lambda n, sha, title, labels=(): {
                "number": n,
                "title": title,
                "labels": [{"name": l} for l in labels],
                "mergeCommit": {"oid": sha},
            }
            listing = [
                pr(1, fix, "UN-1 [FIX] a", ["backport/rc"]),
                pr(2, sec, "UN-2 [FIX] b", ["backport/ga"]),
                pr(3, misc, "UN-3 [MISC] c", ["main-only"]),
                pr(4, bad, "no prefix"),
                {"number": 5, "title": "open", "labels": [], "mergeCommit": None},
            ]
            classes = bp.classes_from_listing(listing)
            self.assertEqual(classes[fix], ("rc", "#1", "UN-1 [FIX] a"))
            self.assertEqual(classes[sec], ("ga", "#2", "UN-2 [FIX] b"))
            self.assertEqual(classes[misc], (None, "#3", "UN-3 [MISC] c"))
            self.assertEqual(classes[bad][:2], (bp.UNCLASSIFIABLE, "#4"))
            self.assertIn(
                "no recognised '[TYPE]' or 'TICKET [TYPE]' prefix", classes[bad][2]
            )
            self.assertEqual(
                len(classes), 4
            )  # an unmerged row (no merge commit) is skipped
            looked = []
            saved = bp.fix_class
            bp.fix_class = lambda slug, sha, token=None: (
                looked.append(sha)
                or (
                    None,
                    "no PR",
                    None,
                )
            )
            try:
                rows = bp.held("o/r", repo, "release/0.1", accept=bp.OWED, cache=classes)
            finally:
                bp.fix_class = saved
            self.assertEqual(
                looked, [nopr]
            )  # only the commit the listing missed is looked up
            self.assertEqual(
                [(s, c) for s, c, *_ in rows],
                [
                    (fix, "rc"),
                    (sec, "ga"),
                    (bad, bp.UNCLASSIFIABLE),
                    (nopr, bp.UNCLASSIFIABLE),
                ],
            )


class PushRetry(unittest.TestCase):
    def test_retry_then_fail_loudly(self):
        sha, head, branch = "c" * 40, "backport/0.190/ccccccc", "release/0.190"
        rejected = "To https://github.com/o/r\n ! [remote rejected] HEAD -> backport/0.190/ccccccc (failure)"
        calls, sleeps = [], []

        def fake(results):
            def run(*args, check=True, input=None):
                calls.append(args)
                rc = results.pop(0) if args[:2] == ("git", "push") else 0
                return subprocess.CompletedProcess(args, rc, "", rejected if rc else "")

            return run

        saved, env = bp.run, dict(os.environ)
        os.environ.update(
            GITHUB_SERVER_URL="https://github.com",
            GITHUB_REPOSITORY="o/r",
            GITHUB_RUN_ID="9",
        )
        try:
            bp.run = fake(
                [1, 1, 0]
            )  # rejected twice, then pushed: one success, two waits, no comment
            self.assertIsNone(
                bp.push_head("o/r", sha, branch, head, "#7", sleep=sleeps.append)
            )
            self.assertEqual((sleeps, len(calls)), ([5, 20], 3))
            calls.clear(), sleeps.clear()
            bp.run = fake([1, 1, 1])
            with mock.patch.object(bp.rm, "is_converged", return_value=False):
                out = bp.push_head("o/r", sha, branch, head, "#7", sleep=sleeps.append)
            comment = calls[-1]
            calls.clear(), sleeps.clear()
            bp.run = fake(
                [1, 1, 1]
            )  # rejected because another run landed the pick: no failure, no comment
            with mock.patch.object(bp.rm, "is_converged", return_value=True):
                landed = bp.push_head("o/r", sha, branch, head, "#7", sleep=sleeps.append)
        finally:
            bp.run = saved
            os.environ.clear(), os.environ.update(env)
        self.assertEqual(
            out,
            (
                "failed",
                f"push of {head} rejected 3 times: ! [remote rejected] HEAD -> {head} (failure)",
            ),
        )
        self.assertEqual(landed[0], "skipped")
        self.assertEqual(sleeps, [5, 20])
        self.assertNotIn(("gh", "pr"), [a[:2] for a in calls])
        self.assertEqual(comment[:6], ("gh", "pr", "comment", "7", "-R", "o/r"))
        self.assertEqual(
            comment[-1].splitlines()[0],
            f"Backport to {branch} failed: push of {head} rejected (run https://github.com/o/r/actions/runs/9)."
            f" Rerun Backport for ccccccc on {branch}.",
        )


ORIG = "0123abc" + "d" * 33


class Body(unittest.TestCase):
    def test_conflict_body_has_no_stale_rule(self):
        body = bp.pr_body(
            ORIG, "#5", "release/1.6", f"backport/1.6/{ORIG[:7]}", ["NOTES.md"]
        )
        self.assertNotIn("do not merge by hand", body)
        self.assertIn(
            "Resolve, get one approval and merge, or close the PR to decline (the close comment is the reason).",
            body,
        )
        self.assertNotIn("Declined:", body)
        self.assertNotIn("backport-approved", body)
        self.assertIn("- `NOTES.md`", body)
        self.assertIn(
            f"push a fix-up commit; the first commit's `(cherry picked from commit {ORIG})` line carries",
            body,
        )
        self.assertIn(
            "Clean pick",
            bp.pr_body(ORIG, "#5", "release/1.6", f"backport/1.6/{ORIG[:7]}"),
        )


class MainOrder(unittest.TestCase):
    def test_newest_first_comes_back_oldest_first(self):
        with tempfile.TemporaryDirectory() as repo:
            rm.git(repo, "init", "-q", "-b", "main")
            shas = []
            for i, date in enumerate(("2026-01-01T00:00:00Z", "2026-01-02T00:00:00Z")):
                os.environ["GIT_COMMITTER_DATE"] = date
                try:
                    dev_git(repo, "commit", "-q", "--allow-empty", "-m", f"fix {i}")
                finally:
                    del os.environ["GIT_COMMITTER_DATE"]
                shas.append(rm.git(repo, "rev-parse", "HEAD"))
            self.assertEqual(bp.main_order(repo, [shas[1], shas[0], shas[1]]), shas)


class OwedSummary(unittest.TestCase):
    def test_table_and_label_hint(self):
        a, b = "a" * 40, "b" * 40
        out = bp.owed_summary(
            [(a, "rc", "#3", "UN-1 [FIX] x | y"), (b, bp.UNCLASSIFIABLE, "no PR", "z")],
            "release/0.187",
        )
        self.assertIn(
            f"| [`aaaaaaa`]({WEB}/commit/{a}) | [#3]({WEB}/pull/3) | UN-1 [FIX] x \\| y | rc |",
            out,
        )
        self.assertIn(
            f"| [`bbbbbbb`]({WEB}/commit/{b}) | no PR | z | {bp.UNCLASSIFIABLE} |", out
        )
        self.assertTrue(
            out.endswith(
                "To pick a fix: dispatch Backport with its commit, `patch_released_lines=true` and `lines=0.187`"
                " plus every newer released line. Backport skips an unclassifiable row."
            )
        )
        self.assertTrue(bp.owed_summary([], "release/0.187").endswith("none"))


ACTIONS = {
    "GITHUB_SERVER_URL": "https://github.com",
    "GITHUB_REPOSITORY": "Zipstack/unstract-cloud",
}
GH = "https://github.com"
WEB = f"{GH}/Zipstack/unstract-cloud"


class SummaryLinks(unittest.TestCase):
    A = "6d49d9f" + "0" * 33

    def test_dispatch_rows(self):
        a = self.A
        with mock.patch.dict(os.environ, ACTIONS):
            self.assertEqual(
                bp.dispatch_row(a, "no PR", "none", "-", "skipped: not a fix", "-"),
                f"| [`6d49d9f`]({WEB}/commit/{a}) | no PR | none | - | skipped: not a fix | - |",
            )
            self.assertEqual(
                bp.dispatch_row(
                    a,
                    "#251",
                    "rc",
                    "release/0.192",
                    "merged 1234567 (#260, retried)",
                    "-",
                ),
                f"| [`6d49d9f`]({WEB}/commit/{a}) | [#251]({WEB}/pull/251) | rc "
                f"| [`release/0.192`]({WEB}/tree/release/0.192) "
                f"| merged [`1234567`]({WEB}/commit/1234567) ([#260]({WEB}/pull/260), retried) | - |",
            )
            self.assertIn(
                f"| pr [#261]({WEB}/pull/261) |",
                bp.dispatch_row(
                    a, "#251", "rc", "release/0.190", f"pr {WEB}/pull/261", "-"
                ),
            )
            self.assertTrue(
                bp.dispatch_row("-------", "-", "-", "-", "x", "-").startswith(
                    "| `-------` | - |"
                )
            )

    def test_display_copies_link_and_paste_lines_stay_plain(self):
        a, b = self.A, "b" * 40
        with mock.patch.dict(os.environ, ACTIONS):
            owed = bp.owed_summary(
                [(a, "rc", "#3", "t"), (b, bp.UNCLASSIFIABLE, "no PR", "z")],
                "release/0.187",
            )
            self.assertIn(f"for [`release/0.187`]({WEB}/tree/release/0.187):", owed)
            self.assertIn(
                f"| [`6d49d9f`]({WEB}/commit/{a}) | [#3]({WEB}/pull/3) | t | rc |", owed
            )
            self.assertIn(f"| [`bbbbbbb`]({WEB}/commit/{b}) | no PR | z |", owed)
            oss = "https://github.com/Zipstack/unstract"
            note = bp.held_note(
                [(a, "ga", "#2", "t"), (b, bp.UNCLASSIFIABLE, "no PR", "t")],
                "release/0.182",
                "Zipstack/unstract",
            )
            self.assertIn(
                f"on Zipstack/unstract [`release/0.182`]({oss}/tree/release/0.182) (stabilized; Promote blocks "
                f"unless forced): [Zipstack/unstract#2]({oss}/pull/2) ga. Pick with",
                note,
            )
            self.assertIn(
                f"record a decline: [`bbbbbbb`]({oss}/commit/{b}) (no PR) t", note
            )
            self.assertIn("-f commits=#2 -f lines=0.182", note)
            pending = bp.pending_block(
                [(261, "release/0.190", 1)],
                [(b, "release/0.189", "ga", "no PR", 1)],
            )
            self.assertIn(
                f"- [#261]({WEB}/pull/261) on [`release/0.190`]({WEB}/tree/release/0.190) · open 1 day",
                pending,
            )
            self.assertIn(
                f"- [`bbbbbbb`]({WEB}/commit/{b}) (no PR) ga → [`release/0.189`]({WEB}/tree/release/0.189)",
                " ".join(pending),
            )
            self.assertIn(f"-f commits={b[:12]} -f lines=0.189", " ".join(pending))
            self.assertEqual(
                bp.this_run([(a, "#251", "rc", "release/0.192", "failed: x", "-")]),
                [
                    f"- [#251]({WEB}/pull/251) → [`release/0.192`]({WEB}/tree/release/0.192): failed: x"
                ],
            )
            self.assertTrue(
                bp.status_row(
                    "release/0.192", "stabilizing", None, 0, 0, [], 0
                ).startswith(
                    f"| [`release/0.192`]({WEB}/tree/release/0.192) | stabilizing | none |"
                )
            )


class OnlyListed(unittest.TestCase):
    def test_filter_narrows_never_adds(self):
        targets = ["release/0.189", "release/0.188"]
        self.assertEqual(bp.only_listed(targets, []), (targets, []))
        self.assertEqual(
            bp.only_listed(targets, ["release/0.188"]), (["release/0.188"], [])
        )
        self.assertEqual(
            bp.only_listed(["release/0.189"], ["release/0.188", "release/0.189"]),
            (["release/0.189"], ["release/0.188"]),
        )


class DispatchNonFix(unittest.TestCase):
    def test_row_names_the_route(self):
        a, b = "a" * 40, "b" * 40
        classes = {a: (None, "#250", "UN-1 [MISC] docs"), b: (None, "no PR", None)}
        with (
            mock.patch("sys.stdout", new_callable=io.StringIO) as out,
            mock.patch.object(bp, "resolve", lambda slug, c, prs: c),
            mock.patch.object(bp, "main_order", lambda repo, shas: shas),
            mock.patch.object(bp, "fix_class", lambda slug, sha: classes[sha]),
        ):
            rows, awaiting = bp.dispatch(
                "o/r",
                {"rc": ["release/0.191"], "ga": []},
                f"{a} {b}",
                False,
                [],
            )
        self.assertEqual(
            rows,
            [
                (
                    a,
                    "#250",
                    "none",
                    "-",
                    "skipped: not a fix; swap #250's main-only label for a backport label and rerun",
                    "-",
                ),
                (b, "no PR", "error", "-", "failed: no PR found", "-"),
            ],
        )
        self.assertEqual(awaiting, [])
        self.assertIn("::error::bbbbbbb: no PR found", out.getvalue())


MERGED = "6d49d9f180015ef06dc28763bc02d04d4be4c5a2"
SUBJECT = "UN-4160 [MISC] Log in to prod through Unstract ID (#1946)"
PR_1946 = {
    "number": 1946,
    "title": "UN-4160 [MISC] Log in to prod through Unstract ID",
    "labels": [
        {"name": "main-only"}
    ],  # set for the not-a-fix path; the live PR carries backport/rc
    "merged": True,
    "merge_commit_sha": MERGED,
}


def api(pulls="[]", message=SUBJECT, pr=PR_1946):
    """Gh api fake: commits/{sha}/pulls, commits/{sha}, then pulls/N."""
    calls = []

    def gh(*a, token=None, retry=True):
        path = a[1]
        calls.append(path)
        if path.endswith("/pulls"):
            return pulls
        if "/commits/" in path:
            return json.dumps({"commit": {"message": message}})
        if pr is None:
            raise RuntimeError("gh api repos/o/r/pulls/1946 (exit 1): " + NOT_FOUND)
        return json.dumps(pr)

    return gh, calls


class ListingUnlabelled(unittest.TestCase):
    def test_a_main_pr_without_a_routing_label_is_unclassifiable(self):
        pr = {
            "number": 8,
            "title": "UN-8 [FIX] x",
            "labels": [],
            "mergeCommit": {"oid": "s"},
        }
        cls, ref, title = bp.classes_from_listing([pr])["s"]
        self.assertEqual((cls, ref), (bp.UNCLASSIFIABLE, "#8"))
        self.assertRegex(title, r"^UN-8 \[FIX\] x \(no backport label: ")

    def test_a_looked_up_pr_without_a_routing_label_keeps_its_number(self):
        pr = {"number": 8, "title": "UN-8 [FIX] x", "labels": []}
        cls, ref, title = bp.pr_class(pr)
        self.assertEqual((cls, ref), (bp.UNCLASSIFIABLE, "#8"))
        self.assertRegex(title, r"^UN-8 \[FIX\] x \(no backport label: ")


class FixClassSubject(unittest.TestCase):
    """GitHub's commit-to-PR index can miss a squash merge; the subject's (#N) is checked against the PR."""

    def fix_class(self, **kw):
        gh, self.calls = api(**kw)
        with (
            mock.patch.object(bp, "gh", gh),
            mock.patch("sys.stdout", new_callable=io.StringIO) as out,
        ):
            got = bp.fix_class("o/r", MERGED)
        self.out = out.getvalue()
        return got

    def test_subject_pr_that_merged_the_commit(self):
        self.assertEqual(self.fix_class(), (None, "#1946", PR_1946["title"]))
        self.assertIn("::notice::6d49d9f: no PR indexed", self.out)

    def test_indexed_pr_wins(self):
        listed = [
            {
                **PR_1946,
                "number": 7,
                "title": "UN-7 [FIX] x",
                "labels": [{"name": "backport/rc"}],
            }
        ]
        self.assertEqual(
            self.fix_class(pulls=json.dumps(listed)), ("rc", "#7", "UN-7 [FIX] x")
        )
        self.assertEqual(len(self.calls), 1)

    def test_unlabelled_indexed_pr_keeps_its_number(self):
        listed = [{**PR_1946, "number": 7, "title": "UN-7 [FIX] x", "labels": []}]
        cls, ref, title = self.fix_class(pulls=json.dumps(listed))
        self.assertEqual((cls, ref), (bp.UNCLASSIFIABLE, "#7"))
        self.assertRegex(title, r"^UN-7 \[FIX\] x \(no backport label: ")

    def test_no_pr_unless_the_subject_names_one_that_merged_it(self):
        cases = {
            "no (#N)": {"message": "UN-4160 [MISC] Log in to prod through Unstract ID"},
            "(#N) not trailing": {"message": "Revert (#1946) login"},
            "(#N) only in the body": {"message": "Squash\n\n* login (#1946)"},
            "another commit": {"pr": {**PR_1946, "merge_commit_sha": "0" * 40}},
            "not merged": {"pr": {**PR_1946, "merged": False}},
            "not a PR": {"pr": None},
        }
        for name, kw in cases.items():
            with self.subTest(name):
                self.assertEqual(self.fix_class(**kw), (None, "no PR", None))
                self.assertNotIn("::notice::", self.out)


class DispatchNamedPr(unittest.TestCase):
    def test_classed_from_the_named_pr(self):
        def no_lookup(*a):
            raise AssertionError("fix_class called for a named PR")

        gh, _ = api()
        with (
            mock.patch.object(bp, "gh", gh),
            mock.patch.object(bp.rm, "resolve", lambda repo, item: item),
            mock.patch.object(bp.rm, "is_ancestor", lambda *a: True),
            mock.patch.object(bp, "main_order", lambda repo, shas: shas),
            mock.patch.object(bp, "fix_class", no_lookup),
        ):
            rows, _ = bp.dispatch(
                "o/r",
                {"rc": ["release/0.191"], "ga": []},
                "#1946",
                False,
                [],
            )
        self.assertEqual(
            rows,
            [
                (
                    MERGED,
                    "#1946",
                    "none",
                    "-",
                    "skipped: not a fix; swap #1946's main-only label for a backport label and rerun",
                    "-",
                )
            ],
        )


class RescanUnclassifiable(unittest.TestCase):
    def test_fails_the_run(self):
        u, b = "u" * 40, "release/0.191"
        with (
            mock.patch.object(bp, "rescan_targets", lambda t, l: ({b: bp.OWED}, [])),
            mock.patch.object(bp, "_rescan_classes", lambda slug, scan: {}),
            mock.patch.object(bp, "held", lambda *a, **k: []),
            mock.patch.object(
                bp, "rescan_plan", lambda *a: ([], [], [(u, b, "no PR", "U")])
            ),
            mock.patch("sys.stdout", new_callable=io.StringIO) as out,
        ):
            rows, *_ = bp.rescan("o/r", {}, False, [])
        self.assertEqual(
            rows, [(u, "no PR", bp.UNCLASSIFIABLE, b, "failed: unclassifiable", "-")]
        )
        self.assertIn("::error::uuuuuuu (no PR, U) cannot be classed", out.getvalue())

    def test_a_listed_line_that_is_not_a_target_fails(self):
        with (
            mock.patch.object(bp, "_rescan_classes", lambda slug, scan: {}),
            mock.patch("sys.stdout", new_callable=io.StringIO) as out,
        ):
            rows, *_ = bp.rescan("o/r", TARGETS, False, ["release/0.150"])
        self.assertEqual(
            rows, [("-------", "-", "-", "release/0.150", "failed: not a target", "-")]
        )
        self.assertIn(
            "::error::release/0.150 is not a target: nothing picked there", out.getvalue()
        )


class DispatchHold(unittest.TestCase):
    def test_security_waits_for_rm_on_a_stabilized_line(self):
        sec, fix = "s" * 40, "f" * 40
        classes = {
            sec: ("ga", "#3", "UN-3 [FIX] x"),
            fix: ("rc", "#4", "UN-4 [FIX] y"),
        }
        targets = {
            "rc": ["release/0.191"],
            "ga": [
                {"branch": "release/0.191", "needs_rm_confirmation": False},
                {"branch": "release/0.190", "needs_rm_confirmation": True},
            ],
        }
        with (
            mock.patch.object(bp, "resolve", lambda slug, c, prs: c),
            mock.patch.object(bp, "main_order", lambda repo, shas: shas),
            mock.patch.object(bp, "fix_class", lambda slug, sha: classes[sha]),
            mock.patch.object(bp, "pick_row", lambda slug, sha, b, *a: (sha, b)),
        ):
            run = lambda confirm: bp.dispatch("o/r", targets, f"{sec} {fix}", confirm, [])
            self.assertEqual(
                run(False),
                (
                    [(sec, "release/0.191"), (fix, "release/0.191")],
                    [(sec, "release/0.190", "ga", "#3")],
                ),
            )
            self.assertEqual(
                run(True),
                (
                    [
                        (sec, "release/0.191"),
                        (sec, "release/0.190"),
                        (
                            fix,
                            "#4",
                            "rc",
                            "release/0.190",
                            "failed: stabilized; a backport/rc fix needs lines",
                            "-",
                        ),
                        (fix, "release/0.191"),
                    ],
                    [],
                ),
            )


class DispatchPatch(unittest.TestCase):
    """patch_released_lines + lines: a plain fix goes onto the stabilized lines named, and only those."""

    def setUp(self):
        self.fix = "f" * 40
        targets = {
            "rc": ["release/0.191"],
            "ga": [
                {"branch": "release/0.191", "needs_rm_confirmation": False},
                {"branch": "release/0.190", "needs_rm_confirmation": True},
                {"branch": "release/0.188", "needs_rm_confirmation": True},
            ],
        }
        for p in (
            mock.patch.object(bp, "resolve", lambda slug, c, prs: c),
            mock.patch.object(bp, "main_order", lambda repo, shas: shas),
            mock.patch.object(
                bp, "fix_class", lambda slug, sha: ("rc", "#4", "UN-4 [HOT-FIX] y")
            ),
            mock.patch.object(bp, "pick_row", lambda slug, sha, b, *a: b),
            mock.patch("sys.stdout", io.StringIO()),
        ):
            p.start()
            self.addCleanup(p.stop)
        self.run_ = lambda confirm, listed, t=targets: bp.dispatch(
            "o/r", t, self.fix, confirm, listed
        )[0]

    def test_named_stabilized_lines(self):
        self.assertEqual(
            self.run_(True, ["release/0.190", "release/0.188"]),
            ["release/0.190", "release/0.188"],
        )
        # A stabilizing line named beside a stabilized one is picked once.
        self.assertEqual(
            self.run_(True, ["release/0.191", "release/0.190"]),
            ["release/0.191", "release/0.190"],
        )

    def test_without_confirm_a_named_stabilized_line_says_why(self):
        self.assertEqual(
            self.run_(False, ["release/0.190", "release/0.150"]),
            [
                (
                    self.fix,
                    "#4",
                    "rc",
                    "release/0.190",
                    "failed: stabilized; needs patch_released_lines",
                    "-",
                ),
                (self.fix, "#4", "rc", "release/0.150", "failed: not a target", "-"),
            ],
        )

    def test_confirm_without_branches_says_why(self):
        why = "failed: stabilized; a backport/rc fix needs lines"
        self.assertEqual(
            self.run_(True, []),
            [
                (self.fix, "#4", "rc", "release/0.190", why, "-"),
                (self.fix, "#4", "rc", "release/0.188", why, "-"),
                "release/0.191",
            ],
        )
        self.assertEqual(self.run_(False, []), ["release/0.191"])
        # No stabilizing line: the why rows stand alone, without a "no target branch" row.
        only = {
            "rc": [],
            "ga": [{"branch": "release/0.190", "needs_rm_confirmation": True}],
        }
        self.assertEqual(
            self.run_(True, [], only),
            [(self.fix, "#4", "rc", "release/0.190", why, "-")],
        )


class PatchLines(unittest.TestCase):
    def test_paste_line_per_stabilized_line(self):
        a, b, u = "a" * 40, "b" * 40, "u" * 40
        stable = lambda tag, at: {"tag": tag, "pushed_at": at}
        state = {
            "branches": [
                {"branch": "release/0.191", "state": "stabilizing", "targets": {}},
                {
                    "branch": "release/0.190",
                    "state": "stabilized",
                    "targets": {
                        "cloud": {
                            "ga": stable("v0.190.1", "2026-08-02T00:00:00Z"),
                            "promoted": stable("v0.190.10", "2026-10-02T00:00:00Z"),
                        },
                        "on-prem": {
                            "ga": stable("v0.190.0", "2026-08-01T00:00:00Z"),
                            "promoted": stable("v0.190.9", "2026-10-01T00:00:00Z"),
                        },
                    },
                },
                {
                    "branch": "release/0.188",
                    "state": "stabilized",
                    "targets": {
                        "cloud": {
                            "ga": stable("v0.188.0", "2026-06-01T00:00:00Z"),
                            "promoted": stable("v0.188.2", "2026-09-01T00:00:00Z"),
                        },
                        "on-prem": {"ga": None, "promoted": None},
                    },
                },
            ]
        }
        rows = {
            "release/0.190": [
                (a, "rc", "#7", "t"),
                (b, "ga", "no PR", "t"),
                (u, bp.UNCLASSIFIABLE, "no PR", "t"),
            ],
            "release/0.188": [],
        }
        calls = []

        def held(slug, repo, branch, accept, cache):
            calls.append((branch, accept))
            return rows[branch]

        listed = []
        with (
            mock.patch.object(bp, "held", held),
            mock.patch.object(
                bp, "pr_classes", lambda slug, since: listed.append(since) or {}
            ),
        ):
            out = bp.patch_lines(state, "o/r").splitlines()
        self.assertEqual(
            listed, ["2026-06-01T00:00:00Z"]
        )  # one listing, from the oldest first GA
        self.assertEqual(
            calls,
            [
                ("release/0.190", bp.OWED),
                ("release/0.188", bp.OWED),
            ],
        )
        self.assertEqual(
            out[2:],
            [
                f"- [`release/0.190`]({WEB}/tree/release/0.190): `#7 {b[:12]}` (1 unclassifiable left out)",
                f"- [`release/0.188`]({WEB}/tree/release/0.188): none",
            ],
        )
        with (
            mock.patch.dict(os.environ, ACTIONS),
            mock.patch.object(bp, "held", held),
            mock.patch.object(bp, "pr_classes", lambda slug, since: {}),
        ):
            self.assertEqual(
                bp.patch_lines(state, "o/r").splitlines()[2],
                f"- [`release/0.190`]({WEB}/tree/release/0.190): `#7 {b[:12]}` (1 unclassifiable left out)",
            )
        with mock.patch.object(bp, "held", held):
            self.assertTrue(
                bp.patch_lines({"branches": state["branches"][:1]}, "o/r").endswith(
                    "no stabilized line"
                )
            )

    def test_a_failing_line_is_reported_not_raised(self):
        ga = {"tag": "v0.190.0", "pushed_at": "2026-08-01T00:00:00Z"}
        state = {
            "branches": [
                {
                    "branch": "release/0.190",
                    "state": "stabilized",
                    "targets": {"cloud": {"ga": ga}},
                },
            ]
        }

        def held(*a, **k):
            raise RuntimeError("gh pr list (exit 1): rate limited")

        with (
            mock.patch.object(bp, "held", held),
            mock.patch.object(bp, "pr_classes", lambda slug, since: {}),
            contextlib.redirect_stdout(io.StringIO()),
        ):
            out = bp.patch_lines(state, "o/r").splitlines()
        self.assertEqual(
            out[2:],
            [
                f"- [`release/0.190`]({WEB}/tree/release/0.190): patch list unavailable (see the run log)",
            ],
        )


class MissedPicks(unittest.TestCase):
    STATE = {
        "branches": [
            {"branch": "release/0.191", "state": "stabilizing", "targets": {}},
            {"branch": "release/0.190", "state": "stabilizing", "targets": {}},
            {"branch": "release/0.188", "state": "stabilized", "targets": {}},
            {"branch": "release/0.187", "state": "past-eos", "targets": {}},
        ]
    }
    B = "b" * 40

    def setUp(self):
        self.held_calls, self.listed = [], []
        conflict = lambda n, base: {
            "number": n,
            "url": f"https://x/{n}",
            "baseRefName": base,
            "createdAt": "2026-10-01T00:00:00Z",
        }
        # gh pr list --label backport-conflict, per repo: every base, filtered by conflict_prs.
        self.prs = {
            "o/r": [conflict(12, "release/0.191"), conflict(13, "release/0.188")],
            "Zipstack/unstract": [conflict(30, "release/0.191")],
        }
        self.rows = {
            "release/0.191": [(self.B, "rc", "#7", "t")],
            "release/0.190": [],
        }
        self.cut = {"release/0.191": "2026-10-20", "release/0.190": "2026-09-15"}

    def held(self, slug, repo, branch, accept, cache):
        self.held_calls.append((branch, accept))
        return self.rows[branch]

    def gh(self, *a, **k):
        return json.dumps(self.prs[a[a.index("-R") + 1]])

    def git(self, repo, *a):
        if a[0] == "merge-base":
            return a[-1]
        return self.cut[a[-1].removeprefix("origin/")]

    def missed(self, others=("Zipstack/unstract",), **patches):
        with (
            mock.patch.object(bp, "held", patches.get("held", self.held)),
            mock.patch.object(bp, "gh", patches.get("gh", self.gh)),
            mock.patch.object(bp.rm, "git", patches.get("git", self.git)),
            mock.patch.object(
                bp, "pr_classes", lambda slug, since: self.listed.append(since) or {}
            ),
            contextlib.redirect_stdout(io.StringIO()),
        ):
            return bp.missed_picks(self.STATE, others, "o/r").splitlines()

    def test_line_per_stabilizing_line(self):
        self.assertEqual(
            self.missed()[2:],
            [
                f"- [`release/0.191`]({WEB}/tree/release/0.191): owed `#7`; conflict PRs "
                f"[o/r#12]({GH}/o/r/pull/12), [Zipstack/unstract#30]({GH}/Zipstack/unstract/pull/30)",
                f"- [`release/0.190`]({WEB}/tree/release/0.190): owed none; conflict PRs none",
            ],
        )
        self.assertEqual(
            self.held_calls, [("release/0.191", bp.OWED), ("release/0.190", bp.OWED)]
        )
        self.assertEqual(self.listed, ["2026-09-15"])  # one listing, from the oldest cut

    def test_links_under_actions(self):
        with mock.patch.dict(os.environ, ACTIONS):
            line = self.missed()[2]
        web = "https://github.com"
        self.assertEqual(
            line,
            f"- [`release/0.191`]({WEB}/tree/release/0.191): owed `#7`; conflict PRs "
            f"[o/r#12]({web}/o/r/pull/12), [Zipstack/unstract#30]({web}/Zipstack/unstract/pull/30)",
        )

    def test_same_repo_listed_once(self):  # the OSS repo's own State run
        self.assertEqual(
            self.missed(others=("o/r",))[2],
            f"- [`release/0.191`]({WEB}/tree/release/0.191): owed `#7`; conflict PRs [o/r#12]({GH}/o/r/pull/12)",
        )

    def test_no_stabilizing_line(self):
        state = {"branches": self.STATE["branches"][2:]}
        with mock.patch.object(bp, "held", self.held):
            out = bp.missed_picks(state, (), "o/r")
        self.assertTrue(out.endswith("no stabilizing line"))
        self.assertEqual(self.held_calls, [])

    def test_failures_are_reported_not_raised(self):
        def fail(*a, **k):
            raise RuntimeError("gh pr list (exit 1): gh: Server Error (HTTP 502)")

        out = self.missed(held=fail, gh=fail, git=fail)
        self.assertEqual(
            out[2],
            f"- [`release/0.191`]({WEB}/tree/release/0.191): owed patch list unavailable (see the run log); "
            "conflict PRs unavailable (see the run log)",
        )
        self.assertEqual(
            self.listed, []
        )  # no cut date: each commit is looked up on its own


class PushSummary(unittest.TestCase):
    def setUp(self):  # plain-text links, whatever the shell exports
        self.env = mock.patch.dict(
            os.environ, {"GITHUB_SERVER_URL": "", "GITHUB_REPOSITORY": ""}
        )
        self.env.start()
        self.addCleanup(self.env.stop)

    def test_next_step_first_match_wins(self):
        row = lambda **k: bp.status_row(
            "release/0.192",
            "stabilizing",
            **{
                "tag": "v0.192.0-rc.2",
                "unbuilt": 0,
                "missing": 0,
                "conflicts": [],
                "held_n": 0,
                **k,
            },
        )
        self.assertEqual(
            row(conflicts=[243], held_n=4, unbuilt=1),
            "| `release/0.192` | stabilizing | `v0.192.0-rc.2` · all built | 0 | 1 conflict, 4 held | resolve #243 |".replace(
                "all built", "+1 not built"
            ),
        )
        self.assertTrue(
            row(held_n=4, unbuilt=1).endswith(
                "| 4 held | confirm 4 held backport/ga fixes |"
            )
        )
        self.assertTrue(
            row(held_n=1, unbuilt=1).endswith(
                "| 1 held | confirm 1 held backport/ga fix |"
            )
        )
        self.assertTrue(row(unbuilt=1).endswith("+1 not built | 0 | - | Take RC |"))
        self.assertTrue(row().endswith("all built | 0 | - | Promote |"))
        self.assertTrue(
            row(tag="v0.192.0").endswith("`v0.192.0` · all built | 0 | - | - |")
        )
        self.assertIn("| none |", row(tag=None, unbuilt=None))

    def test_latest_tag_counts_since_any_tag(self):
        with tempfile.TemporaryDirectory() as repo:
            rm.git(repo, "init", "-q", "-b", "release/0.1")
            commit = lambda m: dev_git(repo, "commit", "-q", "--allow-empty", "-m", m)
            commit("cut")
            rm.git(repo, "tag", "v0.1.0-rc.1")
            rm.git(repo, "tag", "v0.1.0")  # promoted: same commit, the stable tag wins
            rm.git(
                repo, "tag", "v0.10.0"
            )  # another line's tag on the same commit is not this line's
            rm.git(repo, "update-ref", "refs/remotes/origin/release/0.1", "HEAD")
            self.assertEqual(bp.latest_tag(repo, "release/0.1"), ("v0.1.0", 0))
            commit("fix")
            rm.git(repo, "tag", "v0.1.1-rc.1")
            commit("fix 2")
            rm.git(repo, "update-ref", "refs/remotes/origin/release/0.1", "HEAD")
            self.assertEqual(
                bp.latest_tag(repo, "release/0.1"), ("v0.1.1-rc.1", 1)
            )  # since the RC, not since v0.1.0

    def test_stale_mark_from_five_days(self):
        self.assertEqual(bp.stale(4), "4 days")
        self.assertEqual(bp.stale(5), "5 days ⚠")
        self.assertEqual(bp.stale(1), "1 day")

    def test_quiet_push_is_one_line(self):
        self.assertEqual(
            bp.push_summary(
                "Backport · push `abc1234` (#250, not a fix)", ["| row |"], [], []
            ),
            [
                "Backport · push `abc1234` (#250, not a fix) · nothing picked, nothing pending"
            ],
        )
        out = bp.push_summary(
            "Backport · push `abc1234` (#251, fix)", ["| row |"], ["- done"], []
        )
        self.assertEqual(out[0], "### Backport · push `abc1234` (#251, fix)")
        self.assertIn("**This run**", out)
        out = bp.push_summary(
            "Backport · push `abc1234` (#252, not a fix)", ["| row |"], [], ["<details>"]
        )
        self.assertIn(
            "**This run:** nothing picked", out
        )  # something pending: never the quiet line

    def test_this_run_and_pending(self):
        a = "a" * 40
        rows = [
            (a, "#251", "rc", "release/0.192", "merged 1234567 (#260)", "-"),
            (
                a,
                "#251",
                "rc",
                "release/0.190",
                "pr https://github.com/o/r/pull/261",
                "-",
            ),
            (a, "#251", "rc", "release/0.189", "skipped: already on branch", "-"),
            (a, "#251", "rc", "release/0.188", "merged 89abcde (#262, retried)", "-"),
        ]
        self.assertEqual(
            bp.this_run(rows),
            [
                "- #251 → `release/0.192`: merged as `1234567` (#260)",
                "- #251 → `release/0.190`: conflict, #261 to resolve",
                "- #251 → `release/0.188`: merged as `89abcde` (#262)",
            ],
        )
        out = bp.pending_block(
            [(261, "release/0.190", 6)],
            [
                (a, "release/0.190", "ga", "#247", 2),
                (a, "release/0.189", "ga", "#247", 2),
            ],
        )
        self.assertEqual(out[0], "<details><summary>Pending (2)</summary>")
        self.assertIn("- #261 on `release/0.190` · open 6 days ⚠", out)
        self.assertIn(
            "- #247 ga → `release/0.190`, `release/0.189` · merged 2 days ago", out
        )
        self.assertIn(
            "gh workflow run backport.yaml -f commits=#247 -f lines=0.190,0.189 "
            "-f patch_released_lines=true",
            out,
        )
        self.assertEqual(bp.pending_block([], []), [])


class ConflictPRs(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.d = tmp.name
        with open(os.path.join(self.d, "gh"), "w") as fh:
            fh.write(
                f'#!/bin/sh\necho "$GH_TOKEN $*" >> {self.d}/gh.log\n[ -e {self.d}/fail ] && exit 1\ncat {self.d}/prs.json\n'
            )
        os.chmod(os.path.join(self.d, "gh"), 0o755)
        p = mock.patch.dict(
            os.environ, {"PATH": f"{self.d}:{os.environ['PATH']}", "GH_TOKEN": "cloud"}
        )
        p.start()
        self.addCleanup(p.stop)
        pr = lambda n, base: {
            "number": n,
            "url": f"https://x/{n}",
            "baseRefName": base,
            "createdAt": "2026-10-01T00:00:00Z",
        }
        with open(os.path.join(self.d, "prs.json"), "w") as fh:
            json.dump([pr(7, "release/1.7"), pr(8, "release/1.6")], fh)

    def log(self):
        with open(os.path.join(self.d, "gh.log")) as fh:
            return fh.read()

    def test_lists_one_line_as_the_token(self):
        self.assertEqual(
            [p["number"] for p in bp.conflict_prs("o/oss", "release/1.7", "oss")], [7]
        )
        self.assertEqual([p["number"] for p in bp.conflict_prs("o/r")], [7, 8])
        log = self.log().splitlines()
        self.assertTrue(
            log[0].startswith(
                "oss pr list -R o/oss --label backport-conflict --state open"
            ),
            log[0],
        )
        self.assertTrue(log[1].startswith("cloud pr list -R o/r "), log[1])

    def test_open_conflicts(self):
        with mock.patch("sys.stdout", new_callable=io.StringIO) as out:
            refs, note = bp.open_conflicts(
                [("o/r", "release/1.6", None), ("o/oss", "release/1.7", "oss")], "error"
            )
        self.assertEqual(refs, ["o/r#8", "o/oss#7"])
        self.assertIn(
            "::error::Open backport conflict PR o/oss#7 on release/1.7", out.getvalue()
        )
        self.assertEqual(
            note,
            "⚠ Open backport conflict PRs: [o/r#8](https://x/8) on `release/1.6`, "
            "[o/oss#7](https://x/7) on `release/1.7`",
        )
        with mock.patch("sys.stdout", new_callable=io.StringIO):
            self.assertEqual(
                bp.open_conflicts([("o/r", "release/1.9", None)]), ([], None)
            )

    def test_failed_listing_raises(self):
        open(os.path.join(self.d, "fail"), "w").close()
        with self.assertRaises(RuntimeError):
            bp.open_conflicts([("o/r", "release/1.7", None)])


class FinishOpen(unittest.TestCase):
    def setUp(self):
        self.softs, self.soft_rc = [], 0
        self.tmp = tempfile.TemporaryDirectory()
        d = self.tmp.name
        g = (
            lambda *a, cwd=d + "/w": subprocess.run(
                ["git", "-C", cwd, *a], check=True, capture_output=True, text=True
            ).stdout.strip()
        )
        subprocess.run(
            ["git", "init", "-q", "--bare", "-b", "main", d + "/o"], check=True
        )
        subprocess.run(
            ["git", "clone", "-q", d + "/o", d + "/w"], check=True, capture_output=True
        )
        g(
            "-c",
            "user.name=t",
            "-c",
            "user.email=t@t",
            "commit",
            "-q",
            "--allow-empty",
            "-m",
            "base",
        )
        g("push", "-q", "origin", "HEAD:refs/heads/release/1.0")
        g(
            "-c",
            "user.name=t",
            "-c",
            "user.email=t@t",
            "commit",
            "-q",
            "--allow-empty",
            "-m",
            "fix: x\n\n(cherry picked from commit " + "a" * 40 + ")",
        )
        g("push", "-q", "origin", "HEAD:refs/heads/backport/1.0/aaaaaaa")
        g("fetch", "-q", "origin")
        self.oid, self.g, self.merged = g("rev-parse", "HEAD"), g, []
        self.cwd = os.getcwd()
        os.chdir(d + "/w")

    def tearDown(self):
        os.chdir(self.cwd)
        self.tmp.cleanup()

    def finish(self, labels=(), oid=None, prs=None, author=BOT):
        listing = [
            {
                "number": 4,
                "headRefOid": oid or self.oid,
                "labels": [{"name": x} for x in labels],
                "author": author,
            }
        ]
        squash = lambda slug, pr, msg: self.merged.append((pr["number"], msg)) or True
        with (
            mock.patch.object(
                bp, "gh", return_value=json.dumps(listing if prs is None else prs)
            ),
            mock.patch.object(bp.bm, "squash", squash),
            mock.patch.object(bp, "soft", side_effect=self.soft),
        ):
            return bp.finish_open("o/r", "release/1.0", "backport/1.0/aaaaaaa")

    def soft(self, what, *args):
        self.softs.append(args)
        return mock.Mock(returncode=self.soft_rc)

    def push(
        self, msg, path=None
    ):  # replace the head's one commit with one carrying msg (and a file at path)
        self.g("reset", "-q", "--hard", "origin/release/1.0")
        if path:
            with open(path, "w") as f:
                f.write("<<<<<<< HEAD\na\n=======\nb\n>>>>>>> fix\n")
            self.g("add", path)
        self.g(
            "-c",
            "user.name=t",
            "-c",
            "user.email=t@t",
            "commit",
            "-q",
            "--allow-empty",
            "-m",
            msg,
        )
        self.g("push", "-q", "-f", "origin", "HEAD:refs/heads/backport/1.0/aaaaaaa")
        return self.g("rev-parse", "HEAD")

    def test_clean_pick_merged_with_its_trailer(self):
        out = self.finish()
        self.assertEqual(out[0], "merged")
        self.assertEqual(self.merged[0][0], 4)
        self.assertIn("(cherry picked from commit " + "a" * 40 + ")", self.merged[0][1])
        # The push summary parses this detail: a format change must not drop the row from it.
        row = ("a" * 40, "#1", "rc", "release/1.0", " ".join(out), "-")
        self.assertEqual(len(bp.this_run([row])), 1)

    def test_waits_for_a_person(self):
        pending = ("skipped", "conflict PR pending on `backport/1.0/aaaaaaa`")
        self.assertEqual(
            self.finish(labels=["backport-conflict"]), pending
        )  # conflict PR
        self.g(
            "-c",
            "user.name=t",
            "-c",
            "user.email=t@t",
            "commit",
            "-q",
            "--allow-empty",
            "-m",
            "person",
        )
        self.g("push", "-q", "origin", "HEAD:refs/heads/backport/1.0/aaaaaaa")
        # A person's commit on top of the bot's unlabelled PR: failed, so the run's summary shows it.
        self.assertEqual(
            self.finish(oid=self.g("rev-parse", "HEAD")),
            (
                "failed",
                "#4 has 2 commits, not the one pick: not merged; label it backport-conflict, then merge it, "
                "or close it to decline",
            ),
        )
        # A head at the release tip adds nothing: close, not merge.
        self.assertEqual(
            self.finish(oid=self.g("rev-parse", f"{self.oid}^")),
            (
                "failed",
                "#4 has 0 commits, not the one pick: not merged; its head has no pick on release/1.0: delete "
                "backport/1.0/aaaaaaa (this closes #4), and the next Backport run treats the fix as not picked",
            ),
        )
        self.assertEqual(self.merged, [])

    def test_head_without_a_pr_fails(self):
        out = self.finish(
            prs=[]
        )  # pushed just now: the run that pushed it has yet to open its PR
        self.assertEqual(
            out,
            (
                "skipped",
                "head backport/1.0/aaaaaaa is 0 min old with no open PR: another run is picking it",
            ),
        )
        # No PR open or closed: a create that failed outright. The head goes, so the next run re-picks.
        with mock.patch.object(bp, "PICK_TIMEOUT", 0):
            out = self.finish(prs=[])
        self.assertEqual(
            out,
            (
                "failed",
                "head backport/1.0/aaaaaaa had no PR: deleted it, so the next Backport run picks the fix again",
            ),
        )
        self.assertEqual(
            self.softs,
            [
                (
                    "gh",
                    "api",
                    "-X",
                    "DELETE",
                    "repos/o/r/git/refs/heads/backport/1.0/aaaaaaa",
                )
            ],
        )
        self.soft_rc = 1
        with mock.patch.object(bp, "PICK_TIMEOUT", 0):
            out = self.finish(prs=[])
        self.assertEqual(
            out,
            (
                "failed",
                "head backport/1.0/aaaaaaa has no PR and its delete failed: delete it, then rerun",
            ),
        )
        # A head moved onto the release tip: reopening its PR would park it with nothing to merge.
        self.g(
            "push", "-q", "-f", "origin", f"{self.oid}^:refs/heads/backport/1.0/aaaaaaa"
        )
        with mock.patch.object(bp, "PICK_TIMEOUT", 0):
            out = self.finish(prs=[])
        self.assertEqual(
            out,
            (
                "failed",
                "head backport/1.0/aaaaaaa exists with no open PR: delete it, then rerun",
            ),
        )

    def test_head_of_a_closed_pr_asks_for_the_record_job(self):
        # Its decline did not land: deleting the head would pick the declined fix again.
        listings = iter(
            [[], [{"number": 4, "state": "MERGED"}, {"number": 3, "state": "CLOSED"}]]
        )
        with (
            mock.patch.object(bp, "PICK_TIMEOUT", 0),
            mock.patch.object(
                bp, "gh", side_effect=lambda *a: json.dumps(next(listings))
            ),
        ):
            out = bp.finish_open("o/r", "release/1.0", "backport/1.0/aaaaaaa")
        self.assertEqual(
            out,
            (
                "failed",
                "head backport/1.0/aaaaaaa exists and its PR #3 is closed, but no decline is recorded on "
                "release/1.0: re-run the Backport record job for #3, then rerun",
            ),
        )
        # An empty head has no pick to decline: the record job would not help.
        self.g(
            "push", "-q", "-f", "origin", f"{self.oid}^:refs/heads/backport/1.0/aaaaaaa"
        )
        listings = iter([[], [{"number": 3, "state": "CLOSED"}]])
        with (
            mock.patch.object(bp, "PICK_TIMEOUT", 0),
            mock.patch.object(
                bp, "gh", side_effect=lambda *a: json.dumps(next(listings))
            ),
        ):
            out = bp.finish_open("o/r", "release/1.0", "backport/1.0/aaaaaaa")
        self.assertEqual(
            out,
            (
                "failed",
                "head backport/1.0/aaaaaaa exists with no open PR: delete it, then rerun",
            ),
        )

    def test_not_the_bots_pick_is_not_squashed(self):
        # The squash bypasses the release ruleset: nothing but the bot's own pick may land through it.
        for author in (
            {"login": "dev", "is_bot": False},
            {"login": "app/other", "is_bot": True},
        ):
            for labels in (
                [],
                ["backport-conflict"],
            ):  # labelled too: it never waits as a conflict PR
                out = self.finish(author=author, labels=labels)
                self.assertEqual(out[0], "failed")
                self.assertIn(
                    "not by the bot (@app/zipstack-push-to-main): not merged", out[1]
                )
        self.g(
            "-c",
            "user.name=t",
            "-c",
            "user.email=t@t",
            "commit",
            "-q",
            "--allow-empty",
            "-m",
            "second",
        )
        out = self.finish(
            oid=self.g("rev-parse", "HEAD"), author={"login": "dev", "is_bot": False}
        )
        self.assertEqual(out[0], "failed")
        self.assertIn("not by the bot", out[1])
        for msg in ("fix: x", "fix: x\n\n(cherry picked from commit " + "b" * 40 + ")"):
            out = self.finish(oid=self.push(msg))
            self.assertEqual(
                out,
                (
                    "failed",
                    "#4: its commit lacks the pick trailer backport/1.0/aaaaaaa names: not merged",
                ),
            )
        self.assertEqual(self.merged, [])

    def test_unlabelled_conflict_pick_is_not_squashed(self):
        trailer = "(cherry picked from commit " + "a" * 40 + ")"
        for oid in (
            self.push(f"fix: x\n\n{trailer}", path="f.txt"),  # markers in the tree
            self.push(f"fix: x\n\n{trailer}\n\nConflicts:\n\tf.txt\n"),
        ):  # the block pick writes
            out = self.finish(oid=oid)
            self.assertEqual(out[0], "failed")
            self.assertIn("without the backport-conflict label", out[1])
        self.assertEqual(self.merged, [])


class Pick(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        d = tmp.name
        self.g = g = lambda *a: subprocess.run(
            ["git", "-C", d + "/w", "-c", "user.name=t", "-c", "user.email=t@t", *a],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
        subprocess.run(
            ["git", "init", "-q", "--bare", "-b", "main", d + "/o"], check=True
        )
        subprocess.run(
            ["git", "clone", "-q", d + "/o", d + "/w"], check=True, capture_output=True
        )
        self.write(d + "/w/a.txt", "x\n")
        g("add", "a.txt")
        g("commit", "-q", "-m", "base")
        g("push", "-q", "origin", "HEAD:main", "HEAD:release/1.0")
        self.write(d + "/w/a.txt", "y\n")
        g("commit", "-q", "-am", "fix: y (#5)")
        g("push", "-q", "origin", "HEAD:main")
        self.fix = g("rev-parse", "HEAD")
        g("fetch", "-q", "origin")
        self.d, cwd = d, os.getcwd()
        os.chdir(d + "/w")
        self.addCleanup(os.chdir, cwd)
        self.calls = []
        self.labels = "backport/rc\nbackport-conflict\nbackport/x\nother"

    @staticmethod
    def write(path, text):
        with open(path, "w") as f:
            f.write(text)

    def gh(self, *a, token=None, retry=True):
        self.calls.append(a)
        if a[:2] == ("api", "repos/o/r/pulls/5"):
            return self.labels
        return "https://github.com/o/r/pull/8"

    def pick(self):
        with (
            mock.patch.object(bp, "gh", self.gh),
            mock.patch.object(bp.bm, "squash", return_value=True),
            mock.patch.object(bp, "soft", return_value=None),
        ):
            return bp.pick("o/r", self.fix, "release/1.0", "UN-1 [FIX] y", "#5")

    def test_clean_pick_carries_fix_labels(self):
        self.assertEqual(self.pick()[0], "merged")
        create = next(a for a in self.calls if a[:2] == ("pr", "create"))
        self.assertEqual(
            [create[i + 1] for i, x in enumerate(create) if x == "--label"],
            ["backport/rc"],
        )

    def test_conflict_pick_carries_fix_labels(self):
        self.g("checkout", "-q", "-B", "rel", "origin/release/1.0")
        self.write(self.d + "/w/a.txt", "z\n")
        self.g("commit", "-q", "-am", "z")
        self.g("push", "-q", "origin", "HEAD:release/1.0")
        self.g("fetch", "-q", "origin")
        self.labels = "backport/ga\nother"
        self.assertEqual(self.pick()[0], "pr")
        create = next(a for a in self.calls if a[:2] == ("pr", "create"))
        self.assertEqual(
            [create[i + 1] for i, x in enumerate(create) if x == "--label"],
            ["backport-conflict", "backport/ga"],
        )

    def test_empty_pick_names_the_decline(self):
        self.g("checkout", "-q", "-B", "rel", "origin/release/1.0")
        self.write(self.d + "/w/a.txt", "y\n")
        self.write(self.d + "/w/b.txt", "b\n")
        self.g("add", ".")
        self.g("commit", "-q", "-m", "y and b, by hand")
        self.g("push", "-q", "origin", "HEAD:release/1.0")
        self.g("fetch", "-q", "origin")
        out = self.pick()
        self.assertEqual(out[0], "failed")
        self.assertIn(f"pick of {self.fix[:7]} onto release/1.0 is empty", out[1])
        self.assertIn(
            f"`(cherry picked from commit {self.fix})` and `Declined: already on release/1.0`",
            out[1],
        )
        self.assertNotIn(("pr", "create"), [a[:2] for a in self.calls])

    def test_silent_failure_names_the_exit(self):
        real = bp.run
        fake = lambda *a, **k: (
            subprocess.CompletedProcess(a, 3, "", "")
            if a[:3] == ("git", "cherry-pick", "-x")
            else real(*a, **k)
        )
        with mock.patch.object(bp, "run", fake):
            self.assertEqual(self.pick(), ("failed", "cherry-pick exit 3"))


class OpenPR(unittest.TestCase):
    URL = "https://github.com/o/r/pull/8"

    def open_pr(self, create, listing):
        fake, waits = (
            FakeGh(
                lambda a: (
                    create(a)
                    if a[1:3] == ("pr", "create")
                    else listing(a)
                    if a[1:3] == ("pr", "list")
                    else (0, "", "")
                )
            ),
            [],
        )
        with (
            mock.patch.object(bp.bm.subprocess, "run", fake),
            mock.patch("sys.stdout", io.StringIO()),
        ):
            try:
                out = bp._open_pr(
                    "o/r", "release/1.0", "backport/1.0/abc1234", "b", sleep=waits.append
                )
            except RuntimeError as e:
                out = e
        deletes = fake.count(
            "api", "-X", "DELETE", "repos/o/r/git/refs/heads/backport/1.0/abc1234"
        )
        return out, fake.count("pr", "create"), deletes, waits

    def test_502_but_opened_returns_the_pr(self):
        out = self.open_pr(
            lambda a: (1, "", BAD_GATEWAY), lambda a: (0, self.URL + "\n", "")
        )
        self.assertEqual(out, (self.URL, 1, 0, []))

    def test_502_not_opened_is_retried(self):
        create = queue((1, "", BAD_GATEWAY), (0, self.URL + "\n", ""))
        out = self.open_pr(create, lambda a: (0, "", ""))
        self.assertEqual(out, (self.URL, 2, 0, [4]))

    def test_never_listed_keeps_the_head(self):
        # GitHub may have opened a PR the listing does not show yet: deleting the head would close it.
        out, creates, deletes, waits = self.open_pr(
            lambda a: (1, "", BAD_GATEWAY), lambda a: (0, "", "")
        )
        self.assertIn("502 Bad Gateway", str(out))
        self.assertEqual((creates, deletes, waits), (5, 0, [4, 8, 16, 32]))

    def test_every_gh_call_retries_a_transient_failure(self):
        fake = FakeGh(queue((1, "", BAD_GATEWAY), (0, "ok\n", "")))
        with (
            mock.patch.object(bp.bm.subprocess, "run", fake),
            mock.patch.object(bp.bm.time, "sleep"),
            mock.patch("sys.stdout", io.StringIO()),
        ):
            self.assertEqual(bp.gh("api", "x"), "ok")
        self.assertEqual(len(fake.calls), 2)

    def test_client_error_keeps_the_head_and_is_not_retried(self):
        out, creates, deletes, waits = self.open_pr(
            lambda a: (1, "", NOT_FOUND), lambda a: (0, self.URL, "")
        )
        self.assertIsInstance(out, RuntimeError)
        self.assertEqual((creates, deletes, waits), (1, 0, []))


class PickRow(unittest.TestCase):
    def test_relevance_failure_never_fails_the_pick(self):
        with (
            mock.patch.object(
                bp.rm, "relevance", side_effect=RuntimeError("bad | path\nsecond line")
            ),
            mock.patch.object(bp, "pick", return_value=("merged", "abc1234 (#8)")),
            mock.patch("sys.stdout", io.StringIO()),
        ):
            row = bp.pick_row("o/r", "c" * 40, "release/1.0", "rc", "#5", "t")
        self.assertEqual(row[4], "merged abc1234 (#8)")
        self.assertEqual(row[5], "unknown (RuntimeError: bad \\| path)")

    def test_failure_names_its_type(self):
        with (
            mock.patch.object(bp.rm, "relevance", return_value="relevant"),
            mock.patch.object(bp, "pick", side_effect=KeyError("x")),
            mock.patch.object(bp, "run"),
            mock.patch("sys.stdout", io.StringIO()),
            mock.patch("sys.stderr", io.StringIO()) as err,
        ):
            row = bp.pick_row("o/r", "c" * 40, "release/1.0", "rc", "#5", "t")
        self.assertEqual(row[4], "failed: KeyError: 'x'")
        self.assertIn("Traceback", err.getvalue())


class PushTitle(unittest.TestCase):
    def test_unclassifiable_push_still_summarised(self):
        with (
            mock.patch.object(bp, "fix_class", side_effect=ValueError("no [TYPE]")),
            mock.patch("sys.stdout", new_callable=io.StringIO) as out,
        ):
            self.assertTrue(
                bp.push_title("o/r", "c" * 40).endswith(f" (-, {bp.UNCLASSIFIABLE})")
            )
        self.assertIn("::warning::ccccccc: fix class: no [TYPE]", out.getvalue())

    def test_unlabelled_push_keeps_its_pr(self):
        row = (bp.UNCLASSIFIABLE, "#8", "UN-8 [FIX] x (no backport label: ...)")
        with (
            mock.patch.object(bp, "fix_class", return_value=row),
            mock.patch("sys.stdout", new_callable=io.StringIO) as out,
        ):
            title = bp.push_title("o/r", "c" * 40)
        self.assertIn(f"{bp.UNCLASSIFIABLE})", title)
        self.assertIn("#8", title)
        self.assertIn(
            "::warning::ccccccc: fix class: UN-8 [FIX] x (no backport label",
            out.getvalue(),
        )

    def test_push_with_no_pr_is_unclassifiable(self):
        with (
            mock.patch.object(bp, "fix_class", return_value=(None, "no PR", None)),
            mock.patch("sys.stdout", new_callable=io.StringIO) as out,
        ):
            title = bp.push_title("o/r", "c" * 40)
        self.assertTrue(title.endswith(f" (no PR, {bp.UNCLASSIFIABLE})"), title)
        self.assertIn("::warning::ccccccc: fix class: no PR found", out.getvalue())


class DispatchCommit(unittest.TestCase):
    def test_unclassifiable_named_commit_fails(self):
        with (
            mock.patch.object(bp, "fix_class", side_effect=ValueError("no [TYPE]")),
            mock.patch("sys.stdout", io.StringIO()),
        ):
            rows = bp._dispatch_commit("o/r", {}, "c" * 40, False, [], [])
        self.assertEqual(rows, [("c" * 40, "?", "error", "-", "failed: no [TYPE]", "-")])

    def test_unlabelled_named_commit_fails_with_its_pr(self):
        pr = {"number": 8, "title": "UN-8 [FIX] x", "labels": []}
        targets = {
            "rc": ["release/0.190"],
            "ga": [
                {"branch": "release/0.190", "needs_rm_confirmation": False},
                {"branch": "release/0.187", "needs_rm_confirmation": True},
            ],
        }
        with mock.patch("sys.stdout", io.StringIO()):
            rows = bp._dispatch_commit(
                "o/r", targets, "c" * 40, True, [], [], named_pr=pr
            )
        self.assertEqual(rows[0][1:4], ("#8", "error", "-"))
        self.assertRegex(rows[0][4], r"^failed: UN-8 \[FIX\] x \(no backport label: ")


class Soft(unittest.TestCase):
    def test_failure_warns(self):
        with mock.patch("sys.stdout", new_callable=io.StringIO) as out:
            bp.soft("delete of h", "sh", "-c", "echo gone >&2; exit 3")
            bp.soft("delete of h", "true")
        self.assertEqual(out.getvalue(), "::warning::delete of h failed (exit 3): gone\n")


class Relevance(unittest.TestCase):
    """relmgr.relevance: are the line versions a main fix edits on the branch?"""

    def test_cases(self):
        with tempfile.TemporaryDirectory() as d:
            g = lambda *a: subprocess.run(
                ["git", "-C", d, "-c", "user.name=t", "-c", "user.email=t@t", *a],
                check=True,
                capture_output=True,
                text=True,
            ).stdout.strip()

            def commit(msg, **files):
                for name, text in files.items():
                    with open(os.path.join(d, name.replace("_", " ")), "w") as f:
                        f.write(text)
                g("add", "-A")
                g("commit", "-q", "-m", msg)
                return g("rev-parse", "HEAD")

            g("init", "-q", "-b", "main")
            commit("base", a="1\n2\n", b="1\n", c_d="1\n")
            g("branch", "release/1.0")
            main = commit("rewrite a:2 after the cut", a="1\nTWO\n", b="1\nnew\n")
            rel = lambda **files: (
                g("checkout", "-q", "-B", "fix", main)
                or bp.rm.relevance(d, commit("fix", **files), "release/1.0")
            )
            self.assertEqual(rel(a="ONE\nTWO\n"), "relevant")  # a:1 is as on the branch
            self.assertEqual(
                rel(a="ONE\nTWO!\n"), "partial"
            )  # a:1 from the cut, a:2 from after it
            self.assertEqual(
                rel(b="1\nnewer\n"), "not-relevant"
            )  # b:2 exists only after the cut
            self.assertEqual(rel(e="added\n"), "unknown")  # a new file: no pre-image
            self.assertEqual(
                rel(c_d="1\nadded\n"), "unknown"
            )  # lines added to an existing file
            self.assertEqual(rel(c_d="one\n"), "relevant")  # a path with a space


class PickGit(unittest.TestCase):
    PATH = "f"

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        ident = {
            "GIT_AUTHOR_NAME": "Dev",
            "GIT_AUTHOR_EMAIL": "dev@example.com",
            "GIT_COMMITTER_NAME": "Dev",
            "GIT_COMMITTER_EMAIL": "dev@example.com",
            "GIT_CONFIG_GLOBAL": os.devnull,
            "GIT_CONFIG_NOSYSTEM": "1",
        }
        p = mock.patch.dict(os.environ, ident)
        p.start()
        self.addCleanup(p.stop)
        origin, self.dev, self.work = (
            os.path.join(tmp.name, d) for d in ("origin", "dev", "work")
        )
        rm.git(tmp.name, "init", "-q", "--bare", "-b", "main", origin)
        rm.git(tmp.name, "clone", "-q", origin, self.dev)
        self.commit(self.PATH, "a\n", "base")
        rm.git(self.dev, "push", "-q", "origin", "main")
        rm.git(self.dev, "checkout", "-q", "-b", "release/1.0")
        self.commit(self.PATH, "b\n", "line change")
        rm.git(self.dev, "push", "-q", "origin", "release/1.0")
        rm.git(self.dev, "checkout", "-q", "main")
        self.fix = self.commit(self.PATH, "c\n", "fix")
        rm.git(self.dev, "push", "-q", "origin", "main")
        rm.git(tmp.name, "clone", "-q", origin, self.work)
        with open(os.path.join(self.work, "state.json"), "w") as f:
            f.write("{}\n")  # relstate's output, untracked in the job's checkout
        cwd = os.getcwd()
        os.chdir(self.work)  # backport.REPO is "."
        self.addCleanup(os.chdir, cwd)
        self.pushed = []
        for name, fake in (
            ("push_head", lambda *a: self.pushed.append(a) or ("failed", "stop")),
            ("fix_labels", lambda *a: []),
        ):
            p = mock.patch.object(bp, name, fake)
            p.start()
            self.addCleanup(p.stop)

    def commit(self, path, text, msg):
        os.makedirs(os.path.dirname(os.path.join(self.dev, path)), exist_ok=True)
        with open(os.path.join(self.dev, path), "w") as f:
            f.write(text)
        rm.git(self.dev, "add", path)
        rm.git(self.dev, "commit", "-q", "-m", msg)
        return rm.git(self.dev, "rev-parse", "HEAD")

    def test_conflict_commit_has_no_untracked_file(self):
        self.assertEqual(
            bp.pick("o/r", self.fix, "release/1.0", "t", "#1"), ("failed", "stop")
        )
        self.assertEqual(len(self.pushed), 1)
        self.assertEqual(
            rm.git(".", "show", "-z", "--name-only", "--format=", "HEAD")
            .rstrip("\0")
            .split("\0"),
            [self.PATH],
        )
        self.assertIn(
            f"Conflicts:\n\t{self.PATH}\n", rm.git(".", "log", "-1", "--format=%B") + "\n"
        )

    def test_pick_merged_by_another_run_after_this_one_fetched(self):
        rm.git(self.dev, "checkout", "-q", "release/1.0")
        rm.git(
            self.dev,
            "commit",
            "-q",
            "--allow-empty",
            "-m",
            f"fix\n\n(cherry picked from commit {self.fix})",
        )
        rm.git(self.dev, "push", "-q", "origin", "release/1.0")
        self.assertEqual(
            bp.pick("o/r", self.fix, "release/1.0", "t", "#1"),
            ("skipped", "already on branch"),
        )
        self.assertEqual(self.pushed, [])


class PickGitPathWithSpace(PickGit):
    """The same against a conflicted path with a space and a non-ASCII name (this repo has paths with spaces)."""

    PATH = "docker (deprecated)/é.txt"


class Guards(unittest.TestCase):
    def test_resolve_refuses_an_option(self):
        with mock.patch.object(bp.rm, "resolve") as resolve:
            self.assertIsNone(bp.resolve("o/r", "#--all"))
        resolve.assert_not_called()

    def test_main_refuses_a_state_file_outside(self):
        argv = ["backport.py", "--state", "/nonexistent/state.json", "--rescan"]
        with mock.patch("sys.argv", argv), self.assertRaises(ValueError):
            bp.main()


class PickStep(unittest.TestCase):
    """backport.yaml's Pick step and backport.py's argparse are kept in step by hand: a drift fails every run."""

    def setUp(self):
        here = os.path.dirname(os.path.abspath(__file__))
        with open(os.path.join(here, "..", "workflows", "backport.yaml")) as f:
            self.yaml = f.read()
        self.run_ = self.yaml.split("- name: Pick", 1)[1].split("\n\n", 1)[0]
        self.help = subprocess.run(
            [sys.executable, os.path.join(here, "backport.py"), "--help"],
            capture_output=True,
            text=True,
            check=True,
        ).stdout

    def test_every_flag_it_passes_is_a_backport_flag(self):
        flags = set(re.findall(r"(?<![\w-])--[a-z][a-z-]*", self.run_))
        self.assertIn("--lines", flags)
        self.assertEqual(flags - set(re.findall(r"--[a-z][a-z-]*", self.help)), set())

    def test_every_input_it_reads_is_declared(self):
        inputs = self.yaml.split("jobs:", 1)[0]
        used = set(re.findall(r"inputs\.(\w+)", self.run_))
        self.assertIn("lines", used)
        self.assertEqual(
            {u for u in used if not re.search(rf"^\s+{u}:", inputs, re.M)}, set()
        )

    def test_every_variable_its_script_reads_is_set(self):
        env = self.run_.split("run: |", 1)[0]
        used = set(re.findall(r"\$\{?([A-Z_]+)", self.run_.split("run: |", 1)[1]))
        self.assertIn("PATCH_RELEASED_LINES", used)
        self.assertEqual(
            {
                u
                for u in used
                if not u.startswith(("GITHUB_", "RUNNER_"))
                and not re.search(rf"^\s+{u}:", env, re.M)
            },
            set(),
        )


TARGETS = {
    "rc": ["release/0.191"],
    "ga": [
        {"branch": "release/0.191", "needs_rm_confirmation": False},
        {"branch": "release/0.190", "needs_rm_confirmation": True},
    ],
}


class Unsettled(unittest.TestCase):
    a, b, c, d = "a" * 40, "b" * 40, "c" * 40, "d" * 40
    OWED = {
        "release/0.191": [
            (a, "rc", "#7", "UN-1 [FIX] x"),
            (b, bp.UNCLASSIFIABLE, "no PR", "y"),
            (c, "ga", "#8", "UN-2 [FIX] z"),
        ],
        "release/0.190": [(d, "ga", "#9", "UN-3 [HOT-FIX] w")],
    }

    def test_left_in_no_known_state(self):
        self.assertEqual(
            bp.unsettled(TARGETS, self.OWED, [], set()),
            [
                (self.a, "#7", "release/0.191", "rc"),
                (self.b, "no PR", "release/0.191", bp.UNCLASSIFIABLE),
                (self.c, "#8", "release/0.191", "ga"),
            ],
        )  # d is held for confirmation on the stabilized line

    def test_a_row_or_a_pick_head_settles_it(self):
        rows = [(self.a, "#7", "rc", "release/0.191", "picked", "-")]
        heads = {"backport/0.191/ccccccc"}
        self.assertEqual(
            bp.unsettled(TARGETS, self.OWED, rows, heads),
            [(self.b, "no PR", "release/0.191", bp.UNCLASSIFIABLE)],
        )
        other = [(self.a, "#7", "rc", "release/0.190", "picked", "-")]  # another line
        self.assertIn(
            (self.a, "#7", "release/0.191", "rc"),
            bp.unsettled(TARGETS, self.OWED, other, heads),
        )

    def test_plain_fix_on_a_stabilized_line_is_not_held(self):
        owed = {"release/0.190": [(self.a, bp.UNCLASSIFIABLE, "no PR", "y")]}
        self.assertEqual(
            bp.unsettled(TARGETS, owed, [], set()),
            [(self.a, "no PR", "release/0.190", bp.UNCLASSIFIABLE)],
        )

    def test_lines_name_the_way_out(self):
        with mock.patch("sys.stdout", new_callable=io.StringIO) as out:
            lines = bp.unsettled_lines(
                [
                    (self.a, "#7", "release/0.191", "rc"),
                    (self.b, "no PR", "release/0.191", bp.UNCLASSIFIABLE),
                ],
                {self.a, self.b},
            )
        self.assertEqual(
            out.getvalue().splitlines(),
            [
                "::error::aaaaaaa (rc, PR #7) is owed on release/0.191 and was left undone: "
                f"dispatch Backport with commits={self.a[:12]} lines=0.191, or record a decline",
                f"::error::bbbbbbb ({bp.UNCLASSIFIABLE}, PR no PR) is owed on release/0.191 and was left undone: "
                "fix its PR title or labels and rerun Backport, or record a decline",
            ],
        )
        self.assertEqual(len(lines), 2)
        self.assertIn(f"[`release/0.191`]({WEB}/tree/release/0.191)", lines[0])

    def test_owed_before_this_run_says_so(self):
        left = [
            (self.a, "#7", "release/0.191", "rc"),
            (self.b, "no PR", "release/0.191", bp.UNCLASSIFIABLE),
        ]
        with mock.patch("sys.stdout", new_callable=io.StringIO) as out:
            lines = bp.unsettled_lines(left, {self.a})
        self.assertEqual(
            out.getvalue().splitlines()[1],
            f"::error::bbbbbbb ({bp.UNCLASSIFIABLE}, PR no PR) is owed on release/0.191 and "
            "was owed before this run, not caused by it: "
            "fix its PR title or labels and rerun Backport, or record a decline",
        )
        self.assertNotIn("before this run", out.getvalue().splitlines()[0])
        self.assertNotIn("before this run", lines[0])
        self.assertEqual(
            lines[1],
            f"- {bp.link_src(self.b, 'no PR')} ({bp.UNCLASSIFIABLE}) → "
            f"[`release/0.191`]({WEB}/tree/release/0.191): owed before this run, not caused by it; "
            "fix its PR title or labels and rerun Backport, or record a decline",
        )

    def test_pick_head_name(self):
        self.assertEqual(
            bp.backport_head("release/0.191", self.c), "backport/0.191/ccccccc"
        )
        out = (
            f"{self.a}\trefs/heads/backport/0.191/ccccccc\n"
            f"{self.b}\trefs/heads/backport/0.190/ddddddd\n"
        )
        with mock.patch.object(bp.rm, "git", lambda *a: out) as _:
            self.assertEqual(
                bp.backport_heads(), {"backport/0.191/ccccccc", "backport/0.190/ddddddd"}
            )
        with mock.patch.object(bp.rm, "git", lambda *a: ""):
            self.assertEqual(bp.backport_heads(), set())


class MainLeftUndone(unittest.TestCase):
    a = "a" * 40

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.state = os.path.join(tmp.name, "state.json")
        with open(self.state, "w") as f:
            json.dump({"branches": [], "backport_targets": TARGETS}, f)
        self.owed = {"release/0.191": [(self.a, "rc", "#7", "UN-1 [FIX] x")]}
        self.rows = []

    def main(self, owed=None, rows=(), heads=(), old=True):
        def owed_now(slug, targets):
            if isinstance(owed, Exception):
                raise owed
            return self.owed if owed is None else owed

        argv = ["backport.py", "--state", self.state, "--commits", "#5"]
        env = {k: v for k, v in os.environ.items() if k != "GITHUB_STEP_SUMMARY"}
        with (
            mock.patch("sys.argv", argv),
            mock.patch.dict(os.environ, env, clear=True),
            mock.patch.object(bp, "dispatch", lambda *a: (list(rows), [])),
            mock.patch.object(bp, "owed_now", owed_now),
            mock.patch.object(bp, "backport_heads", lambda: set(heads)),
            mock.patch.object(bp, "conflict_prs", lambda slug: []),
            mock.patch.object(bp, "overdue", lambda sha, now: old),
            mock.patch("sys.stdout", new_callable=io.StringIO) as out,
        ):
            code = bp.main()
        return code, out.getvalue()

    def test_owed_and_untouched_fails(self):
        code, out = self.main()
        self.assertEqual(code, 1)
        self.assertIn("::error::aaaaaaa (rc, PR #7) is owed on release/0.191", out)
        self.assertIn("**⛔ Left undone**", out)

    def test_named_but_left_undone_keeps_the_wording(self):
        other = [(self.a, "#7", "rc", "release/0.190", "picked", "-")]
        code, out = self.main(rows=other)
        self.assertEqual(code, 1)
        self.assertIn(
            "::error::aaaaaaa (rc, PR #7) is owed on release/0.191 and was left undone: ",
            out,
        )
        self.assertNotIn("before this run", out)

    def test_untouched_says_owed_before_this_run(self):
        e = "e" * 40
        named = [(e, "#5", "rc", "release/0.191", "picked", "-")]
        code, out = self.main(rows=named)
        self.assertEqual(code, 1)
        self.assertIn(
            "::error::aaaaaaa (rc, PR #7) is owed on release/0.191 and "
            "was owed before this run, not caused by it: "
            f"dispatch Backport with commits={self.a[:12]} lines=0.191",
            out,
        )
        self.assertIn(": owed before this run, not caused by it; dispatch Backport", out)

    def test_untouched_within_grace_passes(self):
        # merged while this dispatch ran: its own push's rescan picks it
        self.assertEqual(self.main(old=False)[0], 0)

    def test_named_within_grace_still_fails(self):
        other = [(self.a, "#7", "rc", "release/0.190", "picked", "-")]
        self.assertEqual(self.main(rows=other, old=False)[0], 1)

    def test_settled_passes(self):
        picked = [(self.a, "#7", "rc", "release/0.191", "picked", "-")]
        self.assertEqual(self.main(rows=picked)[0], 0)
        self.assertEqual(self.main(heads=["backport/0.191/aaaaaaa"])[0], 0)
        self.assertEqual(self.main(owed={})[0], 0)

    def test_unchecked_fails(self):
        code, out = self.main(owed=RuntimeError("git fetch (exit 128)"))
        self.assertEqual(code, 1)
        self.assertIn("::error::cannot check what this run left undone: git fetch", out)
        self.assertIn("- unchecked: see the run log", out)


class StateCheck(unittest.TestCase):
    NOW = rm.ts("2026-10-10T12:00:00Z")
    a, b, c, d = "a" * 40, "b" * 40, "c" * 40, "d" * 40
    STATE = {
        "branches": [
            {"branch": "release/0.192", "state": "pre-ga"},
            {"branch": "release/0.191", "state": "stabilizing"},
            {"branch": "release/0.190", "state": "stabilized"},
        ]
    }

    def pr(self, n, base, head, created):
        return {
            "number": n,
            "url": f"https://github.com/Zipstack/unstract-cloud/pull/{n}",
            "baseRefName": base,
            "headRefName": head,
            "createdAt": created,
        }

    def check(self, owed=(), held=(), prs=(), oss_prs=(), merged="2026-10-10T09:00:00Z"):
        self.scanned = []

        def held_(slug, repo, branch, accept, cache):
            self.scanned.append((branch, accept))
            return list(owed if accept is bp.OWED else held)

        listing = {
            "Zipstack/unstract-cloud": list(prs),
            "Zipstack/unstract": list(oss_prs),
        }
        with (
            mock.patch.object(bp, "conflict_prs", lambda slug: listing[slug]),
            mock.patch.object(bp, "_rescan_classes", lambda slug, lines: {}),
            mock.patch.object(bp, "held", held_),
            mock.patch.object(bp.rm, "git", lambda *a: merged),
            mock.patch("sys.stdout", new_callable=io.StringIO) as out,
        ):
            code = bp.state_check(
                self.STATE, ["Zipstack/unstract"], "Zipstack/unstract-cloud", self.NOW
            )
        return code, out.getvalue()

    def test_scans_stabilizing_owed_and_stabilized_held(self):
        self.assertEqual(self.check(), (0, ""))
        self.assertEqual(
            self.scanned, [("release/0.191", bp.OWED), ("release/0.190", bp.HELD)]
        )

    def test_owed_pick_at_the_grace_boundary(self):
        owed = [(self.a, "rc", "#7", "UN-1 [FIX] x")]
        self.assertEqual(self.check(owed, merged="2026-10-10T10:00:00Z"), (0, ""))
        code, out = self.check(owed, merged="2026-10-10T09:59:59Z")
        self.assertEqual(code, 1)
        self.assertEqual(
            out,
            "::error::aaaaaaa (rc, PR #7) owed on stabilizing release/0.191 and not picked: "
            f"dispatch Backport with commits={self.a[:12]}, or record a decline\n",
        )

    def test_owed_on_an_open_conflict_pr_waits_for_the_pr(self):
        owed = [(self.a, "rc", "#7", "UN-1 [FIX] x")]
        pr = self.pr(
            12, "release/0.191", "backport/0.191/aaaaaaa", "2026-10-10T00:00:00Z"
        )
        self.assertEqual(
            self.check(owed, prs=[pr], merged="2026-10-01T00:00:00Z"), (0, "")
        )
        oss = self.pr(
            30, "release/0.191", "backport/0.191/aaaaaaa", "2026-10-10T00:00:00Z"
        )
        self.assertEqual(
            self.check(owed, oss_prs=[oss], merged="2026-10-01T00:00:00Z")[0], 1
        )  # a head in the other repo is not this commit's pick

    def test_conflict_pr_at_the_grace_boundary_in_either_repo(self):
        at = self.pr(
            12, "release/0.191", "backport/0.191/ccccccc", "2026-10-09T12:00:00Z"
        )
        self.assertEqual(self.check(prs=[at], oss_prs=[{**at, "number": 30}]), (0, ""))
        past = {**at, "createdAt": "2026-10-09T11:59:59Z"}
        for prs, oss_prs, ref in (
            ([past], [], "Zipstack/unstract-cloud#12"),
            ([], [{**past, "number": 30}], "Zipstack/unstract#30"),
        ):
            code, out = self.check(prs=prs, oss_prs=oss_prs)
            self.assertEqual(code, 1)
            self.assertEqual(
                out,
                f"::error::{ref} on release/0.191: backport conflict PR open since 2026-10-09T11:59:59Z; "
                "resolve and merge it, or close it to decline\n",
            )

    def test_same_repo_listed_once(self):
        past = self.pr(
            12, "release/0.191", "backport/0.191/ccccccc", "2026-10-01T00:00:00Z"
        )
        with (
            mock.patch.object(bp, "conflict_prs", lambda slug: [past]) as _,
            mock.patch.object(bp, "_rescan_classes", lambda slug, lines: {}),
            mock.patch.object(bp, "held", lambda *a, **k: []),
            mock.patch("sys.stdout", new_callable=io.StringIO) as out,
        ):
            bp.state_check(self.STATE, ["o/r"], "o/r", self.NOW)
        self.assertEqual(out.getvalue().count("::error::"), 1)

    def test_unclassifiable_fails_on_any_line(self):
        u = [(self.b, bp.UNCLASSIFIABLE, "no PR", "y")]
        for owed, held, line in ((u, (), "release/0.191"), ((), u, "release/0.190")):
            code, out = self.check(owed, held, merged="2026-10-10T11:59:00Z")
            self.assertEqual(code, 1)
            self.assertEqual(
                out,
                f"::error::bbbbbbb (no PR, y) cannot be classed for {line}: "
                "fix its PR title or labels, or record a decline\n",
            )

    def test_held_is_listed_not_failed(self):
        held = [(self.d, "ga", "#9", "UN-3 [FIX] w")]
        code, out = self.check(held=held, merged="2026-10-01T00:00:00Z")
        self.assertEqual(code, 0)
        self.assertEqual(
            out,
            "::notice::ddddddd (ga, PR #9) held for release/0.190: stabilized, needs patch_released_lines\n",
        )


@unittest.skipUnless(
    os.path.exists(
        os.path.join(
            os.path.dirname(os.path.abspath(__file__)), "..", "workflows", "retire.yaml"
        )
    ),
    "the cloud repo's workflows",
)
class FailureAlert(unittest.TestCase):
    """Every release workflow tells Slack when it fails; a called run reports through its caller."""

    WORKFLOWS = (
        "backport",
        "state",
        "cut",
        "take-rc-build",
        "promote",
        "publish",
        "retire",
    )
    SLACK = "uses: slackapi/slack-github-action@v3.0.1"

    def jobs(self, text):
        """{job: body}, in file order; text-based, since CI has no PyYAML."""
        parts = re.split(r"^  ([\w-]+):\n", text.split("\njobs:\n", 1)[1], flags=re.M)
        return dict(zip(parts[1::2], parts[2::2], strict=True))

    def test_every_workflow_alerts(self):
        here = os.path.dirname(os.path.abspath(__file__))
        for name in self.WORKFLOWS:
            with open(os.path.join(here, "..", "workflows", f"{name}.yaml")) as f:
                text = f.read()
            title = re.search(r"^name: (.+)$", text, re.M)[1]
            with self.subTest(name):
                self.assertNotRegex(text, r"(echo|cat|printf)[^\n]*SLACK_WEBHOOK_URL")
                jobs = self.jobs(text)
                alerting = [j for j, body in jobs.items() if self.SLACK in body]
                if alerting != list(jobs)[-1:]:  # no alert job: each job alerts itself
                    self.assertEqual(alerting, list(jobs))
                for j in alerting:
                    body = jobs[j]
                    step = body.rsplit("      - name:", 1)[1]
                    self.assertIn(self.SLACK, step)  # the job's last step
                    self.assertIn("continue-on-error: true", step)
                    self.assertIn("webhook-type: incoming-webhook", step)
                    self.assertIn(
                        "SLACK_WEBHOOK_URL: ${{ secrets.SLACK_WEBHOOK_URL }}", step
                    )
                    self.assertIn(
                        "format('❌ {0} failed on {1}', github.workflow, github.ref_name)",
                        step,
                    )
                    for fmt in re.findall(r"format\('❌[^']*'", step):
                        self.assertTrue(
                            fmt.startswith("format('❌ {0} failed on {1}"), fmt
                        )
                    cond = re.search(r"^    if: (.+)$", body, re.M)
                    if cond and cond[1].startswith(
                        "failure()"
                    ):  # an alert job: last, after every other job
                        self.assertEqual(j, list(jobs)[-1])
                        needs = re.search(r"^    needs: \[(.+)\]$", body, re.M)[1]
                        self.assertEqual(needs.split(", "), list(jobs)[:-1])
                        guard = cond[1].removeprefix("failure()")
                        self.assertIn(guard, ("", f" && github.workflow == '{title}'"))
                        self.assertEqual(guard != "", "workflow_call:" in text)
                    else:
                        self.assertIn("        if: failure()\n", step)


class WorkflowSteps(unittest.TestCase):
    def read(self, name):
        here = os.path.dirname(os.path.abspath(__file__))
        with open(os.path.join(here, "..", "workflows", name)) as f:
            return f.read()

    def test_state_runs_daily_and_fails_through_the_check(self):
        text = self.read("state.yaml")
        on = text.split("\non:\n", 1)[1].split("\n\n", 1)[0]
        self.assertIn('  schedule:\n    - cron: "30 3 * * *"\n', on)
        self.assertIn("  workflow_dispatch:", on)
        check = text.split("- name: Check picks and conflict PRs", 1)[1].split("\n\n", 1)[
            0
        ]
        self.assertIn("sys.exit(backport.state_check(", check)
        self.assertIn("[oss.OSS]", check)
        self.assertNotIn("if:", check)
        self.assertNotIn(
            "Alert Slack", text.split("state_check", 1)[0]
        )  # the alert sees its failure

    @unittest.skipUnless(
        os.path.exists(
            os.path.join(
                os.path.dirname(os.path.abspath(__file__)),
                "..",
                "workflows",
                "retire.yaml",
            )
        ),
        "the cloud repo's workflows",
    )
    def test_first_error_line(self):
        text = self.read("backport.yaml")
        pick = text.split("- name: Pick", 1)[1].split("\n\n", 1)[0]
        self.assertIn("set -o pipefail", pick)
        self.assertIn('| tee "$RUNNER_TEMP/pick.log"', pick)
        step = text.split("- name: First error", 1)[1].split("\n\n", 1)[0]
        run = re.search(r"^        run: (.+)$", step, re.M)[1]
        with tempfile.TemporaryDirectory() as d:
            out = os.path.join(d, "out")
            env = {**os.environ, "RUNNER_TEMP": d, "GITHUB_OUTPUT": out}
            for log, want in (
                (
                    "rescan: 3 PRs listed\n::warning::x\n::error::aaaaaaa <@U1> "
                    + "y" * 400
                    + "\n::error::second\n",
                    "line=aaaaaaa @U1 "
                    + "y" * 287
                    + "\n",  # 301 characters cut, then <> dropped
                ),
                ("rescan: 3 PRs listed\n", "line=\n"),
            ):
                with open(os.path.join(d, "pick.log"), "w") as f:
                    f.write(log)
                open(out, "w").close()
                subprocess.run(["bash", "-e", "-c", run], env=env, check=True)
                with open(out) as f:
                    self.assertEqual(f.read(), want)


if __name__ == "__main__":
    unittest.main()
