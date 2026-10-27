"""backport helpers: held_filter and the held summary line; PR body of a pick PR; picks in main order; branches filter; accept= and UNCLASSIFIABLE; owed-picks summary; dispatch route for a non-fix; push summary (status rows, latest tag, stale mark, quiet line); push rescan plan; PR listing classes; push retry; stuck clean pick PR; open conflict PRs per line; pick against real git (no untracked file in a conflict commit, a path with a space, a pick merged after the fetch). Run: python test_backport.py"""

import io
import json
import os
import subprocess
import tempfile
import unittest
from unittest import mock

os.environ["GITHUB_REPOSITORY"] = (
    "Zipstack/unstract-cloud"  # relstate loads the cloud config, whatever the runner sets
)
os.environ["RELEASE_BOT_APP_SLUG"] = "zipstack-push-to-main"  # the release App
BOT = {
    "login": "app/zipstack-push-to-main",
    "is_bot": True,
}  # gh pr view's author of the App's PRs
import backport as bp
import relmgr as rm


class Held(unittest.TestCase):
    def test_held_filter(self):
        a, b, c, d, e = (ch * 40 for ch in "abcde")
        classes = {
            a: ("security", "#1"),
            b: ("critical", "#2"),
            c: ("fix", "#3"),
            d: (None, "no PR"),
            e: ("security", "#5"),
        }
        # a picked (abbreviated trailer), e declined (same trailer): only b is held; fix and non-fix never are.
        self.assertEqual(
            bp.held_filter([a, b, c, d, e], classes, {a[:7], e}), [(b, "critical", "#2")]
        )
        # accept=OWED adds plain fixes; UNCLASSIFIABLE (no PR, bad title) is never dropped, held or owed.
        classes[d] = (bp.UNCLASSIFIABLE, "no PR")
        self.assertEqual(
            bp.held_filter([a, b, c, d, e], classes, {a[:7], e}),
            [(b, "critical", "#2"), (d, bp.UNCLASSIFIABLE, "no PR")],
        )
        self.assertEqual(
            bp.held_filter([a, b, c, d, e], classes, {a[:7], e}, accept=bp.OWED),
            [(b, "critical", "#2"), (c, "fix", "#3"), (d, bp.UNCLASSIFIABLE, "no PR")],
        )
        rows = [
            (a, "release/0.189", "security", "#1"),
            (a, "release/0.182", "security", "#1"),
            (b, "release/0.182", "critical", "#2"),
        ]
        self.assertEqual(
            bp.held_warnings(rows),
            [
                "::warning::release/0.189: 1 held security/critical fix, Backport with confirm_stabilized",
                "::warning::release/0.182: 2 held security/critical fixes, Backport with confirm_stabilized",
            ],
        )
        self.assertEqual(
            bp.held_line(b, "critical", "#2", "release/0.182"),
            "::warning::bbbbbbb (critical, PR #2) held for release/0.182: stabilized, needs confirm_stabilized",
        )

        self.assertIsNone(bp.held_note([], "release/0.182"))
        with mock.patch.dict(
            os.environ, {"GITHUB_SERVER_URL": "", "GITHUB_REPOSITORY": ""}
        ):
            self.assertEqual(
                bp.held_note(
                    [(b, "critical", "#2", "t"), (d, bp.UNCLASSIFIABLE, "no PR", "t")],
                    "release/0.182",
                ),
                f"⚠ Held for the RM on `release/0.182` (stabilized; Promote blocks unless forced): #2 critical, no PR "
                f"{bp.UNCLASSIFIABLE}. Pick with `gh workflow run backport.yaml -f commits=#2,{d[:12]} "
                "-f branches=release/0.182 -f confirm_stabilized=true`",
            )


class Rescan(unittest.TestCase):
    """Push mode over held_filter output for nested ranges: 0.190 (stabilizing, cut after a) inside 0.187."""

    def test_plan(self):
        a, b, c, d, e, u = (ch * 40 for ch in "abcdeu")
        classes = {
            a: ("fix", "#1", "A"),
            b: ("fix", "#2", "B"),
            c: ("security", "#3", "C"),
            d: ("fix", "#4", "D"),
            e: ("fix", "#5", "E"),
            u: (bp.UNCLASSIFIABLE, "no PR", "U"),
        }
        targets = {
            "fix": ["release/0.190"],
            "security_critical": [
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
        # (1) d is missing on 0.190 only: planned there; b, already picked on 0.190, is not.
        # (2) declined e is planned nowhere. (3) main order (c before d). (4) security c on stabilized 0.187 waits.
        self.assertEqual(
            plan,
            [
                ("release/0.190", c, "security", "#3", "C"),
                ("release/0.190", d, "fix", "#4", "D"),
            ],
        )
        self.assertEqual(awaiting, [(c, "release/0.187", "security", "#3")])
        self.assertEqual(
            unclassifiable,
            [(u, "release/0.190", "no PR", "U"), (u, "release/0.187", "no PR", "U")],
        )
        plan, awaiting, _ = bp.rescan_plan(targets, held, confirm=True)
        self.assertEqual(
            (plan[-1], awaiting), (("release/0.187", c, "security", "#3", "C"), [])
        )

    def test_branches_narrow(self):
        targets = {
            "fix": ["release/0.190"],
            "security_critical": [
                {"branch": "release/0.187", "needs_rm_confirmation": True}
            ],
        }
        self.assertEqual(
            bp.rescan_targets(targets, ["release/0.187", "release/0.1"]),
            ({"release/0.187": bp.HELD}, ["release/0.1"]),
        )


class Listing(unittest.TestCase):
    def test_classes_and_fallback(self):
        with tempfile.TemporaryDirectory() as repo:
            git = lambda *a: rm.git(
                repo, "-c", "user.name=Dev", "-c", "user.email=dev@example.com", *a
            )
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
                pr(1, fix, "UN-1 [FIX] a"),
                pr(2, sec, "UN-2 [FIX] b", ["fix/security"]),
                pr(3, misc, "UN-3 [MISC] c"),
                pr(4, bad, "no prefix"),
                {"number": 5, "title": "open", "labels": [], "mergeCommit": None},
            ]
            classes = bp.classes_from_listing(listing)
            self.assertEqual(classes[fix], ("fix", "#1", "UN-1 [FIX] a"))
            self.assertEqual(classes[sec], ("security", "#2", "UN-2 [FIX] b"))
            self.assertEqual(classes[misc], (None, "#3", "UN-3 [MISC] c"))
            self.assertEqual(classes[bad][0], bp.UNCLASSIFIABLE)
            self.assertIn(
                "no recognised '[TYPE]' or 'TICKET [TYPE]' prefix", classes[bad][1]
            )
            self.assertEqual(
                len(classes), 4
            )  # an unmerged row (no merge commit) is skipped
            looked = []
            saved = bp.fix_class
            bp.fix_class = lambda slug, sha, token=None: looked.append(sha) or (
                None,
                "no PR",
                None,
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
                    (fix, "fix"),
                    (sec, "security"),
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
            with mock.patch.object(bp.rm, "is_converged", lambda *a, **k: False):
                out = bp.push_head("o/r", sha, branch, head, "#7", sleep=sleeps.append)
            comment = calls[-1]
            calls.clear(), sleeps.clear()
            bp.run = fake(
                [1, 1, 1]
            )  # rejected because another run landed the pick: no failure, no comment
            with mock.patch.object(bp.rm, "is_converged", lambda *a, **k: True):
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


ORIG = "77212a38cc07a0e7fc5f31c691275666976c4c82"


class Body(unittest.TestCase):
    def test_conflict_body_has_no_stale_rule(self):
        body = bp.pr_body(
            ORIG, "#57", "release/0.185", "backport/0.185/77212a3", ["NOTES.md"]
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
            bp.pr_body(ORIG, "#57", "release/0.185", "backport/0.185/77212a3"),
        )


class MainOrder(unittest.TestCase):
    def test_newest_first_comes_back_oldest_first(self):
        with tempfile.TemporaryDirectory() as repo:
            rm.git(repo, "init", "-q", "-b", "main")
            shas = []
            for i, date in enumerate(("2026-01-01T00:00:00Z", "2026-01-02T00:00:00Z")):
                os.environ["GIT_COMMITTER_DATE"] = date
                try:
                    rm.git(
                        repo,
                        "-c",
                        "user.name=Dev",
                        "-c",
                        "user.email=dev@example.com",
                        "commit",
                        "-q",
                        "--allow-empty",
                        "-m",
                        f"fix {i}",
                    )
                finally:
                    del os.environ["GIT_COMMITTER_DATE"]
                shas.append(rm.git(repo, "rev-parse", "HEAD"))
            self.assertEqual(bp.main_order(repo, [shas[1], shas[0], shas[1]]), shas)


class OwedSummary(unittest.TestCase):
    def test_table_and_backport_line(self):
        a, b = "a" * 40, "b" * 40
        out = bp.owed_summary(
            [(a, "fix", "#3", "UN-1 [FIX] x | y"), (b, bp.UNCLASSIFIABLE, "no PR", "z")],
            "release/0.187",
        )
        self.assertIn("| `aaaaaaa` | #3 | UN-1 [FIX] x \\| y | fix |", out)
        self.assertIn(f"| `bbbbbbb` | no PR | z | {bp.UNCLASSIFIABLE} |", out)
        self.assertTrue(
            out.endswith(f"Backport commits: {a}")
        )  # UNCLASSIFIABLE stays out of the paste line
        self.assertTrue(bp.owed_summary([], "release/0.187").endswith("none"))


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
            mock.patch.object(bp, "resolve", lambda slug, c: c),
            mock.patch.object(bp, "main_order", lambda repo, shas: shas),
            mock.patch.object(bp, "fix_class", lambda slug, sha: classes[sha]),
        ):
            rows, awaiting = bp.dispatch(
                "o/r",
                {"fix": ["release/0.191"], "security_critical": []},
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
                    "skipped: not a fix; label #250 fix/needs-backport (or the fix label it needs) and rerun",
                    "-",
                ),
                (b, "no PR", "none", "-", "skipped: not a fix", "-"),
            ],
        )
        self.assertEqual(awaiting, [])


class DispatchHold(unittest.TestCase):
    def test_security_waits_for_rm_on_a_stabilized_line(self):
        sec, fix = "s" * 40, "f" * 40
        classes = {
            sec: ("security", "#3", "UN-3 [FIX] x"),
            fix: ("fix", "#4", "UN-4 [FIX] y"),
        }
        targets = {
            "fix": ["release/0.191"],
            "security_critical": [
                {"branch": "release/0.191", "needs_rm_confirmation": False},
                {"branch": "release/0.190", "needs_rm_confirmation": True},
            ],
        }
        with (
            mock.patch.object(bp, "resolve", lambda slug, c: c),
            mock.patch.object(bp, "main_order", lambda repo, shas: shas),
            mock.patch.object(bp, "fix_class", lambda slug, sha: classes[sha]),
            mock.patch.object(bp, "pick_row", lambda slug, sha, b, *a: (sha, b)),
        ):
            run = lambda confirm: bp.dispatch("o/r", targets, f"{sec} {fix}", confirm, [])
            self.assertEqual(
                run(False),
                (
                    [(sec, "release/0.191"), (fix, "release/0.191")],
                    [(sec, "release/0.190", "security", "#3")],
                ),
            )
            self.assertEqual(
                run(True),
                (
                    [
                        (sec, "release/0.191"),
                        (sec, "release/0.190"),
                        (fix, "release/0.191"),
                    ],
                    [],
                ),
            )


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
            "| `release/0.192` | stabilizing | `v0.192.0-rc.2` · all built | 0 | 1 conflict, 4 RM | resolve #243 |".replace(
                "all built", "+1 not built"
            ),
        )
        self.assertTrue(
            row(held_n=4, unbuilt=1).endswith("| 4 RM | RM: confirm 4 security fixes |")
        )
        self.assertTrue(
            row(held_n=1, unbuilt=1).endswith("| 1 RM | RM: confirm 1 security fix |")
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
            commit = lambda m: rm.git(
                repo,
                "-c",
                "user.name=Dev",
                "-c",
                "user.email=dev@example.com",
                "commit",
                "-q",
                "--allow-empty",
                "-m",
                m,
            )
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
            (a, "#251", "fix", "release/0.192", "merged 1234567 (#260)", "-"),
            (
                a,
                "#251",
                "fix",
                "release/0.190",
                "pr https://github.com/o/r/pull/261",
                "-",
            ),
            (a, "#251", "fix", "release/0.189", "skipped: already on branch", "-"),
            (a, "#251", "fix", "release/0.188", "merged 89abcde (#262, retried)", "-"),
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
                (a, "release/0.190", "security", "#247", 2),
                (a, "release/0.189", "security", "#247", 2),
            ],
        )
        self.assertEqual(out[0], "<details><summary>Pending (2)</summary>")
        self.assertIn("- #261 on `release/0.190` · open 6 days ⚠", out)
        self.assertIn(
            "- #247 security → `release/0.190`, `release/0.189` · merged 2 days ago", out
        )
        self.assertIn(
            "gh workflow run backport.yaml -f commits=#247 -f branches=release/0.190,release/0.189 "
            "-f confirm_stabilized=true",
            out,
        )
        self.assertEqual(bp.pending_block([], []), [])


class ConflictPRs(unittest.TestCase):
    """Open backport-conflict PRs of one repo, per line, read by a stub gh as the given token; a failed listing raises."""

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
    """A pick head left by an earlier run: an unlabelled one-commit PR is merged now, anything else waits."""

    def setUp(self):
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
                bp, "gh", lambda *a: json.dumps(listing if prs is None else prs)
            ),
            mock.patch.object(bp.bm, "squash", squash),
            mock.patch.object(bp, "soft", lambda *a: None),
        ):
            return bp.finish_open("o/r", "release/1.0", "backport/1.0/aaaaaaa")

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
        row = ("a" * 40, "#1", "fix", "release/1.0", " ".join(out), "-")
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
                "backport/1.0/aaaaaaa (this closes #4) and the next run re-picks the fix",
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
        with mock.patch.object(bp, "PICK_TIMEOUT", 0):
            out = self.finish(prs=[])
        self.assertEqual(
            out,
            (
                "failed",
                "head backport/1.0/aaaaaaa exists with no open PR: delete it "
                "or reopen its PR, then rerun",
            ),
        )

    def test_not_the_bots_pick_is_not_squashed(self):
        # The squash bypasses the release ruleset: a person's PR on a pick head, or a commit that is not the pick
        # of the head's sha7, must not land through it.
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
        # A person's PR with two commits fails too, rather than waiting silently as a conflict PR.
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
    """pick() against a local origin: an empty pick names its fix and the decline; fix/* labels reach the pick PR."""

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
        (
            g("add", "a.txt"),
            g("commit", "-q", "-m", "base"),
            g("push", "-q", "origin", "HEAD:main", "HEAD:release/1.0"),
        )
        self.write(d + "/w/a.txt", "y\n")
        g("commit", "-q", "-am", "fix: y (#5)"), g("push", "-q", "origin", "HEAD:main")
        self.fix = g("rev-parse", "HEAD")
        g("fetch", "-q", "origin")
        self.d, cwd = d, os.getcwd()
        os.chdir(d + "/w")
        self.addCleanup(os.chdir, cwd)
        self.calls = []

    @staticmethod
    def write(path, text):
        with open(path, "w") as f:
            f.write(text)

    def gh(self, *a, token=None):
        self.calls.append(a)
        if a[:2] == ("api", "repos/o/r/pulls/5"):
            return "fix/security\nfix/needs-backport\nother"
        return "https://github.com/o/r/pull/8"

    def pick(self):
        with (
            mock.patch.object(bp, "gh", self.gh),
            mock.patch.object(bp.bm, "squash", lambda *a: True),
            mock.patch.object(bp, "soft", lambda *a: None),
        ):
            return bp.pick("o/r", self.fix, "release/1.0", "UN-1 [FIX] y", "#5")

    def test_clean_pick_carries_fix_labels(self):
        self.assertEqual(self.pick()[0], "merged")
        create = next(a for a in self.calls if a[:2] == ("pr", "create"))
        self.assertEqual(
            [create[i + 1] for i, x in enumerate(create) if x == "--label"],
            ["fix/security", "fix/needs-backport"],
        )

    def test_conflict_pick_carries_fix_labels(self):
        self.g("checkout", "-q", "-B", "rel", "origin/release/1.0")
        self.write(self.d + "/w/a.txt", "z\n")
        (
            self.g("commit", "-q", "-am", "z"),
            self.g("push", "-q", "origin", "HEAD:release/1.0"),
            self.g("fetch", "-q", "origin"),
        )
        self.assertEqual(self.pick()[0], "pr")
        create = next(a for a in self.calls if a[:2] == ("pr", "create"))
        self.assertEqual(
            [create[i + 1] for i, x in enumerate(create) if x == "--label"],
            ["backport-conflict", "fix/security", "fix/needs-backport"],
        )

    def test_empty_pick_names_the_decline(self):
        self.g("checkout", "-q", "-B", "rel", "origin/release/1.0")
        self.write(self.d + "/w/a.txt", "y\n")
        self.write(self.d + "/w/b.txt", "b\n")
        self.g("add", "."), self.g("commit", "-q", "-m", "y and b, by hand")
        (
            self.g("push", "-q", "origin", "HEAD:release/1.0"),
            self.g("fetch", "-q", "origin"),
        )
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


class PickRow(unittest.TestCase):
    def test_relevance_failure_never_fails_the_pick(self):
        with (
            mock.patch.object(
                bp.rm, "relevance", side_effect=RuntimeError("bad | path\nsecond line")
            ),
            mock.patch.object(bp, "pick", lambda *a: ("merged", "abc1234 (#8)")),
            mock.patch("sys.stdout", io.StringIO()),
        ):
            row = bp.pick_row("o/r", "c" * 40, "release/1.0", "fix", "#5", "t")
        self.assertEqual(row[4], "merged abc1234 (#8)")
        self.assertEqual(row[5], "unknown (RuntimeError: bad \\| path)")

    def test_failure_names_its_type(self):
        with (
            mock.patch.object(bp.rm, "relevance", lambda *a: "relevant"),
            mock.patch.object(bp, "pick", side_effect=KeyError("x")),
            mock.patch.object(bp, "run"),
            mock.patch("sys.stdout", io.StringIO()),
            mock.patch("sys.stderr", io.StringIO()) as err,
        ):
            row = bp.pick_row("o/r", "c" * 40, "release/1.0", "fix", "#5", "t")
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
                g("add", "-A"), g("commit", "-q", "-m", msg)
                return g("rev-parse", "HEAD")

            g("init", "-q", "-b", "main")
            commit("base", a="1\n2\n", b="1\n", c_d="1\n")
            g("branch", "release/1.0")
            main = commit("rewrite a:2 after the cut", a="1\nTWO\n", b="1\nnew\n")
            rel = lambda **files: g(
                "checkout", "-q", "-B", "fix", main
            ) or bp.rm.relevance(d, commit("fix", **files), "release/1.0")
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
    """pick() against real git: a conflict commit carries no untracked file, and a pick another run merged after
    this run fetched is skipped.
    """

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


if __name__ == "__main__":
    unittest.main()
