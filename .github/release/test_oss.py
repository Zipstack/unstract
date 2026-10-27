"""OSS line work by git on a clone of a bare origin: cut (refuses an existing line or used minor, recovers its own
re-run), rc (tip tag else a new ee- RC; plain v* ignored), promote (open conflict PRs and the gate block unless forced, re-runnable), retire
(archive tag; RC tags go without a GA), and a tag already on another commit fails. Run: python test_oss.py
"""

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
    "Zipstack/unstract-cloud"  # relstate loads the cloud config, whatever the runner sets
)
import oss
import relmgr as rm

os.environ.update(GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_NOSYSTEM="1")
os.environ.pop("GITHUB_STEP_SUMMARY", None)


class Choose(unittest.TestCase):
    def test_stable_else_newest_rc(self):
        self.assertEqual(oss.choose(["ee-v1.7.0-rc.2", "ee-v1.7.0"]), "ee-v1.7.0")
        self.assertEqual(
            oss.choose(["ee-v1.7.0-rc.9", "ee-v1.7.0-rc.10"]), "ee-v1.7.0-rc.10"
        )
        self.assertIsNone(oss.choose([]))


class Lines(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.origin, self.dev, self.oss, self.cloud = (
            os.path.join(tmp.name, d) for d in ("origin", "dev", "oss", "cloud")
        )
        rm.git(tmp.name, "init", "-q", "--bare", "-b", "main", self.origin)
        rm.git(tmp.name, "clone", "-q", self.origin, self.dev)
        self.g(self.dev, "commit", "-q", "--allow-empty", "-m", "base")
        self.g(
            self.dev, "tag", "v1.7.3"
        )  # a community release on main: never an OSS line's tag
        self.g(self.dev, "push", "-q", "origin", "main", "v1.7.3")
        self.clone()
        self.gates = []
        self.gate = 0
        p = mock.patch.object(
            oss,
            "gate",
            lambda o, b, ref, annotate: self.gates.append((b, ref, annotate))
            or self.gate,
        )
        p.start()
        self.addCleanup(p.stop)
        self.prs, self.listed = (
            [],
            [],
        )  # open backport-conflict PRs of the OSS repo, and each listing's (slug, base, token)
        p = mock.patch.object(
            oss.bp,
            "conflict_prs",
            lambda *a: self.listed.append(a)
            or [{"number": n, "baseRefName": b} for n, b in self.prs if b == a[1]],
        )
        p.start()
        self.addCleanup(p.stop)

    def g(self, repo, *args):
        return rm.git(
            repo, "-c", "user.name=Dev", "-c", "user.email=dev@example.com", *args
        )

    def clone(self):  # a fresh workflow run's OSS clone
        rm.git(
            os.path.dirname(self.oss),
            "clone",
            "-q",
            "--no-checkout",
            self.origin,
            self.oss,
        ) if not os.path.isdir(self.oss) else self.g(
            self.oss, "fetch", "-q", "--prune", "--prune-tags", "--tags", "origin"
        )

    def remote(self, *args):
        return self.g(self.origin, *args)

    def quiet(self, f, *args, **kw):
        with contextlib.redirect_stderr(io.StringIO()):
            return f(*args, **kw)

    def work(self, branch, msg):  # a developer's commit on the OSS line, pushed
        self.g(self.dev, "fetch", "-q", "origin")
        self.g(self.dev, "checkout", "-q", "-B", branch, f"origin/{branch}")
        self.g(self.dev, "commit", "-q", "--allow-empty", "-m", msg)
        self.g(self.dev, "push", "-q", "origin", branch)
        self.g(self.dev, "checkout", "-q", "main")
        self.clone()

    def test_cut(self):
        self.assertEqual(
            self.quiet(oss.cut, self.oss, "1.7", "https://x.slack.com/archives/C1/p1"),
            "ee-v1.7.0-rc.1",
        )
        tip = self.remote("rev-parse", "release/1.7")
        self.assertEqual(self.remote("rev-parse", "ee-v1.7.0-rc.1^{commit}"), tip)
        self.assertEqual(
            self.remote("log", "-1", "--format=%ae %s", tip),
            f"{rm.BOT_EMAIL} release: ee-v1.7.0-rc.1",
        )
        self.assertEqual(
            self.remote("rev-parse", f"{tip}^"), self.remote("rev-parse", "main")
        )
        self.assertIn(
            "Slack: https://x.slack.com/archives/C1/p1",
            self.remote("tag", "-l", "ee-v1.7.0-rc.1", "--format=%(contents)"),
        )
        # A re-run of the same cut (its cloud branch push failed) finds its own result.
        self.clone()
        self.assertEqual(self.quiet(oss.cut, self.oss, "1.7"), "ee-v1.7.0-rc.1")
        self.assertEqual(self.remote("rev-parse", "release/1.7"), tip)
        # Any other existing line is refused: work on it, or a line cut by hand.
        self.work("release/1.7", "oss work")
        with self.assertRaisesRegex(RuntimeError, "OSS release/1.7 already exists"):
            oss.cut(self.oss, "1.7")
        self.g(self.dev, "push", "-q", "origin", "main:refs/heads/release/1.8")
        self.clone()
        with self.assertRaisesRegex(RuntimeError, "OSS release/1.8 already exists"):
            oss.cut(self.oss, "1.8")

    def test_cut_refuses_a_used_minor(self):
        self.remote(
            "tag", "ee-v1.9.0", "main"
        )  # a retired line that shipped: its GA tag stays
        self.clone()
        with self.assertRaisesRegex(
            RuntimeError, r"OSS minor 1.9 already has tags \(ee-v1.9.0\)"
        ):
            oss.cut(self.oss, "1.9")
        self.assertEqual(
            self.quiet(oss.cut, self.oss, "1.7"), "ee-v1.7.0-rc.1"
        )  # plain v1.7.3 does not count

    def test_rc(self):
        with self.assertRaisesRegex(RuntimeError, "OSS release/1.7 does not exist"):
            oss.rc(self.oss, "release/1.7")
        self.quiet(oss.cut, self.oss, "1.7")
        self.clone()
        self.assertEqual(
            self.quiet(oss.rc, self.oss, "release/1.7"), "ee-v1.7.0-rc.1"
        )  # the tip's tag
        self.work("release/1.7", "oss fix")
        self.remote(
            "tag", "v1.7.4", "release/1.7"
        )  # a plain v* tag on the tip is not the line's
        self.clone()
        self.assertEqual(self.quiet(oss.rc, self.oss, "release/1.7"), "ee-v1.7.0-rc.2")
        tip = self.remote("rev-parse", "release/1.7")
        self.assertEqual(self.remote("rev-parse", "ee-v1.7.0-rc.2^{commit}"), tip)
        self.assertEqual(
            self.remote("log", "-1", "--format=%s", tip), "release: ee-v1.7.0-rc.2"
        )
        self.assertEqual(
            self.gates,
            [
                ("release/1.7", "ee-v1.7.0-rc.1", "warning"),
                ("release/1.7", "ee-v1.7.0-rc.2", "warning"),
            ],
        )
        self.gate = 2  # the preview never blocks
        self.assertEqual(self.quiet(oss.rc, self.oss, "release/1.7"), "ee-v1.7.0-rc.2")

    def pin(self, tag, rc):
        if not os.path.isdir(self.cloud):
            rm.git(os.path.dirname(self.cloud), "init", "-q", "-b", "main", self.cloud)
        with open(os.path.join(self.cloud, "pyproject.toml"), "w") as f:
            f.write(f'unstract-platform-version = "{tag}"\n')
        self.g(self.cloud, "add", "pyproject.toml")
        self.g(self.cloud, "commit", "-q", "-m", f"pin {tag}")
        self.g(self.cloud, "tag", rc)

    def test_promote(self):
        self.quiet(oss.cut, self.oss, "1.7")
        self.pin("ee-v1.7.0-rc.1", "v1.7.0-rc.1")
        self.gate = 2
        with self.assertRaisesRegex(RuntimeError, "blocks: MISSING picks"):
            oss.promote(self.cloud, self.oss, "v1.7.0-rc.1")
        self.assertEqual(self.remote("tag", "-l", "ee-v1.7.0"), "")
        self.assertEqual(
            oss.promote(
                self.cloud, self.oss, "v1.7.0-rc.1", force=True, reason="known gap"
            ),
            "ee-v1.7.0",
        )
        self.assertEqual(
            self.remote("rev-parse", "ee-v1.7.0^{commit}"),
            self.remote("rev-parse", "ee-v1.7.0-rc.1^{commit}"),
        )
        msg = self.remote("tag", "-l", "ee-v1.7.0", "--format=%(contents)")
        self.assertIn("promote: ee-v1.7.0-rc.1 -> ee-v1.7.0 (cloud v1.7.0-rc.1)", msg)
        self.assertIn("forced: known gap", msg)
        n = len(self.gates)
        self.clone()  # the other cloud product: finds the tag, skips the gate
        self.assertEqual(oss.promote(self.cloud, self.oss, "v1.7.0-rc.1"), "ee-v1.7.0")
        self.assertEqual(len(self.gates), n)
        self.pin("ee-v1.7.0", "v1.7.1-rc.1")  # a stable pin needs no promote
        self.assertEqual(oss.promote(self.cloud, self.oss, "v1.7.1-rc.1"), "ee-v1.7.0")
        self.gate = 1
        self.work("release/1.7", "oss fix")
        self.quiet(oss.rc, self.oss, "release/1.7")
        self.pin("ee-v1.7.1-rc.1", "v1.7.1-rc.2")
        with self.assertRaisesRegex(RuntimeError, "did not run"):
            oss.promote(self.cloud, self.oss, "v1.7.1-rc.2", force=True, reason="x")

    def test_on_prem_promote_tags_on_prem_ga_once(self):
        # The OSS line stays stabilizing until its cloud line's on-prem GA: only --on-prem writes the tag, once.
        self.quiet(oss.cut, self.oss, "1.7")
        self.pin("ee-v1.7.0-rc.1", "v1.7.0-rc.1")
        oss.promote(self.cloud, self.oss, "v1.7.0-rc.1")  # the cloud product
        self.assertEqual(self.remote("tag", "-l", "on-prem-ga/*"), "")
        self.clone()
        oss.promote(self.cloud, self.oss, "v1.7.0-rc.1", on_prem=True)
        ga = self.remote("rev-parse", "ee-v1.7.0^{commit}")
        self.assertEqual(self.remote("rev-parse", "on-prem-ga/1.7^{commit}"), ga)
        self.work("release/1.7", "oss fix")
        self.quiet(oss.rc, self.oss, "release/1.7")
        self.pin("ee-v1.7.1-rc.1", "v1.7.1-rc.1")
        self.clone()
        self.assertEqual(
            oss.promote(self.cloud, self.oss, "v1.7.1-rc.1", on_prem=True), "ee-v1.7.1"
        )
        self.assertEqual(self.remote("rev-parse", "on-prem-ga/1.7^{commit}"), ga)

    def test_cli_on_prem_flag(self):
        self.quiet(oss.cut, self.oss, "1.7")
        self.pin("ee-v1.7.0-rc.1", "v1.7.0-rc.1")
        self.addCleanup(os.chdir, os.getcwd())
        os.chdir(self.cloud)  # main promotes the cloud clone in the working directory
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = oss.main(
                ["--oss-repo", self.oss, "promote", "--rc", "v1.7.0-rc.1", "--on-prem"]
            )
        self.assertEqual((code, out.getvalue()), (0, "ee-v1.7.0\n"))
        self.assertEqual(
            self.remote("rev-parse", "on-prem-ga/1.7^{commit}"),
            self.remote("rev-parse", "ee-v1.7.0^{commit}"),
        )

    def test_promote_refuses_a_downgrade(self):
        self.quiet(oss.cut, self.oss, "1.7")
        self.work("release/1.7", "oss fix")
        self.quiet(oss.rc, self.oss, "release/1.7")
        self.remote("tag", "ee-v1.7.0", "ee-v1.7.0-rc.2")  # the later RC shipped
        self.clone()
        with self.assertRaisesRegex(
            ValueError,
            "ee-v1.7.0-rc.1 is older than ee-v1.7.0: promoting it would be a downgrade",
        ):
            rm.promote_version(self.oss, "ee-v1.7.0-rc.1")
        self.pin("ee-v1.7.0-rc.1", "v1.7.0-rc.1")
        with self.assertRaisesRegex(
            RuntimeError, "^OSS ee-v1.7.0-rc.1 is older than ee-v1.7.0"
        ):
            oss.promote(self.cloud, self.oss, "v1.7.0-rc.1")
        self.assertEqual(
            self.gates, [("release/1.7", "ee-v1.7.0-rc.2", "warning")]
        )  # refused before its gate

    @mock.patch.dict(os.environ, {"OSS_TOKEN": "oss-token"})
    def test_promote_blocks_on_open_conflict_prs(self):
        self.quiet(oss.cut, self.oss, "1.7")
        self.pin("ee-v1.7.0-rc.1", "v1.7.0-rc.1")
        self.prs = [(4, "release/1.7"), (5, "release/1.6")]
        with self.assertRaisesRegex(
            RuntimeError, r"OSS release/1.7 has open backport conflict PRs #4: "
        ):
            oss.promote(self.cloud, self.oss, "v1.7.0-rc.1")
        self.assertEqual(self.listed, [(oss.OSS, "release/1.7", "oss-token")])
        self.assertEqual(self.remote("tag", "-l", "ee-v1.7.0"), "")
        self.assertEqual(
            oss.promote(
                self.cloud, self.oss, "v1.7.0-rc.1", force=True, reason="ship it"
            ),
            "ee-v1.7.0",
        )
        msg = self.remote("tag", "-l", "ee-v1.7.0", "--format=%(contents)")
        self.assertIn("forced: ship it", msg)
        self.assertIn("open conflict PRs: #4", msg)

    def test_promote_fails_closed_when_the_listing_fails(self):
        self.quiet(oss.cut, self.oss, "1.7")
        self.pin("ee-v1.7.0-rc.1", "v1.7.0-rc.1")
        with mock.patch.object(
            oss.bp, "conflict_prs", side_effect=RuntimeError("gh pr list (exit 1)")
        ):
            with self.assertRaisesRegex(RuntimeError, "gh pr list"):
                oss.promote(self.cloud, self.oss, "v1.7.0-rc.1")
            self.assertEqual(self.remote("tag", "-l", "ee-v1.7.0"), "")
            with contextlib.redirect_stderr(
                io.StringIO()
            ) as err:  # forced: promoted, the gap recorded on the tag
                self.assertEqual(
                    oss.promote(
                        self.cloud, self.oss, "v1.7.0-rc.1", force=True, reason="x"
                    ),
                    "ee-v1.7.0",
                )
        self.assertIn(
            "::warning::Could not list open backport conflict PRs on OSS release/1.7",
            err.getvalue(),
        )
        msg = self.remote("tag", "-l", "ee-v1.7.0", "--format=%(contents)")
        self.assertIn("forced: x", msg)
        self.assertIn("conflict PRs unchecked: listing failed", msg)

    def test_tag_on_another_commit_fails(self):
        self.quiet(oss.cut, self.oss, "1.7")
        tip, main = (self.remote("rev-parse", r) for r in ("release/1.7", "main"))
        self.assertFalse(
            oss._tag(self.oss, "ee-v1.7.0-rc.1", tip)
        )  # same commit: skipped
        with self.assertRaisesRegex(
            RuntimeError, f"OSS tag ee-v1.7.0-rc.1 is on {tip[:12]}, not on {main[:12]}"
        ):
            oss._tag(self.oss, "ee-v1.7.0-rc.1", main)
        self.remote(
            "tag", f"retired/1.7-{tip[:7]}", "main"
        )  # the archive name, taken on another commit
        self.clone()
        with self.assertRaisesRegex(RuntimeError, f"OSS tag retired/1.7-{tip[:7]} is on"):
            oss.retire(self.oss, "release/1.7", "x", dry_run=False)
        self.assertEqual(self.remote("rev-parse", "release/1.7"), tip)  # nothing deleted

    def test_retire(self):
        self.quiet(oss.cut, self.oss, "1.7")
        self.work("release/1.7", "oss fix")
        self.quiet(oss.rc, self.oss, "release/1.7")
        tip = self.remote("rev-parse", "release/1.7")
        dry = oss.retire(self.oss, "release/1.7", "cut by mistake")
        self.assertEqual(
            dry,
            [
                f"- OSS `release/1.7` (tip `{tip[:12]}`; no GA, RC tags deleted)",
                "- OSS git tag `ee-v1.7.0-rc.1`",
                "- OSS git tag `ee-v1.7.0-rc.2`",
                f"- OSS tag `retired/1.7-{tip[:7]}`: cut by mistake",
            ],
        )
        self.assertEqual(
            self.remote("tag", "-l", "ee-*").split(), ["ee-v1.7.0-rc.1", "ee-v1.7.0-rc.2"]
        )  # dry run
        self.assertEqual(
            oss.retire(self.oss, "release/1.7", "cut by mistake", dry_run=False), dry
        )
        self.assertEqual(self.remote("tag", "-l", "ee-*"), "")
        self.assertEqual(self.remote("tag", "-l", "v*"), "v1.7.3")
        self.assertEqual(self.remote("branch", "-l", "release/*"), "")
        self.assertEqual(
            self.remote("rev-parse", f"retired/1.7-{tip[:7]}^{{commit}}"), tip
        )
        self.assertIn(
            "retired release/1.7: cut by mistake",
            self.remote("tag", "-l", "retired/*", "--format=%(contents)"),
        )
        self.clone()  # a re-run finds the line gone; the minor is free again
        self.assertEqual(
            oss.retire(self.oss, "release/1.7", "cut by mistake", dry_run=False),
            [f"- OSS `release/1.7`: no branch (archived as `retired/1.7-{tip[:7]}`)"],
        )
        self.assertEqual(self.quiet(oss.cut, self.oss, "1.7"), "ee-v1.7.0-rc.1")
        self.clone()  # the reused minor retires again: the old line's archive tag is not on its history
        self.assertEqual(
            len(oss.retire(self.oss, "release/1.7", "again", dry_run=False)), 3
        )
        self.assertEqual(len(self.remote("tag", "-l", "retired/1.7-*").split()), 2)

    def test_retire_keeps_a_branch_pushed_after_its_tip_was_read(self):
        self.quiet(oss.cut, self.oss, "1.7")
        self.clone()
        self.g(self.dev, "fetch", "-q", "origin")  # a commit lands after this run fetched
        self.g(self.dev, "checkout", "-q", "-B", "release/1.7", "origin/release/1.7")
        self.g(self.dev, "commit", "-q", "--allow-empty", "-m", "late fix")
        self.g(self.dev, "push", "-q", "origin", "release/1.7")
        late = self.g(self.dev, "rev-parse", "HEAD")
        self.g(self.dev, "checkout", "-q", "main")
        with self.assertRaises(RuntimeError):
            oss.retire(self.oss, "release/1.7", "x", dry_run=False)
        self.assertEqual(self.remote("rev-parse", "release/1.7"), late)
        self.assertEqual(self.remote("tag", "-l", "ee-v1.7.*"), "ee-v1.7.0-rc.1")
        self.assertEqual(self.remote("tag", "-l", "retired/*"), "")
        self.assertEqual(
            self.g(self.oss, "tag", "-l", "retired/*"), ""
        )  # nor left in the clone

    def test_retire_rerun_in_the_same_clone_archives_the_tip(self):
        self.quiet(oss.cut, self.oss, "1.7")
        self.clone()
        tip = self.remote("rev-parse", "release/1.7")
        push, calls = oss._push, []

        def flaky(
            *a,
        ):  # the first push fails (network, a remote hook), the re-run's goes through
            calls.append(a)
            if len(calls) == 1:
                raise RuntimeError("push failed")
            return push(*a)

        with mock.patch.object(oss, "_push", flaky):
            with self.assertRaises(RuntimeError):
                oss.retire(self.oss, "release/1.7", "x", dry_run=False)
            oss.retire(self.oss, "release/1.7", "x", dry_run=False)
        self.assertEqual(
            self.remote("rev-parse", f"retired/1.7-{tip[:7]}^{{commit}}"), tip
        )
        self.assertEqual(self.remote("branch", "-l", "release/1.7"), "")

    def test_retire_pushes_an_archive_tag_left_in_the_clone(self):
        self.quiet(oss.cut, self.oss, "1.7")
        self.clone()
        tip = self.remote("rev-parse", "release/1.7")
        oss._tag(self.oss, f"retired/1.7-{tip[:7]}", tip, "a run killed before its push")
        oss.retire(self.oss, "release/1.7", "x", dry_run=False)
        self.assertEqual(
            self.remote("rev-parse", f"retired/1.7-{tip[:7]}^{{commit}}"), tip
        )

    def test_rc_refuses_a_branch_deleted_after_its_tip_was_read(self):
        self.quiet(oss.cut, self.oss, "1.7")
        self.work("release/1.7", "oss fix")  # an untagged tip, so rc bumps
        self.clone()
        self.remote(
            "update-ref", "-d", "refs/heads/release/1.7"
        )  # a retire lands after this run fetched
        with self.assertRaises(RuntimeError):
            self.quiet(oss.rc, self.oss, "release/1.7")
        self.assertEqual(self.remote("branch", "-l", "release/1.7"), "")

    def test_cut_refuses_a_branch_created_after_it_fetched(self):
        self.clone()
        main = self.remote("rev-parse", "main")
        self.remote(
            "update-ref", "refs/heads/release/1.7", main
        )  # another run cut the line after this run fetched
        with self.assertRaises(RuntimeError):
            self.quiet(oss.cut, self.oss, "1.7")
        self.assertEqual(self.remote("rev-parse", "release/1.7"), main)
        self.assertEqual(
            rm.git(self.oss, "tag", "-l", "ee-v1.7.0-rc.*"), ""
        )  # nor left in the clone, where a re-run would read the minor as used

    def test_promote_rerun_in_the_same_clone_pushes_the_tag(self):
        self.quiet(oss.cut, self.oss, "1.7")
        self.pin("ee-v1.7.0-rc.1", "v1.7.0-rc.1")
        push, calls = oss._push, []

        def flaky(*a):  # the first push fails, the re-run's goes through
            calls.append(a)
            if len(calls) == 1:
                raise RuntimeError("push failed")
            return push(*a)

        with mock.patch.object(oss, "_push", flaky):
            with self.assertRaises(RuntimeError):
                oss.promote(self.cloud, self.oss, "v1.7.0-rc.1")
            self.assertEqual(rm.git(self.oss, "tag", "-l", "ee-v1.7.0"), "")
            self.assertEqual(
                oss.promote(self.cloud, self.oss, "v1.7.0-rc.1"), "ee-v1.7.0"
            )
        self.assertEqual(len(calls), 2)
        self.assertEqual(
            self.remote("rev-parse", "ee-v1.7.0^{commit}"),
            self.remote("rev-parse", "ee-v1.7.0-rc.1^{commit}"),
        )

    def test_retire_refuses_a_line_moved_after_its_archive(self):
        self.quiet(oss.cut, self.oss, "1.7")
        tip = self.remote("rev-parse", "release/1.7")
        self.remote(
            "tag", f"retired/1.7-{tip[:7]}", tip
        )  # an earlier run archived, then failed before the delete
        self.work("release/1.7", "oss fix")
        self.clone()
        with self.assertRaisesRegex(
            RuntimeError, f"moved to .* after retired/1.7-{tip[:7]} archived it"
        ):
            oss.retire(self.oss, "release/1.7", "again")
        self.assertEqual(
            self.remote("tag", "-l", "retired/*").split(), [f"retired/1.7-{tip[:7]}"]
        )

    def test_retire_keeps_a_shipped_line(self):
        self.quiet(oss.cut, self.oss, "1.7")
        self.pin("ee-v1.7.0-rc.1", "v1.7.0-rc.1")
        oss.promote(self.cloud, self.oss, "v1.7.0-rc.1")
        tip = self.remote("rev-parse", "release/1.7")
        self.assertEqual(
            oss.retire(self.oss, "release/1.7", "past end of support", dry_run=False),
            [
                f"- OSS `release/1.7` (tip `{tip[:12]}`; has GA, tags kept)",
                f"- OSS tag `retired/1.7-{tip[:7]}`: past end of support",
            ],
        )
        self.assertEqual(
            self.remote("tag", "-l", "ee-*").split(), ["ee-v1.7.0", "ee-v1.7.0-rc.1"]
        )
        self.assertEqual(self.remote("branch", "-l", "release/*"), "")
        self.clone()
        with self.assertRaisesRegex(RuntimeError, "OSS minor 1.7 already has tags"):
            oss.cut(self.oss, "1.7")


class Gate(unittest.TestCase):
    def test_runs_on_the_oss_clone_as_the_oss_repo(self):
        # OSS 1.6 shipped with OSS fix F picked; OSS 1.7 lacks it. The gate reads only ee- tags and asks the OSS repo
        # (not the cloud one) for Backport conflict PRs.
        with tempfile.TemporaryDirectory() as d:
            g = lambda *a: rm.git(
                d, "-c", "user.name=Dev", "-c", "user.email=dev@example.com", *a
            )
            g("init", "-q", "-b", "main")
            g("commit", "-q", "--allow-empty", "-m", "base")
            g("branch", "release/1.6")
            g("branch", "release/1.7")
            with open(os.path.join(d, "f.txt"), "w") as fh:
                fh.write("fix")
            g("add", "f.txt")
            g("commit", "-q", "-m", "F: oss fix (#7)")
            f = g("rev-parse", "HEAD")
            g("tag", "v1.7.3")  # a community release: never the 1.7 line's
            g("checkout", "-q", "release/1.6")
            g("cherry-pick", "-x", f)
            g("tag", "ee-v1.6.0-rc.1")
            g("tag", "ee-v1.6.0")
            g("checkout", "-q", "release/1.7")
            g("commit", "-q", "--allow-empty", "-m", "release: ee-v1.7.0-rc.1")
            g("tag", "ee-v1.7.0-rc.1")
            for b in ("main", "release/1.6", "release/1.7"):
                g("update-ref", f"refs/remotes/origin/{b}", b)
            bin_ = os.path.join(d, "bin")
            os.mkdir(bin_)
            with open(os.path.join(bin_, "gh"), "w") as fh:
                fh.write(f'#!/bin/sh\necho "$@" >> {d}/gh.log\necho "[]"\n')
            os.chmod(os.path.join(bin_, "gh"), 0o755)
            with mock.patch.dict(
                os.environ,
                PATH=f"{bin_}:{os.environ['PATH']}",
                GITHUB_REPOSITORY="Zipstack/x",
            ):
                self.assertEqual(oss.gate(d, "release/1.7", "ee-v1.7.0-rc.1", "error"), 2)
            with open(os.path.join(d, "gh.log")) as fh:
                self.assertIn(f"-R {oss.OSS} --head backport/1.7/{f[:7]}", fh.read())

    def test_usage_error_is_an_error_not_a_block(self):
        # argparse exits 2 on a usage error, the code a MISSING block uses: only a block may be forced past.
        with tempfile.TemporaryDirectory() as d:
            fake = os.path.join(d, "convgate.py")
            for script, want in (
                ("import sys; sys.exit(2)", 2),
                ("import argparse; argparse.ArgumentParser().parse_args(['--nope'])", 1),
                ("import sys; sys.exit(3)", 1),
                ("pass", 0),
            ):
                with open(fake, "w") as fh:
                    fh.write(script)
                with (
                    mock.patch.object(oss, "HERE", d),
                    contextlib.redirect_stderr(io.StringIO()),
                ):
                    self.assertEqual(
                        oss.gate(d, "release/1.7", "ee-v1.7.0-rc.1", "error"),
                        want,
                        script,
                    )


HERE = os.path.dirname(os.path.abspath(__file__))


def inline(workflow, step):
    """The inline python of a workflow step."""
    with open(os.path.join(HERE, "..", "workflows", workflow)) as fh:
        wf = fh.read()
    body = wf[
        wf.index("python3 - <<'PY'", wf.index(f"- name: {step}\n")) :
    ]  # the heredoc line may redirect
    return "\n".join(
        line[10:] for line in body.split("\n")[1 : body.split("\n").index("          PY")]
    )


@unittest.skipUnless(
    os.path.exists(os.path.join(HERE, "..", "workflows", "retire.yaml")),
    "the cloud repo's workflows",
)
class Workflow(unittest.TestCase):
    """A cloud and an OSS origin with clones; a sitecustomize stands in for Artifact Registry with reg.jsonl as
    cloud/backend's versions (other artifacts empty); a stub gh serves the open backport-conflict PRs of each repo
    (<owner>_<repo>.json; a `prfail` file fails the listing) and the PRs of a main commit (pulls.json). gh.log:
    each pr list and commit PRs call, as its token.
    """

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.d = d = tmp.name
        self.repos = {}
        for name in ("cloud", "oss"):
            origin, work = os.path.join(d, f"{name}.git"), os.path.join(d, name)
            rm.git(d, "init", "-q", "--bare", "-b", "main", origin)
            rm.git(d, "clone", "-q", origin, work)
            self.g(work, "commit", "-q", "--allow-empty", "-m", "base")
            self.g(work, "push", "-q", "origin", "main")
            self.repos[name] = (origin, work)
        os.makedirs(os.path.join(self.cloud, ".relmgr", ".github"))
        os.symlink(HERE, os.path.join(self.cloud, ".relmgr", ".github", "release"))
        self.site = os.path.join(d, "site")
        os.mkdir(self.site)
        with open(os.path.join(self.site, "sitecustomize.py"), "w") as fh:
            fh.write(f"""import json, os, sys
sys.path.insert(0, {HERE!r})
import relstate
def _ar_versions(artifact):  # reg.jsonl as Artifact Registry versions of cloud/backend; other artifacts empty
    if artifact != "cloud/backend" or not os.path.exists({os.path.join(d, "reg.jsonl")!r}):
        return []
    with open({os.path.join(d, "reg.jsonl")!r}) as fh:
        rows = [json.loads(line) for line in fh]
    return [{{"name": f"r/packages/backend/versions/{{v['digest']}}", "createTime": v["pushed_at"],
              "relatedTags": [{{"name": f"r/packages/backend/tags/{{t}}"}} for t in v["tags"]]}} for v in rows]
relstate._ar_versions = _ar_versions
""")
        bin_ = os.path.join(d, "bin")
        os.mkdir(bin_)
        with open(os.path.join(bin_, "gh"), "w") as fh:
            fh.write(f"""#!/bin/sh
case "$*" in
  "pr list -R "*) echo "$GH_TOKEN $*" >> {d}/gh.log; [ -e {d}/prfail ] && exit 1
    cat "{d}/$(echo "$4" | tr / _).json" 2>/dev/null || echo "[]";;
  *"/pulls"*) echo "$GH_TOKEN $*" >> {d}/gh.log; [ -e {d}/pullsfail ] && exit 1
    cat {d}/pulls.json 2>/dev/null || echo "[]";;
esac
true
""")
        os.chmod(os.path.join(bin_, "gh"), 0o755)
        self.path = f"{bin_}:{os.environ['PATH']}"

    cloud = property(lambda self: self.repos["cloud"][1])

    def g(self, repo, *a):
        return rm.git(repo, "-c", "user.name=Dev", "-c", "user.email=dev@example.com", *a)

    def line(
        self, x_y, *tags
    ):  # cloud and OSS release/X.Y; tags: cloud tags on the cloud tip, also in the registry
        self.g(self.cloud, "push", "-q", "origin", f"main:refs/heads/release/{x_y}")
        for i, t in enumerate(tags):
            self.g(self.cloud, "tag", t, "main")
            self.g(self.cloud, "push", "-q", "origin", t)
            with open(os.path.join(self.d, "reg.jsonl"), "a") as fh:
                fh.write(
                    f'{{"id": {len(t) * 10 + i}, "digest": "sha256:{t}", "pushed_at": "2026-09-01T00:00:00Z", '
                    f'"tags": ["{t}"]}}\n'
                )
        with contextlib.redirect_stderr(io.StringIO()):
            oss.cut(self.repos["oss"][1], x_y)

    def run_step(self, script, **env):
        self.g(self.cloud, "fetch", "-q", "--tags", "origin")
        for name in ("output", "notes.md"):  # a fresh run's files
            with contextlib.suppress(FileNotFoundError):
                os.remove(os.path.join(self.d, name))
        env = {
            **os.environ,
            "PATH": self.path,
            "PYTHONPATH": self.site,
            "FORCE": "false",
            "REASON": "",
            "OSS_REPO": self.repos["oss"][1],
            "OSS_TOKEN": "oss-token",
            "GH_TOKEN": "cloud-token",
            "RUNNER_TEMP": self.d,
            "GITHUB_REPOSITORY": "Zipstack/unstract-cloud",
            "GITHUB_STEP_SUMMARY": os.path.join(self.d, "summary"),
            "GITHUB_OUTPUT": os.path.join(self.d, "output"),
            **env,
        }
        return subprocess.run(
            [sys.executable, "-"],
            input=script,
            cwd=self.cloud,
            env=env,
            capture_output=True,
            text=True,
        )

    def read(self, name):
        with open(os.path.join(self.d, name)) as fh:
            return fh.read()

    def write(self, name, data):
        with open(os.path.join(self.d, name), "w") as fh:
            fh.write(data)


class RetireWorkflow(Workflow):
    """Retire's inline script in each mode: the OSS line goes with the cloud one."""

    def retire(self, **env):
        r = self.run_step(
            inline("retire.yaml", "Derive and retire"),
            **{"ABANDON": "", "RETIRE_LINE": "", "NOW": "", "DRY_RUN": "false", **env},
        )
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def assert_gone(self, x_y):
        c_origin, o_origin = self.repos["cloud"][0], self.repos["oss"][0]
        self.assertNotIn(f"release/{x_y}", rm.git(c_origin, "branch", "-l", "release/*"))
        self.assertNotIn(f"release/{x_y}", rm.git(o_origin, "branch", "-l", "release/*"))
        self.assertEqual(
            rm.git(o_origin, "tag", "-l", f"ee-v{x_y}.*"), ""
        )  # no OSS GA: RC tags go
        self.assertRegex(
            rm.git(o_origin, "tag", "-l", f"retired/{x_y}-*"),
            rf"^retired/{re.escape(x_y)}-[0-9a-f]{{7}}$",
        )

    def test_abandon(self):
        self.line("1.7")
        self.retire(ABANDON="release/1.7", REASON="cut by mistake")
        self.assert_gone("1.7")

    def test_retire_line_no_ga(self):
        self.line("1.7")
        self.retire(RETIRE_LINE="release/1.7", REASON="not shipping")
        self.assert_gone("1.7")

    def test_derived_list(self):
        self.line("1.6", "v1.6.0-rc.1", "v1.6.0")
        self.line(
            "1.7", "v1.7.0-rc.1", "v1.7.0"
        )  # 1.7 is cloud production: 1.6 is past end of support
        self.retire()
        self.assert_gone("1.6")
        self.assertRegex(
            rm.git(
                self.repos["cloud"][0],
                "tag",
                "-l",
                "retired/1.6-*",
                "--format=%(refname:short) %(contents)",
            ),
            r"^retired/1\.6-[0-9a-f]{7} retired release/1\.6: past end of support",
        )
        self.assertIn(
            "release/1.7", rm.git(self.repos["oss"][0], "branch", "-l", "release/*")
        )

    def moved(
        self, x_y
    ):  # an earlier run archived release/x_y, failed before the delete, then the line moved
        origin = self.repos["cloud"][0]
        tip = rm.git(origin, "rev-parse", f"release/{x_y}")
        rm.git(origin, "tag", f"retired/{x_y}-{tip[:7]}", tip)
        self.g(self.cloud, "commit", "-q", "--allow-empty", "-m", "late fix")
        self.g(self.cloud, "push", "-q", "origin", f"HEAD:refs/heads/release/{x_y}")
        return f"retired/{x_y}-{tip[:7]}"

    def refused(self, x_y, tag, **env):
        origin = self.repos["cloud"][0]
        r = self.run_step(
            inline("retire.yaml", "Derive and retire"),
            **{"ABANDON": "", "RETIRE_LINE": "", "NOW": "", "DRY_RUN": "false", **env},
        )
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn(f"after {tag} archived it", r.stdout)
        self.assertEqual(rm.git(origin, "tag", "-l", "retired/*"), tag)
        self.assertIn(f"release/{x_y}", rm.git(origin, "branch", "-l", "release/*"))

    def test_retire_line_refuses_a_line_moved_after_its_archive(self):
        self.line("1.7")
        self.refused(
            "1.7", self.moved("1.7"), RETIRE_LINE="release/1.7", REASON="not shipping"
        )

    def test_derived_list_refuses_a_line_moved_after_its_archive(self):
        self.line("1.6", "v1.6.0-rc.1", "v1.6.0")
        tag = self.moved("1.6")
        self.line("1.7", "v1.7.0-rc.1", "v1.7.0")
        self.refused("1.6", tag)


class PendingPicksWorkflow(Workflow):
    """Promote's Plan blocks on open backport-conflict PRs of the cloud line or the OSS line it pins, and on held
    security/critical fixes, unless forced (recorded). A failed listing blocks too: forced, a failed conflict listing
    passes and is recorded, a failed held listing still blocks. Take RC only warns.
    """

    def setUp(self):
        super().setUp()
        with open(os.path.join(self.cloud, "pyproject.toml"), "w") as fh:
            fh.write('unstract-platform-version = "ee-v1.7.0-rc.1"\n')
        self.g(self.cloud, "add", "pyproject.toml")
        self.g(self.cloud, "commit", "-q", "-m", "pin")
        self.g(self.cloud, "push", "-q", "origin", "main")

    def prs(self, slug, *bases):
        self.write(
            slug.replace("/", "_") + ".json",
            json.dumps(
                [
                    {
                        "number": 40 + i,
                        "url": f"https://x/{i}",
                        "baseRefName": b,
                        "createdAt": "2026-10-01T00:00:00Z",
                    }
                    for i, b in enumerate(bases)
                ]
            ),
        )

    def promote(self, rc="v1.7.0-rc.1", **env):
        return self.run_step(inline("promote.yaml", "Plan"), RC=rc, TARGET="cloud", **env)

    def blocked(self, r, msg):
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn(msg, r.stdout)
        self.assertFalse(os.path.exists(os.path.join(self.d, "output")))

    def forced(self, r):
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        return re.search(r"^forced=(.*)$", self.read("output"), re.M)[1]

    def test_promote_conflict_prs(self):
        self.line("1.7", "v1.7.0-rc.1")
        self.assertEqual(self.forced(self.promote()), "")
        self.prs("Zipstack/unstract-cloud", "release/1.6")  # another line's PR: no block
        self.prs(oss.OSS, "release/1.6")
        self.assertEqual(self.forced(self.promote()), "")
        self.prs("Zipstack/unstract-cloud", "release/1.7")
        self.blocked(
            self.promote(),
            "::error::Open backport conflict PR Zipstack/unstract-cloud#40 on release/1.7",
        )
        self.prs("Zipstack/unstract-cloud")
        self.prs(oss.OSS, "release/1.7")
        self.blocked(
            self.promote(),
            f"::error::Open backport conflict PR {oss.OSS}#40 on release/1.7",
        )
        self.assertIn(f"oss-token pr list -R {oss.OSS} ", self.read("gh.log"))
        self.assertIn(
            "cloud-token pr list -R Zipstack/unstract-cloud ", self.read("gh.log")
        )
        self.assertEqual(
            self.forced(self.promote(FORCE="true", REASON="ship it")),
            f"ship it; open conflict PRs: {oss.OSS}#40",
        )

    def test_promote_fails_closed(self):
        self.line("1.7", "v1.7.0-rc.1")
        self.write("prfail", "")
        self.blocked(self.promote(), "::error::cannot list open backport conflict PRs")
        self.assertEqual(
            self.forced(self.promote(FORCE="true", REASON="ship it")),
            "ship it; open conflict PRs: unchecked: listing failed",
        )

    def test_promote_held_fixes(self):
        self.line("1.7", "v1.7.0-rc.1", "v1.7.0")  # cloud GA: the line is stabilized
        self.g(
            self.cloud, "commit", "-q", "--allow-empty", "-m", "fix: y"
        )  # the next RC's commit
        self.g(self.cloud, "tag", "v1.7.1-rc.1")
        self.g(
            self.cloud,
            "push",
            "-q",
            "origin",
            "main:refs/heads/release/1.7",
            "v1.7.1-rc.1",
        )
        with open(os.path.join(self.d, "reg.jsonl"), "a") as fh:
            fh.write(
                '{"id": 9, "digest": "sha256:rc", "pushed_at": "2026-09-01T00:00:00Z", "tags": ["v1.7.1-rc.1"]}\n'
            )
        self.g(
            self.cloud, "commit", "-q", "--allow-empty", "-m", "fix: x (#9)"
        )  # on main only: held for 1.7
        self.g(self.cloud, "push", "-q", "origin", "main")
        self.write(
            "pulls.json",
            json.dumps(
                [{"number": 9, "title": "fix: x", "labels": [{"name": "fix/security"}]}]
            ),
        )
        r = self.promote("v1.7.1-rc.1")
        self.blocked(r, "::error::pending picks")
        self.assertRegex(
            r.stdout, r"::error::[0-9a-f]{7} \(security, PR #9\) held for release/1\.7"
        )
        self.assertNotIn(
            f"oss-token api repos/{oss.OSS}/", self.read("gh.log")
        )  # nothing on OSS main yet
        self.assertEqual(
            self.forced(self.promote("v1.7.1-rc.1", FORCE="true", REASON="next RC")),
            "next RC",
        )
        oss_work = self.repos["oss"][
            1
        ]  # a security fix on OSS main, not picked onto OSS release/1.7: held too
        self.g(oss_work, "pull", "-q", "origin", "main")
        self.g(oss_work, "commit", "-q", "--allow-empty", "-m", "fix: z (#9)")
        self.g(oss_work, "push", "-q", "origin", "main")
        self.g(oss_work, "fetch", "-q", "origin")
        r = self.promote("v1.7.1-rc.1")
        self.blocked(r, "::error::pending picks")
        self.assertIn(f"oss-token api repos/{oss.OSS}/commits/", self.read("gh.log"))
        self.assertEqual(
            len(
                re.findall(
                    r"::error::[0-9a-f]{7} \(security, PR #9\) held for release/1\.7",
                    r.stdout,
                )
            ),
            1,
        )
        self.assertRegex(
            r.stdout,
            rf"::error::[0-9a-f]{{7}} \(security, PR {re.escape(oss.OSS)}#9\) held for release/1\.7",
        )
        take = self.run_step(
            inline("take-rc-build.yaml", "Plan checks"),
            BRANCH="release/1.7",
            TARGETS="cloud",
        )  # Take RC lists the OSS-held fix too, and never blocks on it
        self.assertIn(
            f"Held for the RM on {oss.OSS} `release/1.7`",
            self.read("notes.md"),
            take.stdout + take.stderr,
        )
        self.assertIn(f"Held for the RM on {oss.OSS} `release/1.7`", self.read("summary"))
        self.assertIn(f"backport.yaml -R {oss.OSS} -f commits=#9", self.read("summary"))
        self.write(
            "pullsfail", ""
        )  # the held-fix listing fails: Take RC warns and goes on, Promote fails closed
        take = self.run_step(
            inline("take-rc-build.yaml", "Plan checks"),
            BRANCH="release/1.7",
            TARGETS="cloud",
        )
        self.assertEqual(take.returncode, 0, take.stdout + take.stderr)
        self.assertIn(
            "::warning::⚠ Could not list held fixes on Zipstack/unstract-cloud",
            take.stdout,
        )
        self.blocked(
            self.promote("v1.7.1-rc.1", FORCE="true", REASON="x"),
            "::error::cannot list held security/critical fixes",
        )
        self.assertIn("rerun Promote once GitHub answers", self.read("summary"))

    def test_take_rc_only_warns(self):
        self.line("1.7")
        self.prs(oss.OSS, "release/1.7")
        script = inline("take-rc-build.yaml", "Plan checks")
        self.g(self.cloud, "checkout", "-q", "-b", "release/1.7", "origin/release/1.7")
        r = self.run_step(script, BRANCH="release/1.7", TARGETS="cloud")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn(
            f"::warning::Open backport conflict PR {oss.OSS}#40 on release/1.7", r.stdout
        )
        self.assertIn(
            f"⚠ Open backport conflict PRs: [{oss.OSS}#40]", self.read("notes.md")
        )
        self.write("prfail", "")
        r = self.run_step(script, BRANCH="release/1.7", TARGETS="cloud")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("::warning::⚠ Could not list open backport conflict PRs", r.stdout)


class TakeRcVersion(Workflow):
    def test_allocates_past_a_registry_rc(self):
        # An earlier run pushed the cloud artifact of v1.7.0-rc.1, then its tag push failed and the tip moved.
        self.line("1.7")
        self.g(self.cloud, "checkout", "-q", "-b", "release/1.7", "origin/release/1.7")
        self.write(
            "reg.jsonl",
            '{"id": 1, "digest": "sha256:a", "pushed_at": "2026-09-01T00:00:00Z", "tags": ["v1.7.0-rc.1"]}\n',
        )
        r = self.run_step(
            inline("take-rc-build.yaml", "Plan version and targets"),
            BRANCH="release/1.7",
            TARGETS="cloud",
        )
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(
            self.read("output"), "tag=v1.7.0-rc.2\nbump=true\ntargets=cloud\n"
        )


class PublishWorkflow(Workflow):
    """Publish's Plan reads the OSS pins of the RC and the previous stable; its Changelog step runs the fetcher
    against this repo and the OSS repo with one token (the release bot's, which reads both).
    """

    def release(
        self, pin, *tags
    ):  # a main commit pinning pin (None: no pyproject.toml), tagged; tags in the registry
        path = os.path.join(self.cloud, "pyproject.toml")
        if pin:
            with open(path, "w") as fh:
                fh.write(f'unstract-platform-version = "{pin}"\n')
            self.g(self.cloud, "add", "pyproject.toml")
        elif os.path.exists(path):
            self.g(self.cloud, "rm", "-q", "pyproject.toml")
        self.g(self.cloud, "commit", "-q", "--allow-empty", "-m", f"pin {pin}")
        for t in tags:
            self.g(
                self.cloud,
                "tag",
                *(
                    ["-a", t, "-m", f"promote: {tags[0]} -> {t} (cloud)"]
                    if t != tags[0]
                    else [t]
                ),
            )
            with open(os.path.join(self.d, "reg.jsonl"), "a") as fh:
                fh.write(
                    f'{{"id": {len(t)}, "digest": "sha256:{t}", "pushed_at": "2026-09-01T00:00:00Z", "tags": ["{t}"]}}\n'
                )
        self.g(self.cloud, "push", "-q", "--tags", "origin", "main")

    def plan(self):
        r = self.run_step(
            inline("publish.yaml", "Plan"),
            VERSION="v1.7.0",
            TARGET="cloud",
            OWNER_REPO="Zipstack/unstract-cloud",
        )
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        return r.stdout, dict(
            line.split("=", 1) for line in self.read("output").splitlines()
        )

    def test_oss_range_is_the_two_pins(self):
        self.release("ee-v1.6.0", "v1.6.0")
        self.release("ee-v1.7.0-rc.1", "v1.7.0-rc.1", "v1.7.0")
        log, out = self.plan()
        self.assertEqual((out["prev_oss"], out["oss"]), ("ee-v1.6.0", "ee-v1.7.0-rc.1"))
        self.assertNotIn("::warning::no OSS pin", log)

    def test_a_side_with_no_pin_skips_oss(self):
        self.release(None, "v1.6.0")
        self.release("ee-v1.7.0-rc.1", "v1.7.0-rc.1", "v1.7.0")
        log, out = self.plan()
        self.assertIn("::warning::no OSS pin at v1.6.0: OSS changelog skipped", log)
        self.assertEqual(
            (out["prev_oss"], out["oss"]), ("ee-v1.7.0-rc.1", "ee-v1.7.0-rc.1")
        )  # same pin: skipped

    def test_changelog_reads_both_repos_with_one_token(self):
        # The real fetcher with a stand-in requests that logs each call and a main that calls it.
        action = os.path.join(self.cloud, ".github", "actions", "update-changelogs")
        os.makedirs(action)
        os.symlink(
            os.path.join(HERE, "..", "actions", "update-changelogs", "core"),
            os.path.join(action, "core"),
        )
        with open(os.path.join(action, "requests.py"), "w") as fh:
            fh.write(f"""class exceptions:
    RequestException = Exception
class R:
    def raise_for_status(self): pass
    def json(self): return {{"body": "notes"}}
def post(url, json, headers):
    with open({os.path.join(self.d, "calls")!r}, "a") as f:
        f.write(url.split("/repos/")[1].split("/releases")[0] + " " + headers["Authorization"] + "\\n")
    return R()
""")
        with open(os.path.join(action, "main.py"), "w") as fh:
            fh.write("""import sys, core.changelog_fetcher as cf
def main():
    print("argv", sys.argv[1:])
    f = cf.ChangelogFetcher("workflow-token")
    f._fetch_enterprise_changelog("v1.6.0", "v1.7.0-rc.1")
    f._fetch_oss_changelog("ee-v1.6.0", "ee-v1.7.0-rc.1")
    f._fetch_enterprise_changelog("v1.6.0", "v1.7.0-rc.1")
""")
        r = self.run_step(
            inline("publish.yaml", "Changelog"),
            VERSION="v1.7.0",
            RC="v1.7.0-rc.1",
            PREV="v1.6.0",
            OSS="ee-v1.7.0-rc.1",
            PREV_OSS="ee-v1.6.0",
            EXCLUDE="12,14",
        )
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn(
            "argv ['--release-version', 'v1.7.0', '--rc-tag', 'v1.7.0-rc.1', '--previous-stable', 'v1.6.0', "
            "'--current-oss', 'ee-v1.7.0-rc.1', '--previous-oss', 'ee-v1.6.0', '--exclude-prs', '12,14']",
            r.stdout,
        )
        self.assertEqual(
            self.read("calls").splitlines(),
            [
                "Zipstack/unstract-cloud token workflow-token",
                "Zipstack/unstract token workflow-token",
                "Zipstack/unstract-cloud token workflow-token",
            ],
        )


if __name__ == "__main__":
    unittest.main()
