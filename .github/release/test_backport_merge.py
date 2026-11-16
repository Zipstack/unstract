import json
import os
import subprocess
import tempfile
import unittest
from unittest import mock

import backport_merge as bm


def setUpModule():
    """Jitter off: each wait is its upper bound, so the schedule is exact."""
    p = mock.patch.object(bm.random, "uniform", lambda lo, hi: hi)
    p.start()
    unittest.addModuleCleanup(p.stop)


O = "c" * 40  # the main original
CLOSED = "2026-10-12T10:00:00Z"
ME = "closer"
APP = "zipstack-push-to-main"  # the release App: gh pr view shows its PRs authored by app/<slug>, is_bot true
BOT = f"app/{APP}"
os.environ["RELEASE_BOT_APP_SLUG"] = APP


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

    def test_pick_trailer_dropped(
        self,
    ):  # it would mark that commit declined in the decline commit's message
        self.assertEqual(
            bm.decline_reason(
                [comment(f"Declined: dup of (cherry picked from commit {'a' * 40})")],
                ME,
                CLOSED,
            ),
            "dup of",
        )
        nested = f"(cherry picked from (cherry picked from commit {'b' * 40})commit {'a' * 40})"
        self.assertEqual(
            bm.decline_reason([comment(f"Declined: dup {nested}")], ME, CLOSED), "dup"
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
            "author": {"login": BOT, "is_bot": True},
        }
        self.comments, self.calls = list(comments), []
        self.head_ref = "a" * 40  # the head branch still at this PR's head
        self.patch_errors = []  # raised, in order, by the base ref updates

    def __call__(self, *args, token=None):
        self.calls.append(args)
        if args[:2] == ("pr", "view"):
            return json.dumps(self.pr)
        if args[:2] == ("api", "--paginate"):
            return "\n".join(json.dumps(c) for c in self.comments)
        if args[:2] == ("api", "repos/o/r/git/ref/heads/backport/0.187/ccccccc"):
            if isinstance(self.head_ref, Exception):
                raise self.head_ref
            if self.head_ref is None:
                raise RuntimeError(
                    "gh api repos/o/r/git/ref/heads/... (exit 1): gh: Not Found (HTTP 404)"
                )
            return self.head_ref
        if args[:4] == ("api", "-X", "POST", "repos/o/r/git/commits"):
            return json.dumps({"sha": "e" * 40})
        if args[:3] == ("api", "-X", "PATCH") and self.patch_errors:
            raise self.patch_errors.pop(0)
        return ""

    def writes(self):
        """Every call after the reads, as (verb, path-or-subcommand)."""
        return [
            a[:2] if a[0] == "pr" else a[1:4]
            for a in self.calls
            if a[:2] not in (("pr", "view"), ("api", "--paginate"), ("api", "user"))
            and "/git/ref/heads/" not in a[1]
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
            k: getattr(bm, k)
            for k in ("gh", "first_pick", "base_picks", "base_tip", "fetch_base")
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
        self.fetched = []
        bm.fetch_base = self.fetched.append

    def close(self, *a, patch_errors=(), **k):
        bm.gh = Gh(*a, **k)
        bm.gh.patch_errors = list(patch_errors)
        return bm.record("o/r", 7, ME)["result"]

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
        self.assertEqual(
            bm.gh.calls[3][-1], "labels[]=backport-merged"
        )  # after pr view and two deletes

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

    def test_moved_base_retries_on_its_new_tip(self):
        moved = RuntimeError(
            "gh api -X (exit 1): gh: Update is not a fast forward (HTTP 422)"
        )
        out = self.close("CLOSED", labels=["backport-conflict"], patch_errors=[moved])
        self.assertEqual(out, "declined eeeeeee")
        self.assertEqual(self.fetched, ["release/0.187"])
        self.assertEqual(
            bm.gh.writes()[:4],
            [
                ("-X", "POST", "repos/o/r/git/commits"),
                ("-X", "PATCH", "repos/o/r/git/refs/heads/release/0.187"),
                ("-X", "POST", "repos/o/r/git/commits"),
                ("-X", "PATCH", "repos/o/r/git/refs/heads/release/0.187"),
            ],
        )

    def test_decline_landing_meanwhile_is_not_written_twice(self):
        moved = RuntimeError("gh: Update is not a fast forward (HTTP 422)")
        bm.fetch_base = lambda base: self.on_base.append(
            (
                "d" * 40,
                f"fix: x\n\n(cherry picked from commit {O})\n\nDeclined: other run",
            )
        )
        out = self.close("CLOSED", labels=["backport-conflict"], patch_errors=[moved])
        self.assertEqual(out, "skipped: already on release/0.187 as ddddddd")
        self.assertEqual(
            [w for w in bm.gh.writes() if w[0] == "-X"][:3],
            [
                ("-X", "POST", "repos/o/r/git/commits"),
                ("-X", "PATCH", "repos/o/r/git/refs/heads/release/0.187"),
                ("-X", "DELETE", f"{LABELS}/backport-conflict"),
            ],
        )

    def test_other_ref_errors_are_not_retried(self):
        with self.assertRaises(RuntimeError):
            self.close(
                "CLOSED",
                labels=["backport-conflict"],
                patch_errors=[RuntimeError("gh: Server Error (HTTP 502)")],
            )
        self.assertEqual(self.fetched, [])

    def test_base_moving_every_time_gives_up(self):
        moved = RuntimeError("gh: Update is not a fast forward (HTTP 422)")
        with self.assertRaises(RuntimeError):
            self.close(
                "CLOSED",
                labels=["backport-conflict"],
                patch_errors=[moved] * bm.DECLINE_TRIES,
            )
        self.assertEqual(len(self.fetched), bm.DECLINE_TRIES - 1)

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

    def test_close_by_the_app_is_not_a_decline(self):
        bm.gh = Gh("CLOSED", labels=["backport-conflict"])
        with self.assertRaisesRegex(RuntimeError, "closed by the release App"):
            bm.record("o/r", 7, f"{APP}[bot]")
        self.assertEqual(bm.gh.writes(), [])

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

    def test_head_without_a_pick_declines_nothing(self):
        bm.first_pick = lambda pr: (None, [])
        self.assertEqual(
            self.close("CLOSED", labels=["backport-conflict"]), "skipped: no pick"
        )
        self.assertEqual(bm.gh.writes(), [("pr", "comment")])
        said = bm.gh.said()[0]
        self.assertTrue(
            said.startswith(bm.NO_PICK + " release/0.187, so nothing was declined")
        )
        self.assertIn("delete `backport/0.187/ccccccc` by hand", said)
        self.assertIn("do not delete the head yet", said)
        self.assertIn("Declined: <reason>", said)
        out = self.close("CLOSED", comments=[comment(said, user="bot")])  # a re-run
        self.assertEqual((out, bm.gh.writes()), ("skipped: no pick", []))
        # A comment from an earlier close does not count for this one.
        early = comment(said, at="2026-10-12T09:00:00Z", user="bot")
        self.close("CLOSED", comments=[early])
        self.assertEqual(bm.gh.writes(), [("pr", "comment")])
        # The head already deleted (that closed the PR), or holding a later run's pick: no delete advice.
        for ref in (None, "d" * 40):
            bm.gh = Gh("CLOSED")
            bm.gh.head_ref = ref
            self.assertEqual(
                bm.record("o/r", 7, ME)["result"], "skipped: no pick, head gone"
            )
            self.assertEqual(bm.gh.writes(), [("pr", "comment")])
            said = bm.gh.said()[0]
            self.assertIn("no longer holds this PR's head", said)
            self.assertNotIn("delete `", said)
        # A ref read that fails for another reason (auth, outage) is not read as "head gone".
        bm.gh = Gh("CLOSED")
        bm.gh.head_ref = RuntimeError(
            "gh api repos/o/r/git/ref/heads/... (exit 1): gh: Bad credentials (HTTP 401)"
        )
        with self.assertRaisesRegex(RuntimeError, "HTTP 401"):
            bm.record("o/r", 7, ME)["result"]
        self.assertEqual(bm.gh.writes(), [])

    def test_reopened_sets_conflict_only(self):
        self.assertEqual(self.close("OPEN", labels=["backport-declined"]), "reopened")
        self.assertEqual(
            bm.gh.writes(),
            [("-X", "DELETE", f"{LABELS}/backport-declined"), ("-X", "POST", LABELS)],
        )
        self.assertEqual(bm.gh.calls[-1][-1], "labels[]=backport-conflict")

    def test_not_a_backport_pr_refused(self):
        for change in (
            {"headRefName": "feat/x"},
            {"baseRefName": "main"},
            {"isCrossRepository": True},
            {"headRefName": "backport/0.186/ccccccc"},
            {"headRefName": "backport/0.187/ccccccc-x"},
            {"headRefName": "backport/0.187/cccccc"},
            {"author": {"login": ME, "is_bot": False}},
            {"author": {"login": BOT, "is_bot": False}},
            {"author": {"login": "app/other-app", "is_bot": True}},
        ):
            bm.gh = Gh("CLOSED", labels=["backport-conflict"])
            bm.gh.pr.update(change)
            with self.assertRaises(RuntimeError):
                bm.record("o/r", 7, ME)["result"]
            self.assertEqual(bm.gh.writes(), [])

    def test_unset_app_slug_refused(self):
        bm.gh = Gh("CLOSED", labels=["backport-conflict"])
        with mock.patch.dict(os.environ, {"RELEASE_BOT_APP_SLUG": ""}):
            with self.assertRaisesRegex(RuntimeError, "RELEASE_BOT_APP_SLUG is unset"):
                bm.record("o/r", 7, ME)["result"]
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
        self.assertEqual(bm.record("o/r", 7, ME)["result"], "merged")


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
            with mock.patch.object(bm, "head_messages", return_value=[edited]):
                self.assertEqual(
                    bm.first_pick(pr),
                    (f"fix: real (#9)\n\n(cherry picked from commit {o})", [o]),
                )
            with mock.patch.object(
                bm,
                "head_messages",
                return_value=["fix: x\n\n(cherry picked from commit " + "d" * 40 + ")"],
            ):
                self.assertEqual(
                    bm.first_pick({"headRefName": "backport/0.187/ddddddd"}), ("", [])
                )  # not on main
            with mock.patch.object(bm, "head_messages", return_value=[]):
                self.assertEqual(bm.first_pick(pr), (None, []))  # no commit past the base


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
            self.assertEqual(
                bm.summary(246, ME, rec("skipped: no pick", sha=None)),
                [
                    "**Backport PR** #246 on `release/0.189`: **skipped**: its head has no commit past the base, "
                    "so nothing was declined",
                    "Next: delete the head by hand to have the fix picked again; to decline it, keep the head "
                    "until the decline commit is on the base (the PR comment says how).",
                ],
            )
            self.assertEqual(
                bm.summary(246, ME, rec("skipped: no pick, head gone", sha=None))[1],
                "Next: nothing here; its head no longer holds this PR's commit.",
            )

    def test_links_under_actions(self):
        web = "https://github.com/Zipstack/unstract-cloud"
        env = {
            "GITHUB_SERVER_URL": "https://github.com",
            "GITHUB_REPOSITORY": "Zipstack/unstract-cloud",
        }
        rec = {
            "result": "merged",
            "base": "release/0.189",
            "sha": "6" * 40,
            "reason": None,
        }
        with mock.patch.dict(os.environ, env):
            out = bm.summary(246, ME, rec)
        base = f"[`release/0.189`]({web}/tree/release/0.189)"
        squash = f"[`6666666`]({web}/commit/{'6' * 40})"
        self.assertEqual(
            out,
            [
                f"**Backport PR** [#246]({web}/pull/246) on {base}: **merged** as {squash} (@{ME})",
                f"Undo: revert {squash} on {base}.",
            ],
        )


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
        self.assertEqual(self.run_squash([self.MOVED, None]), (True, 2, [4]))

    def test_base_modified_three_times_raises(self):
        with self.assertRaisesRegex(RuntimeError, "Base branch was modified"):
            self.run_squash([self.MOVED] * 5)

    def test_pending_check_is_not_retried(self):
        with mock.patch("builtins.print") as out:
            self.assertEqual(
                self.run_squash([RuntimeError("Required status check is expected")]),
                (False, 1, []),
            )
        out.assert_called_once_with(
            "#4: Required status check is expected"
        )  # GitHub's words reach the log

    def test_other_error_is_not_retried(self):
        calls = [RuntimeError("Head branch was modified (HTTP 409)"), None]
        with self.assertRaisesRegex(RuntimeError, "HTTP 409"):
            self.run_squash(calls)


# Verbatim from failed Backport runs during a GitHub incident; the 4xx ones in gh's "gh: <status> (HTTP <code>)" form.
S502 = "gh: Server Error (HTTP 502)"
BAD_GATEWAY = "pull request create failed: HTTP 502: 502 Bad Gateway (https://api.github.com/graphql)"
CUT_SHORT = "unexpected end of JSON input"
NOT_FOUND = "gh: Not Found (HTTP 404)"
# Messages from GitHub's REST rate-limit docs, in gh's "gh: <message> (HTTP <code>)" form.
PRIMARY_LIMIT = "gh: API rate limit exceeded for installation ID 1. (HTTP 403)"
SECONDARY_LIMIT = "gh: You have exceeded a secondary rate limit. Please wait a few minutes before you try again. (HTTP 403)"
TOO_MANY = "gh: Too Many Requests (HTTP 429)"
FORBIDDEN = "gh: Resource not accessible by integration (HTTP 403)"
MOVED_ERR = "gh: Base branch was modified. Review and try the merge again. (HTTP 405)"


class FakeGh:
    """subprocess.run for gh: answer(argv) gives (exit, stdout, stderr)."""

    def __init__(self, answer):
        self.answer, self.calls = answer, []

    def __call__(self, argv, **kw):
        self.calls.append(tuple(argv))
        return subprocess.CompletedProcess(argv, *self.answer(tuple(argv)))

    def count(self, *prefix):
        return sum(c[1 : 1 + len(prefix)] == prefix for c in self.calls)


def queue(*answers):
    q = list(answers)
    return lambda argv: q.pop(0)


class Transient(unittest.TestCase):
    def setUp(self):
        self.waits = []
        for p in (
            mock.patch.object(bm.time, "sleep", self.waits.append),
            mock.patch("builtins.print"),
        ):
            self.print = p.start()
            self.addCleanup(p.stop)

    def gh(self, answer, *args, **kw):
        fake = FakeGh(answer)
        with mock.patch.object(bm.subprocess, "run", fake):
            try:
                return bm.gh(*args, **kw), fake
            except RuntimeError as e:
                return e, fake

    def test_classification(self):
        for err in (
            S502,
            BAD_GATEWAY,
            CUT_SHORT,
            "net/http: TLS handshake timeout",
            "read: connection reset by peer",
            PRIMARY_LIMIT,
            SECONDARY_LIMIT,
            TOO_MANY,
        ):
            self.assertTrue(bm.transient(err), err)
        for err in (
            NOT_FOUND,
            MOVED_ERR,
            "Required status check is expected",
            "gh: Request Timeout (HTTP 408)",
            FORBIDDEN,
        ):
            self.assertFalse(bm.transient(err), err)

    def test_transient_failure_is_retried(self):
        out, fake = self.gh(queue((1, "", S502), (0, "ok\n", "")), "api", "x")
        self.assertEqual((out, len(fake.calls), self.waits), ("ok", 2, [4]))

    def test_retry_warning_stays_off_stdout(self):
        # oss.py's stdout is the tag promote.yaml captures.
        self.gh(queue((1, "", S502), (0, "ok\n", "")), "api", "x")
        (call,) = self.print.call_args_list
        self.assertIn("retried in", call.args[0])
        self.assertIs(call.kwargs.get("file"), bm.sys.stderr)

    def test_gives_up_after_five_tries(self):
        out, fake = self.gh(lambda a: (1, "", S502), "api", "x")
        self.assertIn("HTTP 502", str(out))
        self.assertEqual((len(fake.calls), self.waits), (5, [4, 8, 16, 32]))

    def test_rate_limit_is_retried_after_a_minute_or_more(self):
        for err in (PRIMARY_LIMIT, SECONDARY_LIMIT, TOO_MANY):
            self.waits.clear()
            out, fake = self.gh(
                queue((1, "", err), (1, "", err), (0, "ok\n", "")), "api", "x"
            )
            self.assertEqual(
                (out, len(fake.calls), self.waits), ("ok", 3, [60, 120]), err
            )

    def test_forbidden_is_not_a_rate_limit(self):
        out, fake = self.gh(lambda a: (1, "", FORBIDDEN), "api", "x")
        self.assertEqual((len(fake.calls), self.waits), (1, []))

    def test_waits_grow_and_are_jittered(self):
        with mock.patch.object(bm.random, "uniform", lambda lo, hi: lo):
            self.assertEqual([bm.gh_wait(n) for n in range(4)], [2, 4, 8, 16])
            self.assertEqual([bm.gh_wait(n, TOO_MANY) for n in range(4)], [60] * 4)
        self.assertEqual([bm.gh_wait(n, TOO_MANY) for n in range(4)], [60, 120, 120, 120])

    def test_client_error_is_never_retried(self):
        out, fake = self.gh(lambda a: (1, "", NOT_FOUND), "api", "x")
        self.assertIsInstance(out, RuntimeError)
        self.assertEqual(len(fake.calls), 1)

    def test_write_that_may_have_landed_is_not_retried_blindly(self):
        out, fake = self.gh(lambda a: (1, "", S502), "api", "x", retry=False)
        self.assertEqual((len(fake.calls), self.waits), (1, []))

    def squash(self, answer):
        fake, waits = FakeGh(answer), []
        with mock.patch.object(bm.subprocess, "run", fake):
            try:
                out = bm.squash("o/r", SquashRetry.PR, "t\n\nb", sleep=waits.append)
            except RuntimeError as e:
                out = e
        return (
            out,
            fake.count("api", "-X", "PUT"),
            fake.count("api", "repos/o/r/pulls/4"),
            waits,
        )

    def test_squash_cut_short_but_merged_is_merged(self):
        answer = lambda a: (1, "", CUT_SHORT) if "PUT" in a else (0, "true\n", "")
        self.assertEqual(self.squash(answer), (True, 1, 1, []))

    def test_squash_502_not_merged_is_retried(self):
        puts = queue((1, "", S502), (0, "{}", ""))
        answer = lambda a: puts(a) if "PUT" in a else (0, "false\n", "")
        self.assertEqual(self.squash(answer), (True, 2, 1, [4]))

    def test_squash_502_every_time_fails_after_checking_each(self):
        answer = lambda a: (1, "", S502) if "PUT" in a else (0, "false\n", "")
        out, puts, checks, waits = self.squash(answer)
        self.assertIn("HTTP 502", str(out))
        self.assertEqual((puts, checks, waits), (5, 5, [4, 8, 16, 32]))

    def test_squash_base_modified_still_retried_without_a_merged_check(self):
        puts = queue((1, "", MOVED_ERR), (0, "{}", ""))
        self.assertEqual(self.squash(puts), (True, 2, 0, [4]))


if __name__ == "__main__":
    unittest.main()
