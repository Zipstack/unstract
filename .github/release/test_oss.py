"""Tests for oss line work (cut, rc, promote, retire) on clones of a bare origin, and the workflows'
inline scripts. Run: python test_oss.py
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
    "Zipstack/unstract-cloud"  # pin relstate to the cloud config
)
import oss
import relmgr as rm

os.environ.update(GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_NOSYSTEM="1")
os.environ.pop("GITHUB_STEP_SUMMARY", None)


def dev_git(repo, *a):
    return rm.git(repo, "-c", "user.name=Dev", "-c", "user.email=dev@example.com", *a)


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
        dev_git(self.dev, "commit", "-q", "--allow-empty", "-m", "base")
        dev_git(
            self.dev, "tag", "v1.7.3"
        )  # a community release on main: never an OSS line's tag
        dev_git(self.dev, "push", "-q", "origin", "main", "v1.7.3")
        self.clone()
        self.gates = []
        self.gate = 0
        p = mock.patch.object(
            oss,
            "gate",
            lambda o, b, ref, annotate: (
                self.gates.append((b, ref, annotate)) or self.gate
            ),
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
            lambda *a: (
                self.listed.append(a)
                or [{"number": n, "baseRefName": b} for n, b in self.prs if b == a[1]]
            ),
        )
        p.start()
        self.addCleanup(p.stop)

    def clone(self):  # a fresh workflow run's OSS clone
        rm.git(
            os.path.dirname(self.oss),
            "clone",
            "-q",
            "--no-checkout",
            self.origin,
            self.oss,
        ) if not os.path.isdir(self.oss) else dev_git(
            self.oss, "fetch", "-q", "--prune", "--prune-tags", "--tags", "origin"
        )

    def remote(self, *args):
        return dev_git(self.origin, *args)

    def quiet(self, f, *args, **kw):
        with contextlib.redirect_stderr(io.StringIO()):
            return f(*args, **kw)

    def work(self, branch, msg):  # a developer's commit on the OSS line, pushed
        dev_git(self.dev, "fetch", "-q", "origin")
        dev_git(self.dev, "checkout", "-q", "-B", branch, f"origin/{branch}")
        dev_git(self.dev, "commit", "-q", "--allow-empty", "-m", msg)
        dev_git(self.dev, "push", "-q", "origin", branch)
        dev_git(self.dev, "checkout", "-q", "main")
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
        dev_git(self.dev, "push", "-q", "origin", "main:refs/heads/release/1.8")
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
        dev_git(self.cloud, "add", "pyproject.toml")
        dev_git(self.cloud, "commit", "-q", "-m", f"pin {tag}")
        dev_git(self.cloud, "tag", rc)

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

    def test_stabilized_promote_tags_the_line_once(self):
        # The OSS line stays stabilizing until its cloud line is GA on every enabled target: only --stabilized
        # writes the tag, once; a later promote keeps it on the GA commit.
        self.quiet(oss.cut, self.oss, "1.7")
        self.pin("ee-v1.7.0-rc.1", "v1.7.0-rc.1")
        # Cloud GA, on-prem still enabled.
        oss.promote(self.cloud, self.oss, "v1.7.0-rc.1")
        self.assertEqual(self.remote("tag", "-l", "stabilized/*"), "")
        self.clone()
        oss.promote(self.cloud, self.oss, "v1.7.0-rc.1", stabilized=True)
        ga = self.remote("rev-parse", "ee-v1.7.0^{commit}")
        self.assertEqual(self.remote("rev-parse", "stabilized/1.7^{commit}"), ga)
        self.work("release/1.7", "oss fix")
        self.quiet(oss.rc, self.oss, "release/1.7")
        self.pin("ee-v1.7.1-rc.1", "v1.7.1-rc.1")
        self.clone()
        self.assertEqual(
            oss.promote(self.cloud, self.oss, "v1.7.1-rc.1", stabilized=True), "ee-v1.7.1"
        )
        self.assertEqual(self.remote("rev-parse", "stabilized/1.7^{commit}"), ga)

    def test_reopen_deletes_the_stabilized_tag(self):
        # Cloud Take RC built a target with no GA: the OSS line is stabilizing again. No tag is a no-op.
        self.quiet(oss.cut, self.oss, "1.7")
        self.assertEqual(oss.reopen(self.oss, "release/1.7"), [])
        self.pin("ee-v1.7.0-rc.1", "v1.7.0-rc.1")
        oss.promote(self.cloud, self.oss, "v1.7.0-rc.1", stabilized=True)
        self.clone()
        self.assertEqual(
            oss.reopen(self.oss, "release/1.7"),
            [
                "- OSS `release/1.7`: deleted `stabilized/1.7`, stabilizing until Promote's last GA tags it again"
            ],
        )
        self.assertEqual(self.remote("tag", "-l", "stabilized/*"), "")
        self.assertEqual(self.remote("tag", "-l", "ee-v1.7.0"), "ee-v1.7.0")
        self.assertEqual(oss.reopen(self.oss, "release/1.7"), [])  # a rerun

    def test_cli_stabilized_flag(self):
        self.quiet(oss.cut, self.oss, "1.7")
        self.pin("ee-v1.7.0-rc.1", "v1.7.0-rc.1")
        self.addCleanup(os.chdir, os.getcwd())
        os.chdir(self.cloud)  # main promotes the cloud clone in the working directory
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = oss.main(
                ["--oss-repo", self.oss, "promote", "--rc", "v1.7.0-rc.1", "--stabilized"]
            )
        self.assertEqual((code, out.getvalue()), (0, "ee-v1.7.0\n"))
        self.assertEqual(
            self.remote("rev-parse", "stabilized/1.7^{commit}"),
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
        # a commit lands after this run fetched
        dev_git(self.dev, "fetch", "-q", "origin")
        dev_git(self.dev, "checkout", "-q", "-B", "release/1.7", "origin/release/1.7")
        dev_git(self.dev, "commit", "-q", "--allow-empty", "-m", "late fix")
        dev_git(self.dev, "push", "-q", "origin", "release/1.7")
        late = dev_git(self.dev, "rev-parse", "HEAD")
        dev_git(self.dev, "checkout", "-q", "main")
        with self.assertRaises(RuntimeError):
            oss.retire(self.oss, "release/1.7", "x", dry_run=False)
        self.assertEqual(self.remote("rev-parse", "release/1.7"), late)
        self.assertEqual(self.remote("tag", "-l", "ee-v1.7.*"), "ee-v1.7.0-rc.1")
        self.assertEqual(self.remote("tag", "-l", "retired/*"), "")
        self.assertEqual(
            dev_git(self.oss, "tag", "-l", "retired/*"), ""
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
            g = lambda *a: dev_git(d, *a)
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

    def test_gate_refuses_an_option_or_a_clone_outside(self):
        with tempfile.TemporaryDirectory() as d:
            with open(os.path.join(d, "convgate.py"), "w") as fh:
                fh.write("pass")
            for args in (
                ("/nonexistent/oss", "release/1.7", "ee-v1.7.0-rc.1"),
                (d, "-x", "ee-v1.7.0-rc.1"),
                (d, "release/1.7", "-x"),
            ):
                with (
                    self.subTest(args=args),
                    mock.patch.object(oss, "HERE", d),
                    self.assertRaises(ValueError),
                ):
                    oss.gate(*args, "error")

    def test_main_refuses_an_option_as_a_ref(self):
        with tempfile.TemporaryDirectory() as d:
            for cmd in (
                ["cut", "--line=-x"],
                ["rc", "--branch=-x"],
                ["promote", "--rc=-x"],
            ):
                with (
                    self.subTest(cmd=cmd),
                    contextlib.redirect_stderr(io.StringIO()),
                    self.assertRaises(SystemExit),
                ):
                    oss.main(["--oss-repo", d, *cmd])

    def test_main_reports_a_clone_outside(self):
        with contextlib.redirect_stderr(io.StringIO()) as err:
            code = oss.main(["--oss-repo", "/nonexistent/oss", "cut", "--line", "1.7"])
        self.assertEqual(code, 1)
        self.assertIn("::error::", err.getvalue())


HERE = os.path.dirname(os.path.abspath(__file__))


class TopicBranchHead(unittest.TestCase):
    """release-branch-only.yaml's head check: the bot never pushes to main, a release line or a backport head."""

    def test_head_ref(self):
        with open(
            os.path.join(HERE, "..", "workflows", "release-branch-only.yaml")
        ) as fh:
            wf = fh.read()
        body = wf[wf.index("run: |", wf.index("- name: Topic-branch head\n")) :].split(
            "\n"
        )[1:]
        script = "\n".join(line[10:] for line in body[: body.index("")])
        for head, code in (
            ("main", 1),
            ("release/1.7", 1),
            ("backport/1.7/abc1234", 1),
            ("feature/x", 0),
            ("x-main", 0),
        ):
            with self.subTest(head=head):
                r = subprocess.run(
                    ["bash", "-c", script],
                    env={"HEAD_REF": head, "PATH": os.environ["PATH"]},
                    capture_output=True,
                    text=True,
                )
                self.assertEqual(r.returncode, code, r.stdout)


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


def step(workflow, name, exprs=()):
    """The bash run block of a workflow step, each ${{ }} expression replaced from exprs ("" when absent)."""
    with open(os.path.join(HERE, "..", "workflows", workflow)) as fh:
        lines = fh.read().split("\n")
    i = next(
        n
        for n, line in enumerate(lines)
        if line.strip() in (f"- name: {name}", f"name: {name}")
    )
    i = next(n for n in range(i, len(lines)) if lines[n].strip() == "run: |")
    indent = len(lines[i]) - len(lines[i].lstrip()) + 2
    body = []
    for line in lines[i + 1 :]:
        if line.strip() and len(line) - len(line.lstrip()) < indent:
            break
        body.append(line[indent:])
    return re.sub(
        r"\$\{\{\s*(.*?)\s*\}\}",
        lambda m: dict(exprs).get(m.group(1), ""),
        "\n".join(body),
    )


@unittest.skipUnless(
    os.path.exists(os.path.join(HERE, "..", "workflows", "retire.yaml")),
    "the cloud repo's workflows",
)
class Workflow(unittest.TestCase):
    """Cloud and OSS origins with clones. sitecustomize serves Artifact Registry from reg.jsonl (cloud/backend)
    and reg-<kind>_<package>.jsonl; a stub gh serves <owner>_<repo>.json (conflict PRs; a `prfail` file fails it)
    and pulls.json, logging each call and its token to gh.log.
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
            dev_git(work, "commit", "-q", "--allow-empty", "-m", "base")
            dev_git(work, "push", "-q", "origin", "main")
            self.repos[name] = (origin, work)
        os.makedirs(os.path.join(self.cloud, ".relmgr", ".github"))
        os.symlink(HERE, os.path.join(self.cloud, ".relmgr", ".github", "release"))
        self.site = os.path.join(d, "site")
        os.mkdir(self.site)
        with open(os.path.join(self.site, "sitecustomize.py"), "w") as fh:
            fh.write(f"""import json, os, sys
sys.path.insert(0, {HERE!r})
import relstate
def _ar_versions(repo, package, artifact):  # reg.jsonl for cloud/backend, reg-<kind>_<package>.jsonl for the others; a row's "repo" (default r) is its repository, "names" its version ids' repository
    f = os.path.join({d!r}, "reg.jsonl" if artifact == "cloud/backend" else "reg-" + artifact.replace("/", "_") + ".jsonl")
    if not os.path.exists(f):
        return []
    with open(f) as fh:
        rows = [v for v in map(json.loads, fh) if v.get("repo", "r") == repo]
    return [{{"name": f"{{v.get('names', repo)}}/packages/backend/versions/{{v['digest']}}", "createTime": v["pushed_at"],
              "relatedTags": [{{"name": f"{{repo}}/packages/backend/tags/{{t}}"}} for t in v["tags"]]}} for v in rows]
relstate._ar_versions = _ar_versions
for kind in ("CLOUD", "ON_PREM", "CHART"):
    os.environ.setdefault("RELSTATE_AR_" + kind, "r")
import urllib.request
def _urlopen(req, timeout=None):  # a registry delete, logged to ar.log
    with open({os.path.join(d, "ar.log")!r}, "a") as fh:
        fh.write(f"{{req.get_method()}} {{req.full_url}}\\n")
    return open(os.devnull, "rb")
urllib.request.urlopen = _urlopen
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

    def line(
        self, x_y, *tags
    ):  # cloud and OSS release/X.Y; tags: cloud tags on the cloud tip, also in the registry
        dev_git(self.cloud, "push", "-q", "origin", f"main:refs/heads/release/{x_y}")
        for i, t in enumerate(tags):
            dev_git(self.cloud, "tag", t, "main")
            dev_git(self.cloud, "push", "-q", "origin", t)
            with open(os.path.join(self.d, "reg.jsonl"), "a") as fh:
                fh.write(
                    f'{{"id": {len(t) * 10 + i}, "digest": "sha256:{t}", "pushed_at": "2026-09-01T00:00:00Z", '
                    f'"tags": ["{t}"]}}\n'
                )
        with contextlib.redirect_stderr(io.StringIO()):
            oss.cut(self.repos["oss"][1], x_y)

    def run_step(self, script, **env):
        dev_git(self.cloud, "fetch", "-q", "--tags", "origin")
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

    def test_abandon_deletes_one_rc_and_keeps_the_last(self):
        self.line("1.7", "v1.7.0-rc.1", "v1.7.0-rc.2")
        self.retire(ABANDON="release/1.7", REASON="cut by mistake", RELSTATE_AR_TOKEN="t")
        self.assertRegex(
            self.read("ar.log"),
            r"^DELETE \S+/r/packages/backend/versions/sha256:v1\.7\.0-rc\.1\?force=true\n$",
        )

    def test_abandon_deletes_in_the_rc_repository(self):
        self.line("1.7")
        for i in (1, 2):  # RCs built after the split: only in the RC repository
            with open(os.path.join(self.d, "reg.jsonl"), "a") as fh:
                fh.write(
                    f'{{"repo": "rc", "digest": "sha256:rc{i}", "pushed_at": "2026-09-01T00:00:00Z", '
                    f'"tags": ["v1.7.0-rc.{i}"]}}\n'
                )
        self.retire(
            ABANDON="release/1.7",
            REASON="cut by mistake",
            RELSTATE_AR_TOKEN="t",
            RELSTATE_AR_CLOUD_RC="rc",
        )
        self.assertRegex(
            self.read("ar.log"),
            r"^DELETE \S+/rc/packages/backend/versions/sha256:rc1\?force=true\n$",
        )

    def test_abandon_refuses_a_version_outside_its_repositories(self):
        self.line("1.7")
        for i in (1, 2):  # read from repository r, but their ids name repository other
            with open(os.path.join(self.d, "reg.jsonl"), "a") as fh:
                fh.write(
                    f'{{"names": "other", "digest": "sha256:rc{i}", "pushed_at": "2026-09-01T00:00:00Z", '
                    f'"tags": ["v1.7.0-rc.{i}"]}}\n'
                )
        r = self.run_step(
            inline("retire.yaml", "Derive and retire"),
            ABANDON="release/1.7",
            REASON="cut by mistake",
            RETIRE_LINE="",
            NOW="",
            DRY_RUN="false",
            RELSTATE_AR_TOKEN="t",
        )
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn("other/packages/backend/versions/sha256:rc1 is outside r", r.stdout)
        self.assertFalse(os.path.exists(os.path.join(self.d, "ar.log")))

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
        dev_git(self.cloud, "commit", "-q", "--allow-empty", "-m", "late fix")
        dev_git(self.cloud, "push", "-q", "origin", f"HEAD:refs/heads/release/{x_y}")
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

    def lands_mid_run(self, x_y):
        """A push to release/x_y lands on origin after this run read its tip: origin's hook moves the branch on the
        run's first other push (an RC tag delete or the archive tag), before the branch delete.
        """
        origin = self.repos["cloud"][0]
        dev_git(self.cloud, "commit", "-q", "--allow-empty", "-m", "late fix")
        late = dev_git(self.cloud, "rev-parse", "HEAD")
        dev_git(self.cloud, "push", "-q", "origin", "HEAD:refs/keep/late")
        dev_git(self.cloud, "reset", "-q", "--hard", "HEAD~1")
        hook = os.path.join(origin, "hooks", "post-receive")
        with open(hook, "w") as fh:
            fh.write(
                f"#!/bin/sh\ngrep -q refs/heads/ || git update-ref refs/heads/release/{x_y} {late}\n"
            )
        os.chmod(hook, 0o755)
        return late

    def kept(self, x_y, late, **env):
        r = self.run_step(
            inline("retire.yaml", "Derive and retire"),
            **{"ABANDON": "", "RETIRE_LINE": "", "NOW": "", "DRY_RUN": "false", **env},
        )
        self.assertNotEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(
            rm.git(self.repos["cloud"][0], "rev-parse", f"release/{x_y}"), late
        )

    def test_abandon_keeps_a_branch_pushed_after_its_tip_was_read(self):
        # Its RC tag delete is the push the hook waits for.
        self.line("1.7", "v1.7.0-rc.1")
        self.kept(
            "1.7",
            self.lands_mid_run("1.7"),
            ABANDON="release/1.7",
            REASON="cut by mistake",
        )

    def test_retire_line_keeps_a_branch_pushed_after_its_tip_was_read(self):
        self.line("1.7")
        self.kept(
            "1.7",
            self.lands_mid_run("1.7"),
            RETIRE_LINE="release/1.7",
            REASON="not shipping",
        )

    def test_derived_list_keeps_a_branch_pushed_after_its_tip_was_read(self):
        self.line("1.6", "v1.6.0-rc.1", "v1.6.0")
        self.line("1.7", "v1.7.0-rc.1", "v1.7.0")
        self.kept("1.6", self.lands_mid_run("1.6"))

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


@unittest.skipUnless(
    os.path.exists(os.path.join(HERE, "..", "workflows", "sync-argocd.yaml")),
    "the cloud repo's workflows",
)
class SyncArgocdParameters(unittest.TestCase):
    """The helm.parameters sync-argocd writes back: its own keys replaced, every other parameter on the app kept."""

    OTHER = {
        "name": "postgresql.enabled",
        "value": "false",
    }  # a chart value this workflow does not own
    REG = "l-docker.pkg.dev/p/rc"

    def merge(self, current, tag="", cloud_rc="", revision="main"):
        return subprocess.run(
            [
                sys.executable,
                "-c",
                inline("sync-argocd.yaml", "Update ArgoCD Application"),
            ],
            env={
                **os.environ,
                "CURRENT": json.dumps(current),
                "IMAGE_TAG": tag,
                "CLOUD_RC": cloud_rc,
                "TARGET_REVISION": revision,
                "APP_NAME": "dev-unstract-dev",
            },
            capture_output=True,
            text=True,
        )

    def merged(self, current, *args, **kwargs):
        r = self.merge(current, *args, **kwargs)
        self.assertEqual(r.returncode, 0, r.stderr)
        params = json.loads(r.stdout)
        self.assertEqual(
            len(params), len({p["name"] for p in params}), params
        )  # each name once
        return {p["name"]: p["value"] for p in params}

    def test_rc_sync_adds_the_registries(self):
        got = self.merged(
            [self.OTHER, {"name": "global.unstract.image.tag", "value": "v1"}],
            "v2.0.0-rc.1",
            self.REG,
        )
        self.assertEqual(got["postgresql.enabled"], "false")
        self.assertEqual(got["global.unstract.image.tag"], "v2.0.0-rc.1")
        self.assertEqual(got["backend.image.registry"], self.REG)
        self.assertEqual(
            got["runner.configMap.TOOL_SIDECAR_IMAGE_NAME"], f"{self.REG}/tool-sidecar"
        )
        self.assertEqual(got["runner.configMap.TOOL_SIDECAR_IMAGE_TAG"], "v2.0.0-rc.1")

    def test_non_rc_sync_drops_the_registries(self):
        rc = [
            {"name": n, "value": v}
            for n, v in self.merged([self.OTHER], "v2.0.0-rc.1", self.REG).items()
        ]
        self.assertEqual(
            self.merged(rc, "v2", self.REG),
            {"postgresql.enabled": "false", "global.unstract.image.tag": "v2"},
        )

    def test_no_tag_keeps_the_current_one(self):
        self.assertEqual(
            self.merged(
                [self.OTHER, {"name": "global.unstract.image.tag", "value": "v1"}]
            ),
            {"postgresql.enabled": "false", "global.unstract.image.tag": "v1"},
        )

    def test_a_kept_rc_tag_pulls_from_cloud_rc(self):
        # a re-sync with no tag keeps the app's RC tag, and rewrites its registries to the RC repository
        tag = {"name": "global.unstract.image.tag", "value": "v2.0.0-rc.1"}
        stable = "us-central1-docker.pkg.dev/p/unstract"
        got = self.merged(
            [self.OTHER, tag, {"name": "backend.image.registry", "value": stable}],
            cloud_rc=self.REG,
        )
        self.assertEqual(got["global.unstract.image.tag"], "v2.0.0-rc.1")
        self.assertEqual(got["backend.image.registry"], self.REG)
        self.assertEqual(got["frontend.image.registry"], self.REG)
        self.assertEqual(got["runner.configMap.TOOL_SIDECAR_IMAGE_TAG"], "v2.0.0-rc.1")

    def test_an_rc_revision_pulls_from_cloud_rc(self):
        # no tag anywhere: the chart's own tag at an RC revision is that RC
        got = self.merged([self.OTHER], cloud_rc=self.REG, revision="v1.1.0-rc.2")
        self.assertEqual(got["backend.image.registry"], self.REG)
        self.assertNotIn("global.unstract.image.tag", got)
        self.assertNotIn("runner.configMap.TOOL_SIDECAR_IMAGE_TAG", got)

    def test_an_rc_tag_without_cloud_rc_fails(self):
        tag = {"name": "global.unstract.image.tag", "value": "v2.0.0-rc.1"}
        for current, kwargs in (
            ([self.OTHER], {"tag": "v2.0.0-rc.1"}),
            ([self.OTHER, tag], {}),
            ([self.OTHER], {"revision": "v1.1.0-rc.2"}),
        ):
            r = self.merge(current, **kwargs)
            self.assertEqual(r.returncode, 1, kwargs)
            self.assertIn("RELSTATE_AR_CLOUD_RC, which is unset", r.stderr, kwargs)
            self.assertEqual(r.stdout, "", kwargs)

    def test_the_sidecar_tag_follows_a_tag_parameter(self):
        # no tag parameter: the chart's tag and sidecar tag are the same anchor
        got = self.merged(
            [
                self.OTHER,
                {"name": "runner.configMap.TOOL_SIDECAR_IMAGE_TAG", "value": "x"},
            ],
            cloud_rc=self.REG,
            revision="v1.1.0-rc.2",
        )
        self.assertNotIn("runner.configMap.TOOL_SIDECAR_IMAGE_TAG", got)
        self.assertEqual(
            self.merged([self.OTHER], "snapshot.7"),
            {"postgresql.enabled": "false", "global.unstract.image.tag": "snapshot.7"},
        )

    def test_cloud_rc_is_not_taken_without_an_rc_tag(self):
        for tag in ("snapshot.7", "v2.0.0", "rc.3"):
            for cloud_rc in (self.REG, ""):
                self.assertEqual(
                    self.merged([self.OTHER], tag, cloud_rc),
                    {"postgresql.enabled": "false", "global.unstract.image.tag": tag},
                )


RC = "projects/p/locations/l/repositories/rc"
RC_HOST = "l-docker.pkg.dev/p/rc"


@unittest.skipUnless(
    os.path.exists(os.path.join(HERE, "..", "workflows", "build-push.yaml")),
    "the cloud repo's workflows",
)
class GuardSteps(unittest.TestCase):
    """Workflow steps run as bash from the workflow files: the input guards of build-push and dev-deploy, sync-argocd's
    update step, retag's copy and the build workflows' image roots. Stubs: curl (the GET answers get.json with the
    HTTP code in code, the PATCH body lands in patch.json); crane (img/<image> holds an image's digest, a missing one
    prints crane_err and fails, each copy is logged to copies, drift makes a copy land at another digest); docker
    (login; buildx imagetools inspect and create over the same img/ and copies, inspect_err failing every inspect,
    img/<image>.json the image config that --format '{{json .Image}}' prints).
    """

    APP = {
        "spec": {
            "source": {
                "helm": {"parameters": [{"name": "postgresql.enabled", "value": "false"}]}
            }
        }
    }

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.d = d = tmp.name
        with open(os.path.join(d, "curl"), "w") as fh:
            fh.write(f"""#!/bin/sh
case "$*" in
  *"-X PATCH"*) cat > {d}/patch.json; printf '{{}}\\n200';;
  *) cat {d}/get.json; printf '\\n%s' "$(cat {d}/code)";;
esac
""")
        os.chmod(os.path.join(d, "curl"), 0o755)
        os.mkdir(os.path.join(d, "img"))
        with open(os.path.join(d, "crane"), "w") as fh:
            fh.write(f"""#!/bin/sh
img() {{ echo "{d}/img/$(echo "$1" | tr '/:' '__')"; }}
case "$1" in
  auth) cat > /dev/null;;
  digest) [ -e "$(img "$2")" ] || {{ cat {d}/crane_err; exit 1; }}; cat "$(img "$2")";;
  copy) echo "$2 $3" >> {d}/copies; cp "$(img "$2")" "$(img "$3")"; [ ! -e {d}/drift ] || echo sha256:other > "$(img "$3")";;
esac
""")
        with open(os.path.join(d, "docker"), "w") as fh:
            fh.write(f"""#!/bin/sh
img() {{ echo "{d}/img/$(echo "$1" | tr '/:' '__')"; }}
case "$1 $2 $3" in
  "buildx imagetools inspect")
    [ ! -e {d}/inspect_err ] || {{ cat {d}/inspect_err; exit 1; }}
    [ -e "$(img "${{4%@*}}")" ] || {{ echo "ERROR: $4: not found"; exit 1; }}
    if [ "$6" = '{{{{json .Image}}}}' ]; then cat "$(img "${{4%@*}}").json"; else cat "$(img "$4")"; fi;;
  "buildx imagetools create") echo "$6 $5" >> {d}/copies; cp "$(img "${{6%@*}}")" "$(img "$5")"
    cp "$(img "${{6%@*}}").json" "$(img "$5").json"
    [ ! -e {d}/drift ] || echo sha256:other > "$(img "$5")";;
  *) cat > /dev/null;;
esac
""")
        for tool in ("crane", "docker"):
            os.chmod(os.path.join(d, tool), 0o755)

    def bash(self, script, **env):
        return subprocess.run(
            ["bash", "-eo", "pipefail", "-c", script],
            env={
                "PATH": f"{self.d}:{os.environ['PATH']}",
                # setup-python's interpreter loads libpython from here
                **{k: v for k, v in os.environ.items() if k == "LD_LIBRARY_PATH"},
                "GITHUB_OUTPUT": os.path.join(self.d, "out"),
                "GITHUB_STEP_SUMMARY": os.path.join(self.d, "summary"),
                "GITHUB_ENV": os.path.join(self.d, "env"),
                **env,
            },
            capture_output=True,
            text=True,
        )

    def build_push(self, tag, **env):
        script = step(
            "build-push.yaml",
            "Assert tags when manual",
            {"github.event.inputs.tag || inputs.tag": tag},
        )
        return self.bash(
            script,
            **{
                "BUILD_FROM_TAG": "false",
                "BUILDS": "true",
                "RC_REPOS": "projects/p/locations/l/repositories/rc",
                **env,
            },
        )

    def test_build_push_refuses_an_rc_tag_built_outside_build_from_tag(self):
        r = self.build_push("v1.2.0-rc.1")
        self.assertEqual(r.returncode, 1, r.stdout)
        self.assertIn("release-line RC tag", r.stdout)

    def test_build_push_passes_an_rc_tag_otherwise(self):
        for env in ({"BUILD_FROM_TAG": "true"}, {"BUILDS": "false"}, {"RC_REPOS": ""}):
            r = self.build_push("v1.2.0-rc.1", **env)
            self.assertEqual(r.returncode, 0, (env, r.stdout))
        for tag in ("snapshot.7", "v1.2.0", "rc.4"):
            self.assertEqual(self.build_push(tag).returncode, 0, tag)

    def test_dev_deploy_refuses_frontend_dev_for_an_rc_tag(self):
        guard = step("dev-deploy.yaml", "Refuse frontend-dev for an RC tag")
        env = {"TAG": "v1.2.0-rc.1", "FRONTEND_DEV": "true", "CLOUD_RC": RC}
        r = self.bash(guard, **env)
        self.assertEqual(r.returncode, 1, r.stdout)
        for change in ({"TAG": "auto"}, {"FRONTEND_DEV": "false"}, {"CLOUD_RC": ""}):
            self.assertEqual(self.bash(guard, **{**env, **change}).returncode, 0, change)

    def sync(self, app, code=200, **env):
        with open(os.path.join(self.d, "get.json"), "w") as fh:
            fh.write(app if isinstance(app, str) else json.dumps(app))
        with open(os.path.join(self.d, "code"), "w") as fh:
            fh.write(str(code))
        r = self.bash(
            step("sync-argocd.yaml", "Update ArgoCD Application"),
            **{
                "APP_NAME": "dev-unstract-dev",
                "TARGET_REVISION": "main",
                "IMAGE_TAG": "",
                "CLOUD_RC": "",
                "TRIGGERED_BY": "dev",
                "ARGOCD_SERVER": "argocd",
                "ARGOCD_TOKEN": "t",
                **env,
            },
        )
        patch = os.path.join(self.d, "patch.json")
        if not os.path.exists(patch):
            return r, None
        with open(patch) as fh:
            params = json.loads(json.load(fh)["patch"])["spec"]["source"]["helm"][
                "parameters"
            ]
        os.remove(patch)
        return r, {p["name"]: p["value"] for p in params}

    def test_sync_refuses_a_read_with_no_spec_source(self):
        for body in (
            '{"error": "permission denied"}',
            '{"spec": {}}',
            "<html>login</html>",
            "",
        ):
            r, params = self.sync(body)
            self.assertEqual(r.returncode, 1, (body, r.stdout))
            self.assertIn(
                "returned no .spec.source", r.stdout, body
            )  # named, not a traceback
            self.assertIsNone(params, body)
        r, params = self.sync(self.APP, code=403)
        self.assertEqual((r.returncode, params), (1, None))

    def test_sync_of_an_app_with_no_parameters(self):
        r, params = self.sync({"spec": {"source": {}}}, IMAGE_TAG="snapshot.7")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(params, {"global.unstract.image.tag": "snapshot.7"})

    def test_sync_keeps_an_unrelated_parameter_and_takes_cloud_rc(self):
        r, params = self.sync(self.APP, IMAGE_TAG="v1.2.0-rc.1", CLOUD_RC=RC)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(params["postgresql.enabled"], "false")
        self.assertEqual(params["backend.image.registry"], RC_HOST)
        with open(os.path.join(self.d, "env")) as fh:
            self.assertIn(f"IMAGE_REGISTRY_APPLIED={RC_HOST}", fh.read())
        r, params = self.sync(self.APP, IMAGE_TAG="snapshot.7", CLOUD_RC=RC)
        self.assertEqual(
            params,
            {"postgresql.enabled": "false", "global.unstract.image.tag": "snapshot.7"},
        )

    def app(self, revision="", **params):
        return {
            "spec": {
                "source": {
                    "targetRevision": revision,
                    "helm": {
                        "parameters": [{"name": n, "value": v} for n, v in params.items()]
                    },
                }
            }
        }

    def test_resync_of_an_rc_pulls_from_cloud_rc(self):
        stable = "us-central1-docker.pkg.dev/p/unstract"
        regs = {
            f"{s}.image.registry": stable
            for s in ("frontend", "backend", "runner", "platform", "x2text", "worker")
        }
        regs["runner.configMap.TOOL_SIDECAR_IMAGE_NAME"] = f"{stable}/tool-sidecar"
        rc_regs = {k: RC_HOST for k in regs if k.endswith("registry")}
        rc_regs["runner.configMap.TOOL_SIDECAR_IMAGE_NAME"] = f"{RC_HOST}/tool-sidecar"
        # a dev namespace on an RC tag, re-synced with no tag on any branch: its registries become the RC repository
        app = self.app("main", **{"global.unstract.image.tag": "v1.1.0-rc.2", **regs})
        for revision in ("main", "feature/x"):
            r, params = self.sync(app, TARGET_REVISION=revision, CLOUD_RC=RC)
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            self.assertEqual(
                params,
                {
                    "global.unstract.image.tag": "v1.1.0-rc.2",
                    "runner.configMap.TOOL_SIDECAR_IMAGE_TAG": "v1.1.0-rc.2",
                    **rc_regs,
                },
            )
        # an app after a take-rc-build sync: registries and no tag parameter, the chart at the RC git tag
        for current in (
            self.app("v1.2.0-rc.1", **rc_regs),
            self.app("v1.1.0-rc.2", **regs),
        ):
            r, params = self.sync(
                current,
                APP_NAME="a-unstract-dev",
                TARGET_REVISION="v1.2.0-rc.1",
                CLOUD_RC=RC,
            )
            self.assertEqual(params, rc_regs)

    def test_an_rc_sync_without_cloud_rc_fails(self):
        for app, env in (
            (self.APP, {"IMAGE_TAG": "v1.2.0-rc.1"}),
            (self.APP, {"TARGET_REVISION": "v1.2.0-rc.1"}),
            (self.app("main", **{"global.unstract.image.tag": "v1.1.0-rc.2"}), {}),
        ):
            r, params = self.sync(app, **env)
            self.assertEqual((r.returncode, params), (1, None), env)
            self.assertIn("RELSTATE_AR_CLOUD_RC, which is unset", r.stderr, env)
        # a non-RC sync drops RC registries an app still has, with the variable unset
        r, params = self.sync(
            self.app("v1.2.0-rc.1", **{"backend.image.registry": RC_HOST}),
            TARGET_REVISION="v1.3.0",
        )
        self.assertEqual((r.returncode, params), (0, {}))

    def test_rc_target_revision_with_no_tag_takes_cloud_rc(self):
        _, params = self.sync(self.APP, TARGET_REVISION="v1.2.0-rc.1", CLOUD_RC=RC)
        self.assertEqual(params["backend.image.registry"], RC_HOST)
        _, params = self.sync(self.APP, TARGET_REVISION="feature/x", CLOUD_RC=RC)
        self.assertEqual(params, {"postgresql.enabled": "false"})

    def test_sync_refuses_a_malformed_repository(self):
        # a newline would add a line to GITHUB_ENV
        for bad in ("bogus", "projects/p\nX=1/locations/l/repositories/r"):
            for tag in ("v1.2.0-rc.1", "snapshot.7"):
                r, params = self.sync(self.APP, IMAGE_TAG=tag, CLOUD_RC=bad)
                self.assertEqual((r.returncode, params), (1, None), (bad, tag))
                self.assertIn("Not an AR repository", r.stderr, bad)

    STABLE = "us-central1-docker.pkg.dev/p/unstract"

    def retag(self, images, err="", drift=False, rc_repo=RC, source="v1.2.0-rc.1"):
        for image, digest in images.items():
            with open(
                os.path.join(self.d, "img", image.replace("/", "_").replace(":", "_")),
                "w",
            ) as fh:
                fh.write(digest)
        with open(os.path.join(self.d, "crane_err"), "w") as fh:
            fh.write(err)
        if drift:
            open(os.path.join(self.d, "drift"), "w").close()
        r = self.bash(
            step("retag-docker-images.yaml", "Retag ${{ matrix.service }} image"),
            PROJECT_ID="p",
            SOURCE_TAG=source,
            TARGET_TAG="v1.2.0",
            SERVICE="backend",
            RC_REPO=rc_repo,
            TOKEN="t",
        )
        copies = os.path.join(self.d, "copies")
        with open(copies) if os.path.exists(copies) else io.StringIO() as fh:
            return r, fh.read().split("\n")[0]

    def test_retag_copies_the_rc_repository_image(self):
        r, copy = self.retag(
            {
                f"{RC_HOST}/backend:v1.2.0-rc.1": "sha256:rc",
                f"{self.STABLE}/backend:v1.2.0-rc.1": "sha256:old",
            }
        )
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(
            copy, f"{RC_HOST}/backend:v1.2.0-rc.1 {self.STABLE}/backend:v1.2.0"
        )

    def test_retag_reads_a_release_line_rc_only_from_its_rc_repository(self):
        stable = {f"{self.STABLE}/backend:v1.2.0-rc.1": "sha256:old"}
        for rc_repo in ("", "bogus", "projects/p/locations/l/repositories/r/x"):
            r, copy = self.retag(stable, rc_repo=rc_repo)
            self.assertEqual((r.returncode, copy), (1, ""), rc_repo)
            self.assertIn("is a release-line RC", r.stdout, rc_repo)
        for source in ("rc.4", "snapshot.7"):
            r, copy = self.retag(
                {f"{self.STABLE}/backend:{source}": "sha256:s"}, source=source
            )
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            self.assertEqual(
                copy, f"{self.STABLE}/backend:{source} {self.STABLE}/backend:v1.2.0"
            )
            os.remove(os.path.join(self.d, "copies"))

    def test_retag_refuses_a_copy_at_another_digest(self):
        r, _ = self.retag({f"{RC_HOST}/backend:v1.2.0-rc.1": "sha256:rc"}, drift=True)
        self.assertEqual(r.returncode, 1)
        self.assertIn("not the RC's sha256:rc", r.stdout)

    def test_image_roots(self):
        roots = step("cloud-backend-docker-build-push.yaml", "Image roots")
        env = {"PROJECT_ID": "p", "TOKEN": "t", "ON_PREM_RC": ""}
        r = self.bash(roots, CLOUD_RC=RC, **env)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        r = self.bash(roots, CLOUD_RC="", **env)
        with open(os.path.join(self.d, "env")) as fh:
            self.assertEqual(
                fh.read().split("\n")[:4],
                [
                    f"IMAGE_ROOT_CLOUD={RC_HOST}",
                    f"IMAGE_ROOT_ON_PREM={self.STABLE}-on-prem",
                    f"IMAGE_ROOT_CLOUD={self.STABLE}",
                    f"IMAGE_ROOT_ON_PREM={self.STABLE}-on-prem",
                ],
            )
        r = self.bash(roots, CLOUD_RC="bogus", **env)
        self.assertEqual(r.returncode, 1)

    LABELLED = '{"config": {"Labels": {"org.opencontainers.image.revision": "r1"}}, "rootfs": {}}'

    def skip(self, images, tag="v1.2.0-rc.1", err="", drift=False, config=LABELLED):
        """Run the runner's Skip at commit r1 over images (ref -> digest, or ref -> (digest, config))."""
        for image, digest in images.items():
            digest, cfg = digest if isinstance(digest, tuple) else (digest, config)
            path = os.path.join(self.d, "img", image.replace("/", "_").replace(":", "_"))
            with open(path, "w") as fh:
                fh.write(digest)
            with open(path + ".json", "w") as fh:
                fh.write(cfg)
        git = os.path.join(self.d, "git")
        os.makedirs(git, exist_ok=True)
        with open(os.path.join(git, "git"), "w") as fh:
            fh.write('#!/bin/sh\n[ "$*" = "rev-parse HEAD" ] && echo r1\n')
        os.chmod(os.path.join(git, "git"), 0o755)
        if err:
            with open(os.path.join(self.d, "inspect_err"), "w") as fh:
                fh.write(err)
        if drift:
            open(os.path.join(self.d, "drift"), "w").close()
        r = self.bash(
            step("cloud-runner-docker-build-push.yaml", "Skip if already pushed"),
            TAG=tag,
            IMAGES="c/runner o/runner",
            PATH=f"{git}:{self.d}:{os.environ['PATH']}",
        )
        out = {}
        for name in ("out", "copies"):
            path = os.path.join(self.d, name)
            with open(path) if os.path.exists(path) else io.StringIO() as fh:
                out[name] = fh.read()
        return r, out["out"], out["copies"]

    def test_skip_when_every_root_has_the_rc(self):
        r, out, copies = self.skip(
            {"c/runner:v1.2.0-rc.1": "sha256:a", "o/runner:v1.2.0-rc.1": "sha256:a"}
        )
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual((out, copies), ("revision=r1\nskip=true\n", ""))

    def test_build_when_no_root_has_the_rc(self):
        r, out, copies = self.skip({})
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual((out, copies), ("revision=r1\n", ""))
        self.assertIn("not pushed yet", r.stdout)

    def test_copy_the_rc_to_a_root_that_lacks_it(self):
        r, out, copies = self.skip({"o/runner:v1.2.0-rc.1": "sha256:a"})
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(out, "revision=r1\nskip=true\n")
        self.assertEqual(copies, "o/runner:v1.2.0-rc.1@sha256:a c/runner:v1.2.0-rc.1\n")
        with open(os.path.join(self.d, "img", "c_runner_v1.2.0-rc.1")) as fh:
            self.assertEqual(fh.read().strip(), "sha256:a")

    def test_copy_refuses_another_digest(self):
        r, out, _ = self.skip({"c/runner:v1.2.0-rc.1": "sha256:a"}, drift=True)
        self.assertEqual(r.returncode, 1)
        self.assertEqual(out, "revision=r1\n")
        self.assertIn("landed at sha256:other, not sha256:a", r.stdout)

    def test_skip_fails_when_a_root_cannot_be_read(self):
        r, out, _ = self.skip({}, err="ERROR: unauthorized")
        self.assertEqual(r.returncode, 1)
        self.assertEqual(out, "revision=r1\n")
        self.assertIn(
            "cannot inspect c/runner:v1.2.0-rc.1: ERROR: unauthorized", r.stdout
        )

    def test_skip_leaves_other_tags_alone(self):
        for tag in ("rc.12", "v1.2.0", "v1.2.0-rc.1-snapshot", "dev-abc"):
            self.setUp()
            r, out, _ = self.skip(
                {f"c/runner:{tag}": "sha256:a", f"o/runner:{tag}": "sha256:a"}, tag=tag
            )
            self.assertEqual((r.returncode, out), (0, "revision=r1\n"), tag)

    def test_skip_refuses_an_image_of_another_commit(self):
        other = self.LABELLED.replace("r1", "r0")
        for images in (
            {"c/runner:v1.2.0-rc.1": ("sha256:a", other)},
            {
                "c/runner:v1.2.0-rc.1": "sha256:a",
                "o/runner:v1.2.0-rc.1": ("sha256:a", other),
            },
        ):
            with self.subTest(images=images):
                self.setUp()
                r, out, copies = self.skip(images)
                self.assertEqual(r.returncode, 1)
                self.assertEqual((out, copies), ("revision=r1\n", ""))
                self.assertIn(
                    "was built from r0, not r1: the tag was used before", r.stdout
                )

    def test_skip_refuses_an_unlabelled_image(self):
        r, out, copies = self.skip(
            {"c/runner:v1.2.0-rc.1": "sha256:a"}, config='{"config": {}, "rootfs": {}}'
        )
        self.assertEqual(r.returncode, 1)
        self.assertEqual((out, copies), ("revision=r1\n", ""))
        self.assertIn("was built from an unlabelled commit, not r1", r.stdout)

    def test_skip_reads_the_label_of_every_platform(self):
        def per_platform(*revs):
            return json.dumps(
                {
                    f"linux/p{n}": {
                        "config": {"Labels": {"org.opencontainers.image.revision": rev}}
                    }
                    for n, rev in enumerate(revs)
                }
            )

        r, out, _ = self.skip(
            {"c/runner:v1.2.0-rc.1": "sha256:a"}, config=per_platform("r1", "r1")
        )
        self.assertEqual(
            (r.returncode, out), (0, "revision=r1\nskip=true\n"), r.stdout + r.stderr
        )
        self.setUp()
        r, out, _ = self.skip(
            {"c/runner:v1.2.0-rc.1": "sha256:a"}, config=per_platform("r1", "r0")
        )
        self.assertEqual(r.returncode, 1)
        self.assertIn("was built from r0 r1, not r1", r.stdout)

    def test_skip_if_already_pushed_is_the_same_in_every_build_workflow(self):
        # the same script before every bake, gated on a release build, its images the ones the bake tags
        files = sorted(
            f
            for f in os.listdir(os.path.join(HERE, "..", "workflows"))
            if f.endswith("-docker-build-push.yaml")
            and f != "cloud-multi-doc-service-docker-build-push.yaml"
        )
        self.assertEqual(len(files), 11)
        want = step("cloud-backend-docker-build-push.yaml", "Skip if already pushed")
        for f in files:
            self.assertEqual(step(f, "Skip if already pushed"), want, f)
            with open(os.path.join(HERE, "..", "workflows", f)) as fh:
                text = fh.read()
            at = text.index("- name: Skip if already pushed")
            block = text[at : text.index("run: |", at)]
            self.assertIn("id: pushed\n", block, f)
            self.assertIn("if: inputs.event == 'release'\n", block, f)
            images = re.search(r"IMAGES: (.*)", block).group(1)
            tags = re.findall(r"tags=(\$\{\{ env\.IMAGE_ROOT_\w+ \}\}/[\w-]+):", text)
            self.assertEqual(images, " ".join(tags), f)
            # the bake labels its images with the commit the step compares
            self.assertEqual(
                re.findall(
                    r"\n +(\*|\w+)\.labels\.org\.opencontainers\.image\.revision=(.*)\n",
                    text,
                ),
                [
                    (
                        re.search(r"\n +(\*|\w+)\.tags=", text).group(1),
                        "${{ steps.pushed.outputs.revision || github.sha }}",
                    )
                ],
                f,
            )
            bake = text.index("uses: docker/bake-action@v7")
            self.assertLess(at, bake, f)
            self.assertEqual(text.count("uses: docker/bake-action@v7"), 1, f)
            self.assertEqual(
                text[:bake].rstrip().split("\n")[-1].strip(),
                "if: steps.pushed.outputs.skip != 'true'",
                f,
            )

    def test_image_roots_is_the_same_in_every_build_workflow(self):
        # on-prem-backend logs in with the credential helper instead of the token (a long compile outlives it)
        def roots(f):
            return [
                line
                for line in step(f, "Image roots").split("\n")
                if not re.search(r"docker login|configure-docker|credential helper", line)
            ]

        files = sorted(
            f
            for f in os.listdir(os.path.join(HERE, "..", "workflows"))
            # multi-doc-service is not built by build-push, so it has no RC image
            if f.endswith("-docker-build-push.yaml")
            and f != "cloud-multi-doc-service-docker-build-push.yaml"
        )

        def env(
            f,
        ):  # the step's RC repository env lines, which gate them on a release build
            with open(os.path.join(HERE, "..", "workflows", f)) as fh:
                text = fh.read()
            block = text[
                text.index("- name: Image roots") : text.index(
                    "run: |", text.index("- name: Image roots")
                )
            ]
            return [line.strip() for line in block.split("\n") if "_RC:" in line]

        self.assertEqual(len(files), 11)
        self.assertEqual(len(env("cloud-backend-docker-build-push.yaml")), 2)
        for f in files:
            self.assertEqual(roots(f), roots("cloud-backend-docker-build-push.yaml"), f)
            self.assertEqual(env(f), env("cloud-backend-docker-build-push.yaml"), f)
            with open(os.path.join(HERE, "..", "workflows", f)) as fh:
                text = fh.read()
            tags = re.findall(r"tags=\$\{\{ env\.(IMAGE_ROOT_\w+) \}\}", text)
            self.assertEqual(len(tags), text.count("tags="), f)  # no tag outside a root
            # a cloud build pushes its cloud image, and some also their on-prem one; an on-prem build only that
            want = (
                [["IMAGE_ROOT_CLOUD"], ["IMAGE_ROOT_CLOUD", "IMAGE_ROOT_ON_PREM"]]
                if f.startswith("cloud-")
                else [["IMAGE_ROOT_ON_PREM"]]
            )
            self.assertIn(tags, want, f)

    def test_on_prem_retag_is_the_cloud_retag(self):
        # both jobs' steps share a name, so step() runs the cloud one; the on-prem one differs only in its stable root
        # and RC repository variable
        def body(n):
            with open(
                os.path.join(HERE, "..", "workflows", "retag-docker-images.yaml")
            ) as fh:
                text = fh.read()
            at = [
                m.start()
                for m in re.finditer(
                    r"- name: Retag \$\{\{ matrix\.service \}\} image", text
                )
            ]
            self.assertEqual(len(at), 2)
            return text[
                at[n] : text.index("\n\n  #", at[n])
            ]  # the whole step, env included

        on_prem = body(1).replace('/unstract-on-prem"', '/unstract"')
        self.assertEqual(
            on_prem.replace("RELSTATE_AR_ON_PREM_RC", "RELSTATE_AR_CLOUD_RC"), body(0)
        )
        self.assertIn("RELSTATE_AR_ON_PREM_RC", body(1))
        self.assertIn("crane copy", body(0))


class PendingPicksWorkflow(Workflow):
    """Promote's Plan blocks on open conflict PRs (cloud line or pinned OSS line) and held security/critical fixes
    unless forced. A failed listing blocks; forcing passes a failed conflict listing (recorded), never a failed
    held listing. Take RC only warns.
    """

    def setUp(self):
        super().setUp()
        with open(os.path.join(self.cloud, "pyproject.toml"), "w") as fh:
            fh.write('unstract-platform-version = "ee-v1.7.0-rc.1"\n')
        dev_git(self.cloud, "add", "pyproject.toml")
        dev_git(self.cloud, "commit", "-q", "-m", "pin")
        dev_git(self.cloud, "push", "-q", "origin", "main")

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
        return self.run_step(
            inline("promote.yaml", "Plan"),
            RC=rc,
            TARGET="cloud",
            PRODUCTS='["cloud"]',
            **env,
        )

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

    def test_promote_marks_a_cloud_only_line_stabilized(self):
        # A cloud-only line: its cloud promote leaves every enabled target GA, so the OSS step gets --stabilized.
        self.line("1.7", "v1.7.0-rc.1")
        r = self.promote()
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("stabilized=true\n", self.read("output"))

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
        dev_git(
            self.cloud, "commit", "-q", "--allow-empty", "-m", "fix: y"
        )  # the next RC's commit
        dev_git(self.cloud, "tag", "v1.7.1-rc.1")
        dev_git(
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
        dev_git(
            self.cloud, "commit", "-q", "--allow-empty", "-m", "fix: x (#9)"
        )  # on main only: held for 1.7
        dev_git(self.cloud, "push", "-q", "origin", "main")
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
        dev_git(oss_work, "pull", "-q", "origin", "main")
        dev_git(oss_work, "commit", "-q", "--allow-empty", "-m", "fix: z (#9)")
        dev_git(oss_work, "push", "-q", "origin", "main")
        dev_git(oss_work, "fetch", "-q", "origin")
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
        dev_git(self.cloud, "checkout", "-q", "-b", "release/1.7", "origin/release/1.7")
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
        dev_git(self.cloud, "checkout", "-q", "-b", "release/1.7", "origin/release/1.7")
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
            self.read("output"),
            "tag=v1.7.0-rc.2\nbump=true\ntargets=cloud\nreopen=true\n",
        )

    def test_patch_rc_on_a_ga_line_does_not_reopen(self):
        # Every enabled target (cloud) is GA: a cloud patch RC keeps the OSS line's stabilized tag.
        self.line("1.7", "v1.7.0")
        dev_git(self.cloud, "checkout", "-q", "-b", "release/1.7", "origin/release/1.7")
        r = self.run_step(
            inline("take-rc-build.yaml", "Plan version and targets"),
            BRANCH="release/1.7",
            TARGETS="cloud",
        )
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(
            self.read("output"),
            "tag=v1.7.1-rc.1\nbump=true\ntargets=cloud\nreopen=false\n",
        )

    def test_rerun_on_a_tagged_tip_reopens_for_a_target_already_built(self):
        # Tip tagged v1.7.1-rc.1 for both targets, on-prem built, cloud failed; a cloud-only rerun still
        # reopens (on-prem has no GA).
        self.line("1.7", "v1.7.0")
        dev_git(self.cloud, "checkout", "-q", "-b", "release/1.7", "origin/release/1.7")
        dev_git(
            self.cloud, "commit", "-q", "--allow-empty", "-m", "release: chart 1.7.1-rc.1"
        )
        dev_git(self.cloud, "tag", "v1.7.1-rc.1")
        dev_git(
            self.cloud,
            "push",
            "-q",
            "origin",
            "HEAD:refs/heads/release/1.7",
            "v1.7.1-rc.1",
        )
        self.write(
            "reg-on-prem_backend.jsonl",
            '{"id": 1, "digest": "sha256:p", "pushed_at": "2026-09-02T00:00:00Z", "tags": ["v1.7.1-rc.1"]}\n',
        )
        r = self.run_step(
            inline("take-rc-build.yaml", "Plan version and targets"),
            BRANCH="release/1.7",
            TARGETS="cloud,on-prem",
        )
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(
            self.read("output"),
            "tag=v1.7.1-rc.1\nbump=false\ntargets=cloud\nreopen=true\n",
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
            dev_git(self.cloud, "add", "pyproject.toml")
        elif os.path.exists(path):
            dev_git(self.cloud, "rm", "-q", "pyproject.toml")
        dev_git(self.cloud, "commit", "-q", "--allow-empty", "-m", f"pin {pin}")
        for t in tags:
            dev_git(
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
        dev_git(self.cloud, "push", "-q", "--tags", "origin", "main")

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
