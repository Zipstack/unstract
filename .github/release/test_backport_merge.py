"""Pure-logic checks for backport_merge (decline reason, landed, merge, close-is-decline, re-runs, reopen, squash retry), with gh
and git injected. Run: python test_backport_merge.py
"""

import json
import os
import subprocess
import tempfile
import unittest
from unittest import mock

import backport_merge as bm

O = "c" * 40  # the main original
CLOSED = "2026-10-12T10:00:00Z"
ME = "closer"
BOT = "release-bot"


def comment(body, at=CLOSED, user=ME):
    return {"created_at": at, "body": body, "user": user}


class Reason(unittest.TestCase):
    def test_closers_newest_comment_in_window(self):
        cs = [
            comment("Declined: older", "2026-10-12T09:59:00Z"),
            comment("Declined: not relevant on 0.185\nmore text", "2026-10-12T09:59:30Z"),
            comment("someone else's", "2026-10-12T09:59:50Z", user="other"),
        ]
        self.assertEqual(bm.decline_reason(cs, ME, CLOSED), "not relevant on 0.185")

    def test_prefix_optional(self):
        self.assertEqual(
            bm.decline_reason([comment("superseded by #12")], ME, CLOSED),
            "superseded by #12",
        )

    def test_none(self):
        self.assertIsNone(bm.decline_reason([], ME, CLOSED))
        self.assertIsNone(bm.decline_reason([comment("Declined:   ")], ME, CLOSED))
        self.assertIsNone(
            bm.decline_reason(
                [comment("Declined: old", "2026-10-12T09:57:59Z")], ME, CLOSED
            )
        )
        self.assertIsNone(
            bm.decline_reason(
                [comment("Declined: later", "2026-10-12T10:00:01Z")], ME, CLOSED
            )
        )
        self.assertIsNone(
            bm.decline_reason([comment("Declined: theirs", user="other")], ME, CLOSED)
        )


class Landed(unittest.TestCase):
    def test_landed(self):
        commits = [
            ("1" * 40, "fix: other\n\n(cherry picked from commit " + "d" * 40 + ")"),
            (
                "2" * 40,
                "fix: x\n\n(cherry picked from commit " + O + ")\n\nDeclined: n/a",
            ),
        ]
        self.assertEqual(bm.landed([O], commits), "2" * 40)
        self.assertIsNone(bm.landed([O], commits[:1]))
        self.assertIsNone(bm.landed([O], []))


class Gh:
    """Stand-in for bm.gh: records each call; serves the PR view, its comments and the decline commit's sha."""

    def __init__(self, state, labels=(), comments=()):
        self.pr = {
            "number": 7,
            "state": state,
            "closedAt": CLOSED,
            "baseRefName": "release/0.187",
            "headRefName": "backport/0.187/ccccccc",
            "headRefOid": "a" * 40,
            "labels": [{"name": n} for n in labels],
            "isCrossRepository": False,
            "author": {"login": BOT},
        }
        self.comments, self.calls = list(comments), []

    def __call__(self, *args, token=None):
        self.calls.append(args)
        if args[:2] == ("pr", "view"):
            return json.dumps(self.pr)
        if args[:2] == ("api", "user"):
            return BOT
        if args[:2] == ("api", "--paginate"):
            return "\n".join(json.dumps(c) for c in self.comments)
        if args[:4] == ("api", "-X", "POST", "repos/o/r/git/commits"):
            return json.dumps({"sha": "e" * 40})
        return ""

    def writes(self):
        """Every call after the reads, as (verb, path-or-subcommand)."""
        return [
            a[:2] if a[0] == "pr" else a[1:4]
            for a in self.calls
            if a[:2] not in (("pr", "view"), ("api", "--paginate"), ("api", "user"))
        ]

    def said(self):
        return [a[-1] for a in self.calls if a[:2] == ("pr", "comment")]


RECORDED = (
    "Recorded as a decline on release/0.187 ({}). To undo: reopen this PR and merge it."
)
LABELS = "repos/o/r/issues/7/labels"


class Close(unittest.TestCase):
    def setUp(self):
        saved = {
            k: getattr(bm, k) for k in ("gh", "first_pick", "base_picks", "base_tip")
        }
        self.addCleanup(lambda: [setattr(bm, k, v) for k, v in saved.items()])
        self.on_base = []  # (sha, message) already on the base, newest first
        self.originals = [O]
        bm.first_pick = lambda pr: (
            f"fix: x (#9)\n\n(cherry picked from commit {O})",
            self.originals,
        )
        bm.base_picks = lambda base, originals: self.on_base
        bm.base_tip = lambda base: ("b" * 40, "t" * 40)

    def close(self, *a, **k):
        bm.gh = Gh(*a, **k)
        return bm.close("o/r", 7, ME)

    def test_merged(self):
        out = self.close("MERGED", labels=["backport-conflict", "backport-declined"])
        self.assertEqual(out, "merged")
        self.assertEqual(
            bm.gh.writes(),
            [
                ("-X", "DELETE", f"{LABELS}/backport-conflict"),
                ("-X", "DELETE", f"{LABELS}/backport-declined"),
                ("-X", "POST", LABELS),
                ("-X", "DELETE", "repos/o/r/git/refs/heads/backport/0.187/ccccccc"),
            ],
        )
        self.assertEqual(bm.gh.calls[4][-1], "labels[]=backport-merged")

    def test_close_with_comment_declines_and_keeps_head(self):
        out = self.close(
            "CLOSED",
            labels=["backport-conflict", "backport-merged"],
            comments=[comment("Declined: not on 0.187")],
        )
        self.assertEqual(out, "declined eeeeeee")
        post = next(
            a
            for a in bm.gh.calls
            if a[:4] == ("api", "-X", "POST", "repos/o/r/git/commits")
        )
        self.assertIn(
            f"message=fix: x (#9)\n\n(cherry picked from commit {O})\n\nDeclined: not on 0.187",
            post,
        )
        self.assertIn("parents[]=" + "b" * 40, post)
        self.assertEqual(
            bm.gh.writes(),
            [
                ("-X", "POST", "repos/o/r/git/commits"),
                ("-X", "PATCH", "repos/o/r/git/refs/heads/release/0.187"),
                ("-X", "DELETE", f"{LABELS}/backport-conflict"),
                ("-X", "DELETE", f"{LABELS}/backport-merged"),
                ("-X", "POST", LABELS),
                ("pr", "comment"),
            ],
        )  # no head delete: a reopen needs it
        self.assertEqual(bm.gh.said(), [RECORDED.format("eeeeeee")])

    def test_close_without_comment_default_reason(self):
        self.assertEqual(
            self.close("CLOSED", labels=["backport-conflict"]), "declined eeeeeee"
        )
        post = next(
            a
            for a in bm.gh.calls
            if a[:4] == ("api", "-X", "POST", "repos/o/r/git/commits")
        )
        self.assertIn(
            f"message=fix: x (#9)\n\n(cherry picked from commit {O})\n\n"
            f"Declined: Closed by @{ME} without a reason (PR #7)",
            post,
        )

    def test_rerun_writes_nothing(self):
        self.on_base = [
            (
                "d" * 40,
                f"fix: x\n\n(cherry picked from commit {O})\n\nDeclined: not on 0.187",
            )
        ]
        out = self.close(
            "CLOSED",
            labels=["backport-declined"],
            comments=[
                comment("Declined: not on 0.187"),
                comment(RECORDED.format("ddddddd"), user="bot"),
            ],
        )
        self.assertEqual(out, "skipped: already on release/0.187 as ddddddd")
        self.assertEqual(bm.gh.writes(), [])

    def test_close_again_after_reopen(self):
        """Reopened (label backport-conflict), closed again: no second decline commit; label and comment fixed."""
        self.on_base = [
            ("d" * 40, f"fix: x\n\n(cherry picked from commit {O})\n\nDeclined: first")
        ]
        out = self.close(
            "CLOSED",
            labels=["backport-conflict"],
            comments=[
                comment(RECORDED.format("ddddddd"), "2026-10-12T09:00:00Z", user="bot")
            ],
        )
        self.assertEqual(out, "skipped: already on release/0.187 as ddddddd")
        self.assertEqual(
            bm.gh.writes(),
            [
                ("-X", "DELETE", f"{LABELS}/backport-conflict"),
                ("-X", "POST", LABELS),
                ("pr", "comment"),
            ],
        )
        self.assertEqual(bm.gh.said(), [RECORDED.format("ddddddd")])

    def test_lost_trailer_fails_loudly(self):
        self.originals = []
        with self.assertRaises(RuntimeError):
            self.close("CLOSED", labels=["backport-conflict"])
        self.assertEqual(bm.gh.writes(), [("pr", "comment")])
        self.assertTrue(bm.gh.said()[0].startswith("Bot could not record the decline"))

    def test_reopened_sets_conflict_only(self):
        self.assertEqual(self.close("OPEN", labels=["backport-declined"]), "reopened")
        self.assertEqual(
            bm.gh.writes(),
            [("-X", "DELETE", f"{LABELS}/backport-declined"), ("-X", "POST", LABELS)],
        )
        self.assertEqual(bm.gh.calls[-1][-1], "labels[]=backport-conflict")

    def test_not_a_backport_pr_refused(self):
        """A dispatch with a wrong number: no label, comment or commit."""
        for change in (
            {"headRefName": "feat/x"},
            {"baseRefName": "main"},
            {"isCrossRepository": True},
            {"headRefName": "backport/0.186/ccccccc"},
            {"headRefName": "backport/0.187/ccccccc-x"},
            {"headRefName": "backport/0.187/cccccc"},
            {"author": {"login": ME}},
        ):
            bm.gh = Gh("CLOSED", labels=["backport-conflict"])
            bm.gh.pr.update(change)
            with self.assertRaises(RuntimeError):
                bm.close("o/r", 7, ME)
            self.assertEqual(bm.gh.writes(), [])

    def test_head_already_gone(self):
        def gh(*args, token=None):
            if args[:3] == ("api", "-X", "DELETE") and "/git/refs/" in args[3]:
                raise RuntimeError(
                    "gh api -X (exit 1): Reference does not exist (HTTP 422)"
                )
            return fake(*args)

        fake = Gh("MERGED", labels=["backport-merged"])
        bm.gh = gh
        self.assertEqual(bm.close("o/r", 7, ME), "merged")


class FirstPick(unittest.TestCase):
    """The decline names only the main commit of the head's sha7, with main's message, never the head's text."""

    def test_pick_trailer(self):
        t = lambda o: f"(cherry picked from commit {o})"
        head = "backport/0.187/ccccccc"
        self.assertEqual(bm.rm.pick_trailer(head, f"fix: x\n\n{t(O)}"), O)
        self.assertIsNone(
            bm.rm.pick_trailer(head, f"fix: x\n\n{t(O)}\n{t('d' * 40)}")
        )  # a second fix named
        self.assertIsNone(
            bm.rm.pick_trailer(head, f"fix: x\n\n{t('d' * 40)}")
        )  # another fix than the head's
        self.assertIsNone(bm.rm.pick_trailer(head, "fix: x"))
        self.assertIsNone(bm.rm.pick_trailer("backport/0.187/ccc", f"fix: x\n\n{t(O)}"))

    def test_message_from_main(self):
        with tempfile.TemporaryDirectory() as d:
            g = lambda *a: subprocess.run(
                ["git", "-C", d, "-c", "user.name=t", "-c", "user.email=t@t", *a],
                capture_output=True,
                text=True,
                check=True,
            ).stdout.strip()
            g("init", "-q", "-b", "main")
            g("commit", "-q", "--allow-empty", "-m", "fix: real (#9)")
            o = g("rev-parse", "HEAD")
            g("update-ref", "refs/remotes/origin/main", o)
            cwd = os.getcwd()
            os.chdir(d)
            self.addCleanup(os.chdir, cwd)
            pr = {"headRefName": f"backport/0.187/{o[:7]}"}
            edited = f"fix: edited by hand\n\n(cherry picked from commit {o[:12]})"
            with mock.patch.object(bm, "head_messages", lambda pr: [edited]):
                self.assertEqual(
                    bm.first_pick(pr),
                    (f"fix: real (#9)\n\n(cherry picked from commit {o})", [o]),
                )
            with mock.patch.object(
                bm,
                "head_messages",
                lambda pr: ["fix: x\n\n(cherry picked from commit " + "d" * 40 + ")"],
            ):
                self.assertEqual(
                    bm.first_pick({"headRefName": "backport/0.187/ddddddd"}), ("", [])
                )  # not on main


class Summary(unittest.TestCase):
    def test_blocks(self):
        rec = lambda result, sha="6" * 40, reason=None: {
            "result": result,
            "base": "release/0.189",
            "sha": sha,
            "reason": reason,
        }
        with mock.patch.dict(os.environ, clear=True):
            self.assertEqual(
                bm.summary(246, ME, rec("declined 6666666", reason="not on 0.189")),
                [
                    "**Backport PR** #246 on `release/0.189`: **declined** as `6666666`",
                    f'Reason: "not on 0.189" (@{ME})',
                    "Undo: reopen #246 and merge it.",
                ],
            )
            self.assertEqual(
                bm.summary(246, ME, rec("merged")),
                [
                    f"**Backport PR** #246 on `release/0.189`: **merged** as `6666666` (@{ME})",
                    "Undo: revert `6666666` on `release/0.189`.",
                ],
            )
            self.assertEqual(
                bm.summary(246, ME, rec("skipped: already on release/0.189 as 6666666")),
                [
                    "**Backport PR** #246 on `release/0.189`: **skipped**: already on `release/0.189` as `6666666`"
                ],
            )
            self.assertEqual(len(bm.summary(246, ME, rec("reopened", sha=None))), 2)


class SquashRetry(unittest.TestCase):
    PR = {"number": 4, "headRefOid": "a" * 40}
    MOVED = RuntimeError(
        "gh api -X (exit 1): gh: Base branch was modified. Review and try the merge again. (HTTP 405)"
    )

    def run_squash(self, answers):
        calls, waits = [], []

        def gh(*args, **kw):
            calls.append(args)
            a = answers.pop(0)
            if isinstance(a, Exception):
                raise a

        with mock.patch.object(bm, "gh", gh):
            return (
                bm.squash("o/r", self.PR, "t\n\nb", sleep=waits.append),
                len(calls),
                waits,
            )

    def test_base_modified_is_retried(self):
        self.assertEqual(self.run_squash([self.MOVED, None]), (True, 2, [5]))

    def test_base_modified_three_times_raises(self):
        with self.assertRaisesRegex(RuntimeError, "Base branch was modified"):
            self.run_squash([self.MOVED] * 3)

    def test_pending_check_is_not_retried(self):
        self.assertEqual(
            self.run_squash([RuntimeError("Required status check is expected")]),
            (False, 1, []),
        )

    def test_other_error_is_not_retried(self):
        with self.assertRaisesRegex(RuntimeError, "HTTP 409"):
            self.run_squash([RuntimeError("Head branch was modified (HTTP 409)"), None])


if __name__ == "__main__":
    unittest.main()
