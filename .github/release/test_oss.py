"""Run: python test_oss.py"""

import contextlib
import datetime as dt
import hashlib
import io
import itertools
import json
import os
import re
import shutil
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
import oss
import relmgr as rm
import relstate as rs

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


class GateHeading(unittest.TestCase):
    def test_gate_heading_links_the_oss_line(self):
        d = tempfile.TemporaryDirectory()
        self.addCleanup(d.cleanup)
        summary = os.path.join(d.name, "summary")
        env = {"GITHUB_SERVER_URL": "https://github.com", "GITHUB_STEP_SUMMARY": summary}
        done = subprocess.CompletedProcess([], 0, stderr="")
        with (
            mock.patch.dict(os.environ, env),
            mock.patch.object(oss.subprocess, "run", return_value=done),
        ):
            self.assertEqual(
                oss.gate(d.name, "release/1.7", "ee-v1.7.0-rc.1", "warning"), 0
            )
        u = f"https://github.com/{oss.OSS}"
        with open(summary) as f:
            self.assertEqual(
                f.read(),
                f"#### OSS line [`release/1.7`]({u}/tree/release/1.7) at "
                f"[`ee-v1.7.0-rc.1`]({u}/releases/tag/ee-v1.7.0-rc.1)\n\n",
            )


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
        )
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

    def clone(self):
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

    def work(self, branch, msg):
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
                ("release/1.7", "ee-v1.7.0-rc.1", "error"),
                ("release/1.7", "ee-v1.7.0-rc.2", "error"),
            ],
        )

    def test_rc_blocks_on_missing_picks_unless_forced(self):
        self.quiet(oss.cut, self.oss, "1.7")
        self.gate = 2
        with self.assertRaisesRegex(
            RuntimeError,
            "^OSS convergence gate for release/1.7 at ee-v1.7.0-rc.1 blocks: MISSING picks",
        ):
            self.quiet(oss.rc, self.oss, "release/1.7")
        notes = os.path.join(os.path.dirname(self.dev), "notes.md")
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            tag = oss.rc(
                self.oss, "release/1.7", force=True, reason="known gap", notes=notes
            )
        self.assertEqual(tag, "ee-v1.7.0-rc.1")
        self.assertEqual(self.gates[-1], ("release/1.7", "ee-v1.7.0-rc.1", "warning"))
        msg = "Forced past the OSS convergence gate for release/1.7 at ee-v1.7.0-rc.1 (MISSING picks): known gap"
        self.assertIn(f"::warning::{msg}", err.getvalue())
        with open(notes) as f:
            self.assertEqual(f.read(), msg + "\n\n")
        self.gate = 0
        os.remove(notes)
        self.assertEqual(
            self.quiet(oss.rc, self.oss, "release/1.7", notes=notes), "ee-v1.7.0-rc.1"
        )
        self.assertFalse(os.path.exists(notes))  # a clean line adds no note
        self.gate = 1
        with self.assertRaisesRegex(RuntimeError, "did not run"):
            self.quiet(
                oss.rc, self.oss, "release/1.7", force=True, reason="x", notes=notes
            )

    def test_rc_cli_passes_force_reason_and_notes(self):
        self.quiet(oss.cut, self.oss, "1.7")
        self.gate = 2
        notes = os.path.join(os.path.dirname(self.dev), "notes.md")
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            self.assertEqual(
                oss.main(["--oss-repo", self.oss, "rc", "--branch", "release/1.7"]), 1
            )
            code = oss.main(
                [
                    "--oss-repo",
                    self.oss,
                    "rc",
                    "--branch",
                    "release/1.7",
                    "--force",
                    "--reason",
                    "known gap",
                    "--notes",
                    notes,
                ]
            )
        self.assertEqual((code, out.getvalue()), (0, "ee-v1.7.0-rc.1\n"))
        with open(notes) as f:
            self.assertIn("(MISSING picks): known gap", f.read())

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
        self.gate = 0
        self.work("release/1.7", "oss fix")
        self.quiet(oss.rc, self.oss, "release/1.7")
        self.gate = 1
        self.pin("ee-v1.7.1-rc.1", "v1.7.1-rc.2")
        with self.assertRaisesRegex(RuntimeError, "did not run"):
            oss.promote(self.cloud, self.oss, "v1.7.1-rc.2", force=True, reason="x")

    def test_first_promote_stabilizes_the_oss_line(self):
        # The OSS line did not move since the cut: the first promote, of any cloud product, still tags its GA, and
        # that GA alone makes the OSS line stabilized. No stabilized/X.Y mark is written.
        self.addCleanup(rs.use, rs.SLUG)
        rs.use("unstract")
        state = lambda: rs.derive(
            self.oss,
            dt.datetime.now(dt.UTC),
            lambda a: self.fail(f"registry read of {a}"),
        )
        self.quiet(oss.cut, self.oss, "1.7")
        self.pin("ee-v1.7.0-rc.1", "v1.7.0-rc.1")
        st = state()
        self.assertEqual(
            (st["branches"][0]["state"], st["backport_targets"]["rc"]),
            ("stabilizing", ["release/1.7"]),
        )
        self.assertEqual(oss.promote(self.cloud, self.oss, "v1.7.0-rc.1"), "ee-v1.7.0")
        st = state()
        self.assertEqual(
            (st["branches"][0]["state"], st["backport_targets"]["rc"]),
            ("stabilized", []),
        )
        self.assertEqual(st["branches"][0]["targets"]["oss"]["ga"]["tag"], "ee-v1.7.0")
        self.assertEqual(
            self.remote("tag", "-l", "ee-v*").split(), ["ee-v1.7.0", "ee-v1.7.0-rc.1"]
        )
        self.assertEqual(self.remote("tag", "-l", "stabilized/*"), "")

    def test_cli_promote(self):
        self.quiet(oss.cut, self.oss, "1.7")
        self.pin("ee-v1.7.0-rc.1", "v1.7.0-rc.1")
        self.addCleanup(os.chdir, os.getcwd())
        os.chdir(self.cloud)  # main promotes the cloud clone in the working directory
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = oss.main(["--oss-repo", self.oss, "promote", "--rc", "v1.7.0-rc.1"])
        self.assertEqual((code, out.getvalue()), (0, "ee-v1.7.0\n"))

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
            self.gates, [("release/1.7", "ee-v1.7.0-rc.2", "error")]
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
        self.assertEqual(self.remote("rev-parse", "release/1.7"), tip)

    def test_retire(self):
        self.quiet(oss.cut, self.oss, "1.7")
        self.work("release/1.7", "oss fix")
        self.quiet(oss.rc, self.oss, "release/1.7")
        tip = self.remote("rev-parse", "release/1.7")
        with mock.patch.dict(os.environ, {"GITHUB_SERVER_URL": ""}):
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
        web = {"GITHUB_SERVER_URL": "https://github.com"}
        u = f"https://github.com/{oss.OSS}"
        with mock.patch.dict(os.environ, web):
            linked = oss.retire(self.oss, "release/1.7", "cut by mistake")
            self.assertEqual(
                linked[0],
                f"- OSS `release/1.7` (tip [`{tip[:12]}`]({u}/commit/{tip}); no GA, RC tags deleted)",
            )
            self.assertEqual(linked[-1], dry[-1])  # not pushed yet: no link
            real = oss.retire(self.oss, "release/1.7", "cut by mistake", dry_run=False)
        self.assertEqual(real[:-1], linked[:-1])
        self.assertEqual(
            real[-1],
            f"- OSS tag [`retired/1.7-{tip[:7]}`]({u}/releases/tag/retired/1.7-{tip[:7]}): cut by mistake",
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
        self.clone()
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
        ):
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

        def flaky(*a):
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
        u = f"https://github.com/{oss.OSS}"
        self.assertEqual(
            oss.retire(self.oss, "release/1.7", "past end of support", dry_run=False),
            [
                f"- OSS `release/1.7` (tip [`{tip[:12]}`]({u}/commit/{tip}); has GA, tags kept)",
                f"- OSS tag [`retired/1.7-{tip[:7]}`]({u}/releases/tag/retired/1.7-{tip[:7]}): past end of support",
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
        # The gate reads only ee- tags and asks the OSS repo, not the cloud one, for conflict PRs.
        with tempfile.TemporaryDirectory() as d:
            g = lambda *a: dev_git(d, *a)
            g("init", "-q", "-b", "main")
            g("commit", "-q", "--allow-empty", "-m", "base")
            g("branch", "release/1.6")
            g("branch", "release/1.7")
            with open(os.path.join(d, "f.txt"), "w") as fh:
                fh.write("rc")
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
    with open(os.path.join(HERE, "..", "workflows", workflow)) as fh:
        wf = fh.read()
    body = wf[
        wf.index("python3 - <<'PY'", wf.index(f"- name: {step}\n")) :
    ]  # the heredoc line may redirect
    return "\n".join(
        line[10:] for line in body.split("\n")[1 : body.split("\n").index("          PY")]
    )


PAST_EOS = "Retire shipped lines past end of support"
ONE = "Retire one shipped line now"
ABANDON = "Abandon a line that never shipped"


def run_name(workflow, **ctx):
    """The workflow's run-name evaluated as Actions does, for ctx keyed like "inputs.dry_run"; an absent key is
    empty, as every input is on a schedule or push run. Covers the operators run-names here use: && || == and
    format(), startsWith().
    """
    with open(os.path.join(HERE, "..", "workflows", workflow)) as fh:
        lines = fh.read().split("\n")
    i = next(n for n, line in enumerate(lines) if line.startswith("run-name:"))
    expr = lines[i][len("run-name:") :].strip()
    if expr == ">-":
        expr = " ".join(
            line.strip()
            for line in itertools.takewhile(
                lambda line: line.startswith("  "), lines[i + 1 :]
            )
        )
    expr = re.fullmatch(r"\$\{\{(.*)\}\}", expr).group(1)
    py = re.sub(
        r"\b(?:inputs|github)\.[\w.-]+", lambda m: f"ctx.get({m.group(0)!r}, '')", expr
    )
    py = py.replace("&&", " and ").replace("||", " or ")
    fns = {
        "format": lambda f, *a: f.format(*a),
        "startsWith": lambda v, p: str(v).lower().startswith(p.lower()),
    }
    return eval(py, fns, {"ctx": ctx})


def dispatch_inputs(workflow):
    """{input: its lines} of the workflow_dispatch form."""
    with open(os.path.join(HERE, "..", "workflows", workflow)) as fh:
        text = fh.read()
    form = text[text.index("  workflow_dispatch:\n") :]
    form = form[form.index("    inputs:\n") + len("    inputs:\n") :]
    inputs, name = {}, None
    for line in form.split("\n"):
        if line.strip() and not line.startswith("      "):
            break
        if re.fullmatch(r"      [\w-]+:", line):
            name = line.strip()[:-1]
            inputs[name] = []
        elif name:
            inputs[name].append(line.strip())
    return inputs


def step(workflow, name, exprs=()):
    """Each ${{ }} expression is replaced from exprs, "" when absent."""
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
    """Cloud and OSS origins with clones. The registry stub reads reg*.jsonl and pkgs-<repo>.json; the gh stub
    serves <owner>_<repo>.json and pulls.json, logs to gh.log, and fails when prfail/pullsfail exists.
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
def _ar_versions(repo, package, artifact):  # reg.jsonl for cloud/backend, reg-<kind>_<package>.jsonl for the others, else its kind's backend; a row's "repo" (default r) is its repository, "names" its version ids' repository
    f = lambda a: os.path.join({d!r}, "reg.jsonl" if a == "cloud/backend" else "reg-" + a.replace("/", "_") + ".jsonl")
    f = f(artifact) if os.path.exists(f(artifact)) else f(artifact.split("/")[0] + "/backend")
    if not os.path.exists(f):
        return []
    with open(f) as fh:
        rows = [v for v in map(json.loads, fh) if v.get("repo", "r") == repo]
    return [{{"name": f"{{v.get('names', repo)}}/packages/{{package}}/versions/{{v['digest']}}", "createTime": v["pushed_at"],
              "relatedTags": [{{"name": f"{{repo}}/packages/{{package}}/tags/{{t}}"}} for t in v["tags"]]}} for v in rows]
relstate._ar_versions = _ar_versions
def _ar_packages(repo):  # pkgs-<repo>.json: the packages a repository lists
    f = os.path.join({d!r}, "pkgs-" + repo + ".json")
    return json.load(open(f)) if os.path.exists(f) else []
relstate._ar_packages = _ar_packages
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
  "pr list -R "*"--state merged"*) echo "$GH_TOKEN $*" >> {d}/gh.log; [ -e {d}/mergedfail ] && exit 1
    cat "{d}/merged-$(echo "$4" | tr / _).json" 2>/dev/null || echo "[]";;
  "pr list -R "*) echo "$GH_TOKEN $*" >> {d}/gh.log; [ -e {d}/prfail ] && exit 1
    cat "{d}/$(echo "$4" | tr / _).json" 2>/dev/null || echo "[]";;
  *"/pulls"*) echo "$GH_TOKEN $*" >> {d}/gh.log; [ -e {d}/pullsfail ] && exit 1
    cat {d}/pulls.json 2>/dev/null || echo "[]";;
  *"/actions/workflows/"*) echo "$GH_TOKEN $*" >> {d}/gh.log; [ -e {d}/runsfail ] && exit 1
    wf=${{2#*/actions/workflows/}}; cat "{d}/runs-${{wf%%/*}}" 2>/dev/null;;
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
        for name in ("output", "notes.md"):
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
    """Retire's inline script in each action: the OSS line goes with the cloud one."""

    def retire(self, **env):
        r = self.run_step(
            inline("retire.yaml", "Derive and retire"),
            **{"ACTION": PAST_EOS, "LINE": "", "DRY_RUN": "false", **env},
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
        self.retire(ACTION=ABANDON, LINE="1.7", REASON="cut by mistake")
        self.assert_gone("1.7")

    def test_abandon_deletes_one_rc_and_keeps_the_last(self):
        self.line("1.7", "v1.7.0-rc.1", "v1.7.0-rc.2")
        self.retire(
            ACTION=ABANDON,
            LINE="release/1.7",
            REASON="cut by mistake",
            RELSTATE_AR_TOKEN="t",
        )
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
            ACTION=ABANDON,
            LINE="release/1.7",
            REASON="cut by mistake",
            RELSTATE_AR_TOKEN="t",
            RELSTATE_AR_CLOUD_RC="rc",
        )
        self.assertRegex(
            self.read("ar.log"),
            r"^DELETE \S+/rc/packages/backend/versions/sha256:rc1\?force=true\n$",
        )

    def test_abandon_deletes_every_service_in_the_rc_repository(self):
        self.line(
            "1.7", "v1.7.0-rc.1", "v1.7.0-rc.2"
        )  # backend RCs in the stable repository
        self.write("pkgs-rc.json", json.dumps(["backend", "frontend"]))
        rows = {
            "reg.jsonl": [("rc", "be3", "v1.7.0-rc.3"), ("rc", "be-old", "v1.6.0-rc.1")],
            "reg-cloud_frontend.jsonl": [
                ("rc", "fe3", "v1.7.0-rc.3"),
                ("rc", "fe-old", "v1.6.0-rc.1"),
                # The stable repository: abandon reads no other service there.
                ("r", "fe-stable1", "v1.7.0-rc.1"),
                ("r", "fe-stable2", "v1.7.0-rc.2"),
            ],
        }
        for name, vs in rows.items():
            with open(os.path.join(self.d, name), "a") as fh:
                for repo, digest, tag in vs:
                    fh.write(
                        json.dumps(
                            {
                                "repo": repo,
                                "digest": f"sha256:{digest}",
                                "pushed_at": "2026-09-01T00:00:00Z",
                                "tags": [tag],
                            }
                        )
                        + "\n"
                    )
        self.retire(
            ACTION=ABANDON,
            LINE="release/1.7",
            REASON="cut by mistake",
            RELSTATE_AR_TOKEN="t",
            RELSTATE_AR_CLOUD_RC="rc",
        )
        self.assertEqual(
            sorted(re.findall(r"DELETE \S+?/v1/(\S+)\?force=true", self.read("ar.log"))),
            [
                "r/packages/backend/versions/sha256:v1.7.0-rc.1",
                "rc/packages/backend/versions/sha256:be3",
                "rc/packages/frontend/versions/sha256:fe3",
            ],
        )

    def test_abandon_without_rc_repositories_reads_no_other_service(self):
        self.line("1.7")
        self.write("pkgs-r.json", json.dumps(["backend", "frontend"]))
        with open(os.path.join(self.d, "reg-cloud_frontend.jsonl"), "a") as fh:
            for i in (1, 2):
                fh.write(
                    json.dumps(
                        {
                            "digest": f"sha256:fe{i}",
                            "pushed_at": "2026-09-01T00:00:00Z",
                            "tags": [f"v1.7.0-rc.{i}"],
                        }
                    )
                    + "\n"
                )
        self.retire(
            ACTION=ABANDON,
            LINE="release/1.7",
            REASON="cut by mistake",
            RELSTATE_AR_TOKEN="t",
        )
        self.assertFalse(os.path.exists(os.path.join(self.d, "ar.log")))

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
            ACTION=ABANDON,
            LINE="release/1.7",
            REASON="cut by mistake",
            DRY_RUN="false",
            RELSTATE_AR_TOKEN="t",
        )
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn("other/packages/backend/versions/sha256:rc1 is outside r", r.stdout)
        self.assertFalse(os.path.exists(os.path.join(self.d, "ar.log")))

    def test_an_unfinished_run_refuses_before_any_change(self):
        self.line("1.7", "v1.7.0-rc.1")
        self.write("runs-take-rc-build.yaml", "https://example.test/runs/9\n")
        origin = self.repos["cloud"][0]
        tags = rm.git(origin, "tag", "-l")
        for dry in ("true", "false"):
            r = self.run_step(
                inline("retire.yaml", "Derive and retire"),
                ACTION=ABANDON,
                LINE="1.7",
                REASON="cut by mistake",
                DRY_RUN=dry,
                RELSTATE_AR_TOKEN="t",
            )
            self.assertEqual(r.returncode, dry == "false", r.stdout + r.stderr)
            if dry == "true":
                self.assertIn(
                    "::warning::a real run would refuse while this run is unfinished: https://example.test/runs/9",
                    r.stdout,
                )
        self.assertIn(
            "::error::wait for these runs to finish, then run Retire again: https://example.test/runs/9",
            r.stdout,
        )
        self.assertIn(
            "cloud-token api repos/Zipstack/unstract-cloud/actions/workflows/promote.yaml/runs?per_page=100 "
            '--jq .workflow_runs[] | select(.status != "completed") | .html_url',
            self.read("gh.log"),
        )
        self.assertIn("release/1.7", rm.git(origin, "branch", "-l", "release/*"))
        self.assertEqual(rm.git(origin, "tag", "-l"), tags)
        self.assertFalse(os.path.exists(os.path.join(self.d, "ar.log")))

    def test_a_failed_run_list_refuses(self):
        self.line("1.7")
        self.write("runsfail", "")
        r = self.run_step(
            inline("retire.yaml", "Derive and retire"),
            ACTION=PAST_EOS,
            LINE="",
            DRY_RUN="true",
        )
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn("::error::could not list the cut.yaml runs", r.stdout)

    def kept_line(self, x_y, msg, **env):
        origin = self.repos["cloud"][0]
        tags = rm.git(origin, "tag", "-l")
        r = self.run_step(
            inline("retire.yaml", "Derive and retire"),
            **{
                "ACTION": PAST_EOS,
                "LINE": "",
                "DRY_RUN": "false",
                "RELSTATE_AR_TOKEN": "t",
                **env,
            },
        )
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn(msg, r.stdout)
        self.assertIn(f"release/{x_y}", rm.git(origin, "branch", "-l", "release/*"))
        self.assertEqual(rm.git(origin, "tag", "-l"), tags)
        self.assertFalse(os.path.exists(os.path.join(self.d, "ar.log")))

    def test_abandon_refuses_a_line_with_ga(self):
        self.line("1.7", "v1.7.0-rc.1", "v1.7.0-rc.2", "v1.7.0")
        self.kept_line(
            "1.7",
            "::error::abandon release/1.7: line has GA v1.7.0, cloud/backend:v1.7.0; use 'Retire one shipped line now'",
            ACTION=ABANDON,
            LINE="release/1.7",
            REASON="cut by mistake",
        )

    def test_abandon_lists_human_commits_the_archive_keeps(self):
        self.line("1.7", "v1.7.0-rc.1", "v1.7.0-rc.2")
        dev_git(self.cloud, "commit", "-q", "--allow-empty", "-m", "work on 1.7")
        dev_git(self.cloud, "push", "-q", "origin", "HEAD:release/1.7")
        work = dev_git(self.cloud, "rev-parse", "HEAD")
        env = {
            "ACTION": ABANDON,
            "LINE": "1.7",
            "REASON": "cut by mistake",
            "GITHUB_SERVER_URL": "https://github.com",
            "RELSTATE_AR_TOKEN": "t",
        }
        self.retire(DRY_RUN="true", **env)
        web = "https://github.com/Zipstack/unstract-cloud"
        line = f"- human commit [`{work[:12]}`]({web}/commit/{work[:12]}) (kept by the archive tag)"
        self.assertIn(line, self.read("summary"))
        self.retire(**env)
        self.assertIn(line, self.read("summary").split("abandoned release/1.7")[1])
        tag = rm.git(self.repos["cloud"][0], "tag", "-l", "retired/1.7-*")
        self.assertEqual(
            rm.git(self.repos["cloud"][0], "rev-parse", f"{tag}^{{commit}}"), work
        )

    def test_links_only_what_survives(self):
        web = "https://github.com/Zipstack/unstract-cloud"
        self.line("1.6", "v1.6.0-rc.1", "v1.6.0")
        self.line("1.7", "v1.7.0-rc.1", "v1.7.0")  # 1.6 is past end of support
        self.line("1.8")
        tip = rm.git(self.repos["cloud"][0], "rev-parse", "release/1.6")
        tag = f"retired/1.6-{tip[:7]}"
        never = {"ACTION": ABANDON, "LINE": "1.8", "REASON": "x"}
        self.retire(DRY_RUN="true")
        self.retire(DRY_RUN="true", **never)
        dry = self.read("summary")
        self.assertIn(f"- tag `{tag}`: past end of support", dry)
        self.assertIn(f"- branch [`release/1.8`]({web}/tree/release/1.8) (tip ", dry)
        self.retire()
        self.retire(**never)
        real = self.read("summary")[len(dry) :]
        self.assertIn(
            f"- tag [`{tag}`]({web}/releases/tag/{tag}): past end of support", real
        )
        self.assertIn("- branch `release/1.8` (tip ", real)

    def test_refuses_a_value_not_a_line(self):
        self.line("1.7")
        for action, verb in ((ABANDON, "abandon"), (ONE, "retire")):
            self.kept_line(
                "1.7",
                f"::error::{verb} 1.7.0: not a release line X.Y (e.g. 0.186): '1.7.0'",
                ACTION=action,
                LINE="1.7.0",
                REASON="x",
            )

    def test_one_line_needs_a_line(self):
        self.line("1.6", "v1.6.0-rc.1", "v1.6.0")
        self.line("1.7", "v1.7.0-rc.1", "v1.7.0")  # 1.6 is past end of support, and stays
        for action, verb in ((ABANDON, "abandon"), (ONE, "retire")):
            self.kept_line(
                "1.6", f"::error::{verb}: line X.Y is required", ACTION=action, REASON="x"
            )

    def test_one_line_needs_a_reason(self):
        self.line("1.7", "v1.7.0-rc.1", "v1.7.0")
        for action, verb in ((ABANDON, "abandon"), (ONE, "retire")):
            self.kept_line(
                "1.7",
                f"::error::{verb} release/1.7: reason is required",
                ACTION=action,
                LINE="1.7",
                REASON=" ",
            )

    def test_refuses_an_unknown_action(self):
        self.line("1.6", "v1.6.0-rc.1", "v1.6.0")
        self.line("1.7", "v1.7.0-rc.1", "v1.7.0")
        self.kept_line(
            "1.6",
            "::error::unknown action 'Delete everything'",
            ACTION="Delete everything",
        )

    def test_past_eos_refuses_a_line(self):
        # A line typed under the default action is a mistake, not a request to retire every past-eos line.
        self.line("1.6", "v1.6.0-rc.1", "v1.6.0")
        self.line("1.7", "v1.7.0-rc.1", "v1.7.0")
        self.kept_line(
            "1.6",
            "::error::line set for 'Retire shipped lines past end of support': pick the matching action, or clear it",
            LINE="1.7",
        )

    def test_past_eos_refuses_a_reason(self):
        # Past-eos archive tags carry a fixed reason, so a typed one would be dropped without a word.
        self.line("1.6", "v1.6.0-rc.1", "v1.6.0")
        self.line("1.7", "v1.7.0-rc.1", "v1.7.0")
        self.kept_line(
            "1.6",
            "::error::reason set for 'Retire shipped lines past end of support': pick the matching action, or clear it",
            REASON="cut by mistake",
        )

    def test_retire_one_with_ga_keeps_its_rcs(self):
        # 1.8 is cloud production, so 1.7 may retire early; it shipped, so its RCs stay as history.
        self.line("1.7", "v1.7.0-rc.1", "v1.7.0-rc.2", "v1.7.0")
        self.line("1.8", "v1.8.0-rc.1", "v1.8.0")
        self.retire(ACTION=ONE, LINE="release/1.7", REASON="early", RELSTATE_AR_TOKEN="t")
        summary = self.read("summary")
        self.assertIn("retired release/1.7: early", summary)
        self.assertIn("has GA, tags and artifacts kept", summary)
        origin = self.repos["cloud"][0]
        self.assertEqual(
            rm.git(origin, "tag", "-l", "v1.7.*").split(),
            ["v1.7.0", "v1.7.0-rc.1", "v1.7.0-rc.2"],
        )
        self.assertRegex(
            rm.git(origin, "tag", "-l", "retired/1.7-*"), r"^retired/1\.7-[0-9a-f]{7}$"
        )
        self.assertFalse(os.path.exists(os.path.join(self.d, "ar.log")))
        self.assertNotIn("release/1.7", rm.git(origin, "branch", "-l", "release/*"))
        self.assertEqual(
            rs._next_minor(origin, []), "1.9"
        )  # a shipped line's minor stays used

    def test_retire_one_refuses_a_line_with_no_ga(self):
        self.line("1.7", "v1.7.0-rc.1")
        self.kept_line(
            "1.7",
            "::error::retire release/1.7: line has no GA; use 'Abandon a line that never shipped'",
            ACTION=ONE,
            LINE="1.7",
            REASON="not shipping",
        )

    def test_retire_one_refuses_cloud_production_even_with_force(self):
        self.line("1.7", "v1.7.0-rc.1", "v1.7.0")
        for force in ("false", "true"):
            self.kept_line(
                "1.7",
                "::error::retire release/1.7: cloud is production (newest cloud GA)",
                ACTION=ONE,
                LINE="1.7",
                REASON="early",
                FORCE=force,
            )

    def test_retire_one_needs_force_for_on_prem_in_its_window(self):
        self.line("1.7", "v1.7.0-rc.1", "v1.7.0")
        self.line("1.8", "v1.8.0-rc.1", "v1.8.0")  # 1.7's cloud is past end of support
        pushed = f"{dt.datetime.now(dt.UTC) - dt.timedelta(days=1):%Y-%m-%dT%H:%M:%SZ}"
        self.write(
            "reg-on-prem_backend.jsonl",
            f'{{"id": 1, "digest": "sha256:o", "pushed_at": "{pushed}", "tags": ["v1.7.0-rc.1"]}}\n',
        )
        self.write(  # the on-prem chart GA, in its support window
            "reg-chart_unstract-platform.jsonl",
            f'{{"id": 2, "digest": "sha256:c", "pushed_at": "{pushed}", "tags": ["1.7.0"]}}\n',
        )
        env = {"ACTION": ONE, "LINE": "1.7", "REASON": "customer moved"}
        self.kept_line(
            "1.7", "::error::retire release/1.7: on-prem still supported", **env
        )
        self.retire(FORCE="true", DRY_RUN="true", **env)
        self.assertIn(
            "would retire release/1.7: customer moved (forced past on-prem)",
            self.read("summary"),
        )
        self.retire(FORCE="true", **env)
        self.assertIn(
            "retired release/1.7: customer moved (forced past on-prem)",
            self.read("summary"),
        )
        self.assertIn(
            "retired release/1.7: customer moved (forced past on-prem)",
            rm.git(
                self.repos["cloud"][0],
                "tag",
                "-l",
                "retired/1.7-*",
                "--format=%(contents)",
            ),
        )
        self.assertNotIn(
            "release/1.7", rm.git(self.repos["cloud"][0], "branch", "-l", "release/*")
        )

    def test_retire_one_records_a_force_that_held_nothing(self):
        self.line("1.7", "v1.7.0-rc.1", "v1.7.0")
        self.line("1.8", "v1.8.0-rc.1", "v1.8.0")
        self.retire(ACTION=ONE, LINE="1.7", REASON="early", FORCE="true")
        self.assertIn(
            "retired release/1.7: early (forced past nothing held)",
            self.read("summary"),
        )

    def test_retire_one_links_only_what_survives(self):
        self.line("1.7", "v1.7.0-rc.1", "v1.7.0")
        self.line("1.8", "v1.8.0-rc.1", "v1.8.0")
        tip = rm.git(self.repos["cloud"][0], "rev-parse", "release/1.7")
        web = "https://github.com/Zipstack/unstract-cloud"
        tag = f"retired/1.7-{tip[:7]}"
        env = {
            "ACTION": ONE,
            "LINE": "1.7",
            "REASON": "x",
            "GITHUB_SERVER_URL": "https://github.com",
        }
        self.retire(DRY_RUN="true", **env)
        dry = self.read("summary")
        self.assertIn(
            f"- branch [`release/1.7`]({web}/tree/release/1.7) (tip [`{tip[:12]}`]({web}/commit/{tip});",
            dry,
        )
        self.assertIn(f"- tag `{tag}`: x", dry)
        self.retire(**env)
        real = self.read("summary")[len(dry) :]
        self.assertIn(
            f"- branch `release/1.7` (tip [`{tip[:12]}`]({web}/commit/{tip});", real
        )
        self.assertIn(f"- tag [`{tag}`]({web}/releases/tag/{tag}): x", real)

    def test_abandon_archives_the_tip_and_frees_the_minor(self):
        self.line("1.7", "v1.7.0-rc.1", "v1.7.0")
        self.line("1.8", "v1.8.0-rc.1")
        origin = self.repos["cloud"][0]
        tip = rm.git(origin, "rev-parse", "release/1.8")
        self.retire(
            ACTION=ABANDON, LINE="1.8", REASON="cut by mistake", RELSTATE_AR_TOKEN="t"
        )
        self.assertIn("abandoned release/1.8 (1 RC tag(s)", self.read("summary"))
        self.assertEqual(
            rm.git(origin, "tag", "-l", "retired/*"), f"retired/1.8-{tip[:7]}"
        )
        self.assertEqual(rm.git(origin, "tag", "-l", "v1.8.*"), "")
        self.assertEqual(rs._next_minor(origin, []), "1.8")  # the next cut reuses it

    def test_past_eos_and_abandon_refuse_force(self):
        self.line("1.6", "v1.6.0-rc.1", "v1.6.0")
        self.line("1.7", "v1.7.0-rc.1", "v1.7.0")
        self.line("1.8")
        self.kept_line(
            "1.6",
            "::error::force set for 'Retire shipped lines past end of support'",
            FORCE="true",
        )
        self.kept_line(
            "1.8",
            "::error::force set for 'Abandon a line that never shipped'",
            ACTION=ABANDON,
            LINE="1.8",
            REASON="x",
            FORCE="true",
        )

    def test_an_omitted_action_retires_past_end_of_support(self):
        self.line("1.6", "v1.6.0-rc.1", "v1.6.0")
        self.line("1.7", "v1.7.0-rc.1", "v1.7.0")
        self.retire(ACTION="")
        self.assert_gone("1.6")

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
            **{"ACTION": PAST_EOS, "LINE": "", "DRY_RUN": "false", **env},
        )
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn(f"after {tag} archived it", r.stdout)
        self.assertEqual(rm.git(origin, "tag", "-l", "retired/*"), tag)
        self.assertIn(f"release/{x_y}", rm.git(origin, "branch", "-l", "release/*"))

    def lands_mid_run(self, x_y):
        """A push to release/x_y lands after this run read its tip: origin's hook moves the branch on the run's
        first tag push, before its branch delete.
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
            **{"ACTION": PAST_EOS, "LINE": "", "DRY_RUN": "false", **env},
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
            ACTION=ABANDON,
            LINE="release/1.7",
            REASON="cut by mistake",
        )

    def test_retire_one_keeps_a_branch_pushed_after_its_tip_was_read(self):
        self.line("1.7", "v1.7.0-rc.1", "v1.7.0")
        self.line("1.8", "v1.8.0-rc.1", "v1.8.0")
        self.kept(
            "1.7",
            self.lands_mid_run("1.7"),
            ACTION=ONE,
            LINE="release/1.7",
            REASON="early",
        )

    def test_retire_one_refuses_a_line_moved_after_its_archive(self):
        self.line("1.7", "v1.7.0-rc.1", "v1.7.0")
        tag = self.moved("1.7")
        self.line("1.8", "v1.8.0-rc.1", "v1.8.0")
        self.refused("1.7", tag, ACTION=ONE, LINE="release/1.7", REASON="early")

    def test_abandon_refuses_a_line_moved_after_its_archive(self):
        self.line("1.7", "v1.7.0-rc.1")
        tag = self.moved("1.7")
        self.refused(
            "1.7", tag, ACTION=ABANDON, LINE="release/1.7", REASON="cut by mistake"
        )

    def test_derived_list_keeps_a_branch_pushed_after_its_tip_was_read(self):
        self.line("1.6", "v1.6.0-rc.1", "v1.6.0")
        self.line("1.7", "v1.7.0-rc.1", "v1.7.0")
        self.kept("1.6", self.lands_mid_run("1.6"))

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
    DEV = "d-docker.pkg.dev/p/dev"

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
                "DEV_REGISTRY": self.DEV,
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
            self.merged(rc, "v2.0.0", self.REG),
            {"postgresql.enabled": "false", "global.unstract.image.tag": "v2.0.0"},
        )

    def test_no_tag_keeps_the_current_one(self):
        self.assertEqual(
            self.merged(
                [self.OTHER, {"name": "global.unstract.image.tag", "value": "v1.0.0"}]
            ),
            {"postgresql.enabled": "false", "global.unstract.image.tag": "v1.0.0"},
        )

    def test_a_kept_rc_tag_pulls_from_cloud_rc(self):
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
            self.merged([self.OTHER], "v2.0.0"),
            {"postgresql.enabled": "false", "global.unstract.image.tag": "v2.0.0"},
        )

    def test_cloud_rc_is_not_taken_without_an_rc_tag(self):
        for tag in ("v2.0.0", "rc.3"):
            for cloud_rc in (self.REG, ""):
                self.assertEqual(
                    self.merged([self.OTHER], tag, cloud_rc),
                    {"postgresql.enabled": "false", "global.unstract.image.tag": tag},
                )

    def test_a_dev_tag_pulls_from_the_dev_registry(self):
        # a dev tag's images are only in the dev repository
        kept = {"name": "global.unstract.image.tag", "value": "snapshot.7"}
        for current, tag in (([self.OTHER], "snapshot.7"), ([self.OTHER, kept], "")):
            for cloud_rc in (self.REG, ""):
                got = self.merged(current, tag, cloud_rc)
                self.assertEqual(got["global.unstract.image.tag"], "snapshot.7")
                for s in (
                    "frontend",
                    "backend",
                    "runner",
                    "platform",
                    "x2text",
                    "worker",
                ):
                    self.assertEqual(got[f"{s}.image.registry"], self.DEV, s)
                self.assertEqual(
                    got["runner.configMap.TOOL_SIDECAR_IMAGE_NAME"],
                    f"{self.DEV}/tool-sidecar",
                )
                self.assertEqual(
                    got["runner.configMap.TOOL_SIDECAR_IMAGE_TAG"], "snapshot.7"
                )
        for tag in ("my-branch-fix", "v1.2.0-rc.1-snapshot", "rc.3a", "v2.0"):
            self.assertEqual(
                self.merged([self.OTHER], tag)["backend.image.registry"], self.DEV, tag
            )

    def test_a_release_tag_after_a_dev_tag_drops_the_dev_registry(self):
        dev = [
            {"name": n, "value": v}
            for n, v in self.merged([self.OTHER], "snapshot.7").items()
        ]
        self.assertEqual(
            self.merged(dev, "v2.0.0"),
            {"postgresql.enabled": "false", "global.unstract.image.tag": "v2.0.0"},
        )
        self.assertEqual(
            self.merged(dev, "v2.0.0-rc.1", self.REG)["backend.image.registry"], self.REG
        )

    def test_a_revision_alone_never_takes_the_dev_registry(self):
        # no tag parameter: the chart's own tag at that revision applies, a release tag in its values.yaml
        for revision in ("main", "feature/x", "snapshot.7"):
            self.assertEqual(
                self.merged([self.OTHER], revision=revision),
                {"postgresql.enabled": "false"},
            )


RC = "projects/p/locations/l/repositories/rc"
RC_HOST = "l-docker.pkg.dev/p/rc"
# The dev repositories, as the build workflows name them; read from there (only the cloud repo has them) to keep the
# names out of this shared file, and pinned by hash in test_dev_repositories_are_pinned
_dev = os.path.join(HERE, "..", "workflows", "cloud-backend-docker-build-push.yaml")
_dev = os.path.exists(_dev) and re.findall(
    r"^ +(?:cloud|on_prem)=\$\(root projects/([^/]+)/locations/([^/]+)/repositories/([^/)]+)\)$",
    open(_dev).read(),
    re.M,
)
DEV_HOST = _dev and f"{_dev[0][1]}-docker.pkg.dev"
DEV_REPOS, DEV_REPOS_ON_PREM = (
    [f"{loc}-docker.pkg.dev/{p}/{r}" for p, loc, r in _dev] if _dev else [None, None]
)


@unittest.skipUnless(
    os.path.exists(os.path.join(HERE, "..", "workflows", "build-push.yaml")),
    "the cloud repo's workflows",
)
class GuardSteps(unittest.TestCase):
    """Workflow steps run as bash against stub curl, crane and docker; the stubs read and log files in self.d,
    and img/<image> holds an image's digest.
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
    if [ "$6" = '{{{{json .Image}}}}' ]; then
      [ ! -e {d}/config_err ] || {{ cat {d}/config_err; exit 1; }}
      cat "$(img "${{4%@*}}").json"
    else cat "$(img "$4")"; fi;;
  "buildx imagetools create") echo "$6 $5" >> {d}/copies; cp "$(img "${{6%@*}}")" "$(img "$5")"
    cp "$(img "${{6%@*}}").json" "$(img "$5").json"
    [ ! -e {d}/drift ] || echo sha256:other > "$(img "$5")";;
  "login -u oauth2accesstoken") echo "$5 $(cat)" >> {d}/logins;;
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
                "DEV_REGISTRY": DEV_REPOS,
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
        r, params = self.sync({"spec": {"source": {}}}, IMAGE_TAG="v1.2.0")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(params, {"global.unstract.image.tag": "v1.2.0"})

    def test_sync_keeps_an_unrelated_parameter_and_takes_cloud_rc(self):
        r, params = self.sync(self.APP, IMAGE_TAG="v1.2.0-rc.1", CLOUD_RC=RC)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(params["postgresql.enabled"], "false")
        self.assertEqual(params["backend.image.registry"], RC_HOST)
        with open(os.path.join(self.d, "env")) as fh:
            self.assertIn(f"IMAGE_REGISTRY_APPLIED={RC_HOST}", fh.read())
        r, params = self.sync(self.APP, IMAGE_TAG="v1.2.0", CLOUD_RC=RC)
        self.assertEqual(
            params,
            {"postgresql.enabled": "false", "global.unstract.image.tag": "v1.2.0"},
        )

    def test_sync_of_a_dev_tag_takes_the_dev_registry(self):
        r, params = self.sync(self.APP, IMAGE_TAG="snapshot.7", CLOUD_RC=RC)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(params["backend.image.registry"], DEV_REPOS)
        with open(os.path.join(self.d, "env")) as fh:
            self.assertIn(f"IMAGE_REGISTRY_APPLIED={DEV_REPOS}", fh.read())

    def test_sync_argocd_dev_registry_is_where_the_builds_push(self):
        with open(os.path.join(HERE, "..", "workflows", "sync-argocd.yaml")) as fh:
            self.assertEqual(
                re.findall(r"\n +DEV_REGISTRY: (.*)\n", fh.read()), [DEV_REPOS]
            )
        r = self.bash(
            step("cloud-backend-docker-build-push.yaml", "Image roots"),
            DEV="true",
            PROJECT_ID="p",
            TOKEN="t",
        )
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        with open(os.path.join(self.d, "env")) as fh:
            self.assertIn(f"IMAGE_ROOT_CLOUD={DEV_REPOS}\n", fh.read())

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
        for source in ("rc.4",):
            r, copy = self.retag(
                {f"{self.STABLE}/backend:{source}": "sha256:s"}, source=source
            )
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            self.assertEqual(
                copy, f"{self.STABLE}/backend:{source} {self.STABLE}/backend:v1.2.0"
            )
            os.remove(os.path.join(self.d, "copies"))

    def test_retag_takes_release_tags_only(self):
        def validate(source, target):
            return self.bash(
                step(
                    "retag-docker-images.yaml",
                    "Validate inputs",
                    {
                        "inputs.source_tag || github.event.inputs.source_tag": source,
                        "inputs.target_tag || github.event.inputs.target_tag": target,
                    },
                )
            ).returncode

        for source in ("rc.4", "v1.2.0-rc.1"):
            self.assertEqual(validate(source, "v1.2.0"), 0, source)
        # a snapshot is a dev build, in the dev repositories, never in the stable ones retag copies within
        for source, target in (
            ("snapshot.7", "v1.2.0"),
            ("rc.4", "snapshot.8"),
            ("v1.2.0", "v1.2.1"),
        ):
            self.assertEqual(validate(source, target), 1, (source, target))

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
        for cloud_rc in (RC, ""):
            os.remove(os.path.join(self.d, "env"))
            r = self.bash(roots, CLOUD_RC=cloud_rc, DEV="true", **env)
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            with open(os.path.join(self.d, "env")) as fh:
                self.assertEqual(
                    fh.read(),
                    f"IMAGE_ROOT_CLOUD={DEV_REPOS}\nIMAGE_ROOT_ON_PREM={DEV_REPOS_ON_PREM}\n",
                )

    def test_dev_repositories_are_pinned(self):
        # the names this file reads from the workflow, pinned without naming them
        self.assertEqual(
            [
                hashlib.sha256(r.encode()).hexdigest()[:16]
                for r in (DEV_REPOS, DEV_REPOS_ON_PREM)
            ],
            ["09c6e2192638ca1b", "0d09d8937e810c71"],
        )

    def test_dev_live_update_image_root(self):
        root = step("dev-live-update-image.yaml", "Image root")
        logins = os.path.join(self.d, "logins")
        for dev, want, login in (
            ("true", DEV_REPOS, f"https://{DEV_HOST} t\n"),
            ("false", self.STABLE, None),
        ):
            for f in (os.path.join(self.d, "env"), logins):
                if os.path.exists(f):
                    os.remove(f)
            r = self.bash(root, DEV=dev, PROJECT_ID="p", TOKEN="t")
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            with open(os.path.join(self.d, "env")) as fh:
                self.assertEqual(fh.read(), f"IMAGE_ROOT_CLOUD={want}\n", dev)
            if login:
                with open(logins) as fh:
                    self.assertEqual(fh.read(), login, dev)
            else:
                self.assertFalse(os.path.exists(logins), dev)

    def test_image_kind(self):
        kind = step("cloud-backend-docker-build-push.yaml", "Image kind")
        for tag, dev in (
            ("rc.12", "false"),
            ("v1.2.0", "false"),
            ("v1.2.0-rc.3", "false"),
            ("snapshot.7", "true"),
            ("snapshot.412-fix2", "true"),
            ("my-feature", "true"),
            ("v1.2", "true"),
            ("rc.12x", "true"),
            ("v1.2.0-rc.1-snapshot", "true"),
            ("xv1.2.0", "true"),
        ):
            out = os.path.join(self.d, "out")
            if os.path.exists(out):
                os.remove(out)
            r = self.bash(kind, TAG=tag)
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            with open(out) as fh:
                self.assertEqual(fh.read(), f"dev={dev}\n", tag)

    def test_dev_push_is_the_same_in_every_build(self):
        wf = os.path.join(HERE, "..", "workflows")
        files = sorted(
            f
            for f in os.listdir(wf)
            if f.endswith("-docker-build-push.yaml")
            and f != "cloud-multi-doc-service-docker-build-push.yaml"
        ) + ["dev-live-update-image.yaml"]
        self.assertEqual(len(files), 12)

        def block(text):
            a = text.index("      - name: Image kind\n")
            return text[a : text.index("\n\n", text.index("- id: dev-auth", a))]

        with open(os.path.join(wf, "cloud-backend-docker-build-push.yaml")) as fh:
            want = block(fh.read())
        self.assertIn("if: steps.kind.outputs.dev == 'true'", want)
        self.assertRegex(
            want,
            r"\n +workload_identity_provider: projects/\d+/locations/global/workloadIdentityPools/[\w-]+-dev-pool/providers/github\n",
        )
        for f in files:
            with open(os.path.join(wf, f)) as fh:
                text = fh.read()
            self.assertEqual(block(text), want, f)
            self.assertEqual(
                text.count(
                    "\n    permissions:\n      contents: read\n      id-token: write"
                ),
                1,
                f,
            )
            self.assertEqual(text.count("    runs-on:"), 1, f)  # one job, the one granted
            self.assertIn("DEV: ${{ steps.kind.outputs.dev }}", text, f)
            self.assertNotIn("tags=us-central1", text, f)
            a = text.index("      - name: Image root")
            root_env = text[a : text.index("run: |", a)]
            if "Nuitka" in text:
                self.assertNotIn("TOKEN:", root_env, f)
                self.assertIn("gcloud auth configure-docker", text[a:], f)
            elif f == "dev-live-update-image.yaml":
                self.assertIn(
                    "TOKEN: ${{ steps.dev-auth.outputs.access_token }}\n", root_env, f
                )
            else:
                self.assertIn(
                    "TOKEN: ${{ steps.dev-auth.outputs.access_token || steps.auth.outputs.access_token }}\n",
                    root_env,
                    f,
                )

    def test_a_nuitka_build_logs_in_through_the_credential_helper(self):
        # its compile can outlast an access token, so no registry login may hold a static one
        wf = os.path.join(HERE, "..", "workflows")
        nuitka = []
        for f in sorted(
            f for f in os.listdir(wf) if f.endswith("-docker-build-push.yaml")
        ):
            with open(os.path.join(wf, f)) as fh:
                text = fh.read()
            if "Nuitka" not in text:
                continue
            nuitka.append(f)
            self.assertNotIn("oauth2accesstoken", text, f)
            self.assertNotIn("docker login", text, f)
            self.assertIn(
                "\n          gcloud auth configure-docker us-central1-docker.pkg.dev --quiet\n",
                text,
                f,
            )
            self.assertLess(
                text.index("uses: google-github-actions/setup-gcloud@"),
                text.index("gcloud auth configure-docker"),
                f,
            )
            self.assertIn(
                'gcloud auth configure-docker "${BASH_REMATCH[2]}-docker.pkg.dev" --quiet >&2 || exit 1',
                step(f, "Image roots"),
                f,
            )
        self.assertEqual(
            nuitka,
            [
                "on-prem-backend-docker-build-push.yaml",
                "on-prem-worker-unified-docker-build-push.yaml",
            ],
        )

    def test_every_caller_of_a_build_grants_id_token(self):
        # A nested job asking for id-token: write fails to start unless each caller up the chain grants it.
        wf = os.path.join(HERE, "..", "workflows")
        uses = re.compile(
            r"^    uses:\s*[\"']?\./\.github/workflows/([\w.-]+\.ya?ml)[\"']?\s*(?:#.*)?$",
            re.M,
        )
        asks = re.compile(r"^\s+id-token:\s*write\b", re.M)
        texts = {}
        for f in sorted(os.listdir(wf)):
            if f.endswith((".yaml", ".yml")):
                with open(os.path.join(wf, f)) as fh:
                    texts[f] = fh.read()

        def jobs(f):
            m = re.search(r"^jobs:\s*(?:#.*)?$", texts[f], re.M)
            if not m:
                # a file naming a local workflow must have a jobs section to search, or a caller goes unseen
                self.assertNotRegex(texts[f], r"\./\.github/workflows/", f)
                return []
            return re.split(r"\n(?=  [\w-]+:\s*(?:#.*)?\n)", texts[f][m.end() :])

        found = {}
        for f in texts:
            for j in jobs(f):
                m = uses.search(j)
                if m and asks.search(texts[m.group(1)]):
                    found.setdefault(f, []).append(j)
        self.assertEqual(
            {f: len(j) for f, j in found.items()},
            {
                "build-push.yaml": 11,
                "cut.yaml": 1,
                "dev-deploy.yaml": 2,
                "take-rc-build.yaml": 1,
            },
        )
        for f, js in found.items():
            for j in js:
                self.assertRegex(
                    j,
                    r"\n    permissions:\n(?:      [\w-]+: \w+.*\n)*      id-token: write",
                    (f, j[:40]),
                )

    LABELLED = '{"config": {"Labels": {"org.opencontainers.image.revision": "r1"}}, "rootfs": {}}'

    def skip(
        self,
        images,
        tag="v1.2.0-rc.1",
        err="",
        drift=False,
        config=LABELLED,
        config_err="",
    ):
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
        if config_err:
            with open(os.path.join(self.d, "config_err"), "w") as fh:
                fh.write(config_err)
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

    def test_skip_fails_when_an_image_config_cannot_be_read(self):
        r, out, copies = self.skip(
            {"c/runner:v1.2.0-rc.1": "sha256:a"}, config_err="ERROR: unauthorized"
        )
        self.assertEqual(r.returncode, 1)
        self.assertEqual((out, copies), ("revision=r1\n", ""))
        self.assertIn("cannot inspect c/runner:v1.2.0-rc.1@sha256:a", r.stdout)
        self.assertNotIn("was built from", r.stdout)

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
            # bash, not the default shell, so a failed inspect in a pipe fails the step
            self.assertRegex(block, r"\n        shell: bash(?: #.*)?\n", f)
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
        # a Nuitka build logs in with the credential helper instead of the token (a long compile outlives it)
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
        ):
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
            self.assertEqual(len(tags), text.count("tags="), f)
            want = (
                [["IMAGE_ROOT_CLOUD"], ["IMAGE_ROOT_CLOUD", "IMAGE_ROOT_ON_PREM"]]
                if f.startswith("cloud-")
                else [["IMAGE_ROOT_ON_PREM"]]
            )
            self.assertIn(tags, want, f)

    def test_every_step_that_derives_state_has_the_registry_token(self):
        # relstate reads the registries, and refuses without a token
        wf = os.path.join(HERE, "..", "workflows")
        steps = []
        for f in sorted(f for f in os.listdir(wf) if f.endswith(".yaml")):
            with open(os.path.join(wf, f)) as fh:
                text = fh.read()
            for job in re.split(r"\n(?=  [\w-]+:\n)", text.split("\njobs:\n", 1)[1]):
                head = job.split("\n    steps:\n")[0]
                for s in re.split(r"\n(?=      - )", job):
                    if re.search(
                        r"rs\.derive\(|relstate\.py|convgate\.py|import convgate|registry_tags",
                        s,
                    ):
                        steps.append(f"{f} {s.split(chr(10))[0].strip()}")
                        self.assertIn("RELSTATE_AR_TOKEN:", s + head, steps[-1])
        self.assertGreaterEqual(len(steps), 10, steps)

    def test_take_rc_build_holds_its_line_over_the_builds(self):
        # a job-level group frees the line once tagging ends, and a second run could tag while the builds still run
        with open(os.path.join(HERE, "..", "workflows", "take-rc-build.yaml")) as fh:
            head, jobs = fh.read().split("\njobs:\n", 1)
        self.assertIn(
            "\nconcurrency:\n  group: take-rc-build-${{ (startsWith(inputs.line, 'release/') "
            "&& inputs.line || format('release/{0}', inputs.line)) }}\n",
            head,
        )
        self.assertNotIn("concurrency:", jobs)

    def test_promote_and_publish_check_every_image_retag_copies(self):
        with open(
            os.path.join(HERE, "..", "workflows", "retag-docker-images.yaml")
        ) as fh:
            matrices = re.findall(r"\n        service:\n +\[([^\]]*)\]", fh.read())
        self.assertEqual(len(matrices), 2)
        for m in matrices:
            self.assertEqual(tuple(re.findall(r"[\w-]+", m)), rs.IMAGES)

    def test_missing_images_reads_the_target_kind(self):
        built = {"on-prem/backend", "on-prem/frontend", "cloud/runner"}
        with (
            mock.patch.object(rs, "TARGETS", rs.REPOS["unstract-cloud"][0]),
            mock.patch.object(
                rs, "registry_tags", lambda a: {"v1.2.0": {}} if a in built else {}
            ),
        ):
            self.assertEqual(
                rs.missing_images("on-prem", "v1.2.0"),
                [f"on-prem/{i}" for i in rs.IMAGES if i not in ("backend", "frontend")],
            )

    def test_a_failed_product_leaves_the_other_its_retag_and_publish(self):
        with open(os.path.join(HERE, "..", "workflows", "promote.yaml")) as fh:
            text = fh.read()
        jobs = {
            j.split(":")[0].strip(): j
            for j in re.split(r"\n(?=  [\w-]+:\n)", text.split("\njobs:\n", 1)[1])
        }
        # a product's key is set by its last step, so a product that fails at any step has none
        promote = jobs["promote"]
        self.assertIn("      cloud: ${{ steps.done.outputs.cloud }}\n", promote)
        self.assertIn("      on-prem: ${{ steps.done.outputs.on-prem }}\n", promote)
        last = re.split(r"\n(?=      - )", promote)[-1]
        self.assertIn("\n        id: done\n", last)
        self.assertNotIn("\n        if:", last)
        self.assertIn('echo "$TARGET=$STABLE" >> "$GITHUB_OUTPUT"', last)
        self.assertNotIn("{t}={stable}", promote)
        for job, need in (
            ("promoted", "products"),
            ("retag", "promoted"),
            ("publish", "retag"),
        ):
            self.assertIn(
                f"\n    if: ${{{{ !cancelled() && needs.{need}.result == 'success' }}}}\n",
                jobs[job],
                job,
            )

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
    """Forcing Promote passes a failed conflict listing, never a failed held-fix listing."""

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

    def test_every_product_promotes_the_pinned_oss_rc(self):
        # The OSS GA, which stabilizes the OSS line, comes from whichever product promotes the line first, on-prem
        # alone included: the OSS step runs for every product, before the cloud tag.
        with open(os.path.join(HERE, "..", "workflows", "promote.yaml")) as fh:
            wf = fh.read()
        start = wf.index("      - name: Promote the pinned OSS RC\n")
        step = wf[start : wf.index("      - name: ", start + 1)]
        self.assertNotIn("if:", step)
        self.assertIn("oss.py promote", step)
        self.assertLess(start, wf.index("      - name: GA commit and tag\n"))

    def test_promote_needs_the_rc_on_every_image(self):
        self.line("1.7", "v1.7.0-rc.1")
        self.write("reg-cloud_frontend.jsonl", "")  # frontend has no RC build
        self.blocked(
            self.promote(),
            "::error::cloud has no complete RC build of v1.7.0-rc.1: cloud/frontend lack it",
        )

    def test_promote_fails_a_product_with_no_rc_build(self):
        self.line("1.7", "v1.7.0-rc.1")
        dev_git(self.cloud, "commit", "-q", "--allow-empty", "-m", "rc")
        dev_git(self.cloud, "tag", "v1.7.0-rc.2")
        dev_git(
            self.cloud,
            "push",
            "-q",
            "origin",
            "main:refs/heads/release/1.7",
            "v1.7.0-rc.2",
        )
        self.blocked(
            self.promote("v1.7.0-rc.2"),
            "::error::cloud has no complete RC build of v1.7.0-rc.2: cloud/backend, cloud/frontend",
        )

    def test_promote_fails_closed(self):
        self.line("1.7", "v1.7.0-rc.1")
        self.write("prfail", "")
        self.blocked(self.promote(), "::error::cannot list open backport conflict PRs")
        self.assertEqual(
            self.forced(self.promote(FORCE="true", REASON="ship it")),
            "ship it; open conflict PRs: unchecked: listing failed",
        )

    def reg(self, tag, digest):  # a registry tag on cloud/backend only, no git tag
        with open(os.path.join(self.d, "reg.jsonl"), "a") as fh:
            fh.write(
                json.dumps(
                    {"digest": digest, "pushed_at": "2026-09-01T00:00:00Z", "tags": [tag]}
                )
                + "\n"
            )

    def test_promote_refuses_a_stable_tag_already_promoted(self):
        self.line("1.7", "v1.7.0-rc.1")
        self.reg("v1.7.0", "sha256:v1.7.0-rc.1")
        dev_git(self.cloud, "tag", "v1.7.0", "v1.7.0-rc.1")
        dev_git(self.cloud, "push", "-q", "origin", "v1.7.0")
        self.blocked(
            self.promote(),
            "::error::cloud/backend:v1.7.0 already exists (same digest: already promoted)",
        )
        self.assertIn(
            "gh workflow run publish.yaml -f version=v1.7.0 -f cloud=true",
            self.read("summary"),
        )

    def test_promote_resumes_a_stable_tag_whose_git_tag_was_deleted(self):
        # The retag landed but the git tag is gone: Promote redoes the GA commit and tag.
        self.line("1.7", "v1.7.0-rc.1")
        self.reg("v1.7.0", "sha256:v1.7.0-rc.1")
        r = self.promote()
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn(
            "::notice::cloud/backend:v1.7.0 already has v1.7.0-rc.1's digest", r.stdout
        )
        self.assertIn("new_tag=true\n", self.read("output"))

    def test_promote_after_the_line_moved(self):
        # A backport merged during QA: the RC is still promoted (its GA commit stays off the line).
        self.line("1.7", "v1.7.0-rc.1")
        dev_git(self.cloud, "commit", "-q", "--allow-empty", "-m", "fix during QA")
        dev_git(self.cloud, "push", "-q", "origin", "HEAD:refs/heads/release/1.7")
        r = self.promote()
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("new_tag=true\n", self.read("output"))

    @unittest.skipUnless(
        os.path.exists(os.path.join(HERE, "..", "..", rm.CHART)), "the cloud repo's chart"
    )
    def test_promote_ga_commit_and_tag(self):
        root = os.path.join(HERE, "..", "..")
        for f in (rm.CHART, rm.VALUES):
            os.makedirs(os.path.join(self.cloud, os.path.dirname(f)), exist_ok=True)
            with (
                open(os.path.join(root, f)) as src,
                open(os.path.join(self.cloud, f), "w") as out,
            ):
                out.write(src.read())
            dev_git(self.cloud, "add", f)
        dev_git(self.cloud, "commit", "-q", "-m", "chart")
        dev_git(self.cloud, "push", "-q", "origin", "main")
        self.line("1.7", "v1.7.0-rc.1")
        origin = self.repos["cloud"][0]
        rc = rm.git(origin, "rev-parse", "v1.7.0-rc.1^{commit}")
        tip = rm.git(origin, "rev-parse", "release/1.7")

        def ga_step(**env):
            return subprocess.run(
                ["bash", "-e", "-c", step("promote.yaml", "GA commit and tag")],
                cwd=self.cloud,
                env={
                    **os.environ,
                    "GITHUB_OUTPUT": os.path.join(self.d, "ga"),
                    "SHA": rc,
                    "STABLE": "v1.7.0",
                    "RC": "v1.7.0-rc.1",
                    "TARGET": "cloud",
                    **env,
                },
                capture_output=True,
                text=True,
            )

        r = ga_step(OSS_TAG="ee-v1.7.0")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        ga = rm.git(origin, "rev-parse", "v1.7.0^{commit}")
        self.assertEqual(self.read("ga"), f"ga={ga}\n")
        self.assertTrue(rm.is_ga_bump(origin, ga, rc, "v1.7.0"))
        self.assertEqual(
            rm.git(origin, "rev-parse", "release/1.7"), tip
        )  # never pushed to the line
        self.assertIn(
            "oss: ee-v1.7.0",
            rm.git(origin, "tag", "-l", "--format=%(contents)", "v1.7.0"),
        )
        # A rerun finds the tag on the GA commit and does not tag again.
        r = self.promote()
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("new_tag=false\n", self.read("output"))
        self.assertIn(f"ga={ga}\n", self.read("output"))
        # The guard: a second anchor line the sed also rewrites is refused, and nothing is tagged.
        dev_git(self.cloud, "checkout", "-q", "--detach", rc)
        with open(os.path.join(self.cloud, rm.VALUES), "a") as fh:
            fh.write("other: &UNSTRACT_APPS_VERSION v0\n")
        dev_git(self.cloud, "commit", "-q", "-am", "second anchor")
        r = ga_step(SHA=dev_git(self.cloud, "rev-parse", "HEAD"), STABLE="v1.7.9")
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn(
            "::error::HEAD is not the GA commit for v1.7.9", r.stderr + r.stdout
        )
        self.assertEqual(rm.git(origin, "tag", "-l", "v1.7.9"), "")

    def test_promote_refuses_a_stable_tag_at_another_digest(self):
        self.line("1.7", "v1.7.0-rc.1")
        self.reg("v1.7.0", "sha256:other")
        self.blocked(
            self.promote(),
            "::error::cloud/backend:v1.7.0 already exists with digest sha256:other, not "
            "sha256:v1.7.0-rc.1",
        )

    def test_promote_refuses_a_target_not_enabled(self):
        self.line("1.7", "v1.7.0-rc.1")  # cloud RCs only
        r = self.run_step(
            inline("promote.yaml", "Plan"),
            RC="v1.7.0-rc.1",
            TARGET="on-prem",
        )
        self.blocked(
            r, "::error::on-prem is not enabled on release/1.7 (enabled: ['cloud'])"
        )

    def test_promote_missing_pick_blocks_unless_forced(self):
        # A fix picked onto GA 1.6 after 1.7 was cut, not onto 1.7.
        self.line("1.6", "v1.6.0-rc.1", "v1.6.0")
        self.line("1.7", "v1.7.0-rc.1")
        with open(os.path.join(self.cloud, "y.txt"), "w") as fh:
            fh.write("y")
        dev_git(self.cloud, "add", "y.txt")
        dev_git(self.cloud, "commit", "-q", "-m", "[FIX] y (#5)")
        dev_git(self.cloud, "push", "-q", "origin", "main")
        fix = dev_git(self.cloud, "rev-parse", "HEAD")
        dev_git(self.cloud, "checkout", "-q", "-b", "pick", "origin/release/1.6")
        dev_git(self.cloud, "cherry-pick", "-x", fix)
        dev_git(self.cloud, "push", "-q", "origin", "pick:release/1.6")
        dev_git(self.cloud, "checkout", "-q", "main")
        self.write(
            "pulls.json",
            json.dumps(
                [
                    {
                        "number": 5,
                        "title": "[FIX] y",
                        "labels": [{"name": "backport/rc"}],
                    }
                ]
            ),
        )
        r = self.promote(GITHUB_SERVER_URL="")
        self.blocked(r, "::error::convergence gate: MISSING picks (summary above)")
        self.assertIn(f"MISSING original {fix[:12]}", r.stdout)
        self.assertIn(
            "### ⛔ Promote blocked · `v1.7.0-rc.1` · cloud", self.read("summary")
        )
        self.promote(GITHUB_SERVER_URL="https://github.com")
        self.assertIn(
            "### ⛔ Promote blocked · [`v1.7.0-rc.1`](https://github.com/Zipstack/unstract-cloud/releases/tag/v1.7.0-rc.1)"
            " · cloud",
            self.read("summary"),
        )
        self.assertEqual(
            self.forced(self.promote(FORCE="true", REASON="ship  it\nnow")), "ship it now"
        )

    def test_promote_order_blocks_unless_forced(self):
        self.line("1.6", "v1.6.0-rc.1")  # older, not GA
        self.line("1.7", "v1.7.0-rc.1")
        self.blocked(self.promote(), "::error::release/1.6 is not GA for cloud yet")
        self.assertEqual(
            self.forced(self.promote(FORCE="true", REASON="hotfix")), "hotfix"
        )

    def test_promote_held_oss_fixes_after_oss_ga(self):
        self.line("1.7", "v1.7.0-rc.1")  # no cloud GA yet: the cloud line is stabilizing
        oss_work = self.repos["oss"][1]
        r = self.promote("v1.7.0-rc.1")  # nothing held: passes
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        dev_git(
            oss_work, "tag", "ee-v1.7.0", "origin/release/1.7"
        )  # an earlier Promote's OSS step, then a failure
        dev_git(oss_work, "push", "-q", "origin", "ee-v1.7.0")
        dev_git(oss_work, "pull", "-q", "origin", "main")
        dev_git(oss_work, "commit", "-q", "--allow-empty", "-m", "fix: z (#9)")
        dev_git(oss_work, "push", "-q", "origin", "main")
        dev_git(oss_work, "fetch", "-q", "origin")
        dev_git(self.cloud, "commit", "-q", "--allow-empty", "-m", "[FIX] x (#9)")
        dev_git(self.cloud, "push", "-q", "origin", "main")
        self.write(
            "pulls.json",
            json.dumps(
                [{"number": 9, "title": "[FIX] x", "labels": [{"name": "backport/ga"}]}]
            ),
        )
        r = self.promote("v1.7.0-rc.1")
        self.blocked(r, "::error::pending picks")
        self.assertRegex(
            r.stdout,
            rf"::error::[0-9a-f]{{7}} \(ga, PR {re.escape(oss.OSS)}#9\) held for release/1\.7",
        )
        self.assertNotRegex(
            r.stdout, r"\(ga, PR #9\)"
        )  # the cloud line is still stabilizing: not checked

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
            self.cloud, "commit", "-q", "--allow-empty", "-m", "[FIX] x (#9)"
        )  # on main only: held for 1.7
        dev_git(self.cloud, "push", "-q", "origin", "main")
        self.write(
            "pulls.json",
            json.dumps(
                [{"number": 9, "title": "[FIX] x", "labels": [{"name": "backport/ga"}]}]
            ),
        )
        r = self.promote("v1.7.1-rc.1")
        self.blocked(r, "::error::pending picks")
        self.assertRegex(
            r.stdout, r"::error::[0-9a-f]{7} \(ga, PR #9\) held for release/1\.7"
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
                    r"::error::[0-9a-f]{7} \(ga, PR #9\) held for release/1\.7",
                    r.stdout,
                )
            ),
            1,
        )
        self.assertRegex(
            r.stdout,
            rf"::error::[0-9a-f]{{7}} \(ga, PR {re.escape(oss.OSS)}#9\) held for release/1\.7",
        )
        take = self.run_step(
            inline("take-rc-build.yaml", "Plan checks"),
            BRANCH="release/1.7",
            TARGETS="cloud",
        )  # Take RC lists the OSS-held fix too, and never blocks on it
        held = f"Held for confirmation on {oss.OSS} [`release/1.7`](https://github.com/{oss.OSS}/tree/release/1.7)"
        self.assertIn(held, self.read("notes.md"), take.stdout + take.stderr)
        self.assertIn(held, self.read("summary"))
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
            "::error::cannot list held backport/ga fixes",
        )
        self.assertIn("rerun Promote once GitHub answers", self.read("summary"))

    def test_take_rc_blocks_on_a_conflict_pr_unless_forced(self):
        self.line("1.7")
        self.prs(oss.OSS, "release/1.7")
        script = inline("take-rc-build.yaml", "Plan checks")
        dev_git(self.cloud, "checkout", "-q", "-b", "release/1.7", "origin/release/1.7")
        r = self.run_step(script, BRANCH="release/1.7", TARGETS="cloud")
        self.blocked(r, "::error::pending picks: open backport conflict PRs")
        self.assertIn(
            f"::error::Open backport conflict PR {oss.OSS}#40 on release/1.7", r.stdout
        )
        summary = self.read("summary")
        self.assertIn(f"⚠ Open backport conflict PRs: [{oss.OSS}#40]", summary)
        self.assertIn(
            "**Next:** resolve and merge or close each conflict PR, then run Take RC build again",
            summary,
        )
        self.assertFalse(os.path.exists(os.path.join(self.d, "notes.md")))
        r = self.run_step(
            script,
            BRANCH="release/1.7",
            TARGETS="cloud",
            FORCE="true",
            REASON="known gap",
        )
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn(
            f"::warning::Open backport conflict PR {oss.OSS}#40 on release/1.7", r.stdout
        )
        notes = self.read("notes.md")
        self.assertIn(f"⚠ Open backport conflict PRs: [{oss.OSS}#40]", notes)
        self.assertIn("Forced: known gap", notes)
        self.write("prfail", "")
        r = self.run_step(script, BRANCH="release/1.7", TARGETS="cloud")
        self.blocked(r, "::error::cannot list open backport conflict PRs")
        self.assertIn(
            "**Next:** rerun Take RC build once GitHub answers", self.read("summary")
        )
        r = self.run_step(
            script,
            BRANCH="release/1.7",
            TARGETS="cloud",
            FORCE="true",
            REASON="known gap",
        )
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn(
            "::warning::⚠ Open backport conflict PRs: unchecked, the listing failed",
            r.stdout,
        )

    def test_take_rc_blocks_on_prem_on_a_declared_fix_unless_forced(self):
        self.line("1.7")
        rows = {}
        for name, slug, n in (
            ("cloud", "Zipstack/unstract-cloud", 11),
            ("oss", oss.OSS, 12),
        ):
            work = self.repos[name][1]
            dev_git(work, "pull", "-q", "origin", "main")
            dev_git(work, "commit", "-q", "--allow-empty", "-m", f"[FIX] declared (#{n})")
            dev_git(work, "push", "-q", "origin", "main")
            dev_git(work, "fetch", "-q", "origin")
            sha = rm.git(work, "rev-parse", "HEAD")
            rows[slug] = [
                {
                    "number": n,
                    "title": "[FIX] declared",
                    "body": "Backport-also: 1.7\r\n",
                    "mergeCommit": {"oid": sha},
                }
            ]
            self.write(f"merged-{slug.replace('/', '_')}.json", json.dumps(rows[slug]))
        dev_git(self.cloud, "checkout", "-q", "-b", "release/1.7", "origin/release/1.7")
        script = inline("take-rc-build.yaml", "Plan checks")
        r = self.run_step(script, BRANCH="release/1.7", TARGETS="cloud")
        self.assertEqual(
            r.returncode, 0, r.stdout + r.stderr
        )  # a declaration holds on-prem builds only
        r = self.run_step(script, BRANCH="release/1.7", TARGETS="cloud,on-prem")
        self.blocked(r, "::error::declared fixes not yet on release/1.7")
        summary = self.read("summary")
        for slug, n in (("Zipstack/unstract-cloud", 11), (oss.OSS, 12)):
            self.assertIn(
                f"- {slug}#{n} [FIX] declared: pick it with `gh workflow run backport.yaml -R {slug} "
                f"-f commits={n} -f lines=1.7 -f patch_released_lines=true`, or remove the "
                f"`Backport-also: 1.7` line from PR #{n} if the fix is no longer needed",
                summary,
            )
        self.assertIn(
            "**Next:** pick each fix or remove its declaration, then run Take RC build again",
            summary,
        )
        self.assertIn(
            "oss-token pr list -R Zipstack/unstract --state merged", self.read("gh.log")
        )
        r = self.run_step(
            script,
            BRANCH="release/1.7",
            TARGETS="on-prem",
            FORCE="true",
            REASON="customer ask",
        )
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        notes = self.read("notes.md")
        self.assertIn("Zipstack/unstract-cloud#11 [FIX] declared", notes)
        self.assertIn("Forced: customer ask", notes)
        self.write("mergedfail", "")
        r = self.run_step(script, BRANCH="release/1.7", TARGETS="on-prem")
        self.blocked(r, "::error::cannot list declared fixes")
        self.assertIn(
            "**Next:** retry Take RC build once GitHub answers", self.read("summary")
        )
        r = self.run_step(
            script,
            BRANCH="release/1.7",
            TARGETS="on-prem",
            FORCE="true",
            REASON="gh down",
        )
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn(
            "::warning::\n⚠ Declared fixes: unchecked, the listing failed", r.stdout
        )

    def test_take_rc_passes_a_line_without_conflict_prs(self):
        self.line("1.7")
        dev_git(self.cloud, "checkout", "-q", "-b", "release/1.7", "origin/release/1.7")
        r = self.run_step(
            inline("take-rc-build.yaml", "Plan checks"),
            BRANCH="release/1.7",
            TARGETS="cloud",
        )
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertNotIn("conflict", r.stdout)


class LateTargetWorkflow(Workflow):
    """On-prem enabled after the cloud GA: built from the tip, and owed main fixes never block or reach the line."""

    def setUp(self):
        super().setUp()
        with open(os.path.join(self.cloud, "pyproject.toml"), "w") as fh:
            fh.write('unstract-platform-version = "ee-v1.7.0-rc.1"\n')
        dev_git(self.cloud, "add", "pyproject.toml")
        dev_git(self.cloud, "commit", "-q", "-m", "pin")
        dev_git(self.cloud, "push", "-q", "origin", "main")
        self.line("1.7", "v1.7.0-rc.3", "v1.7.0")  # cloud GA
        dev_git(self.cloud, "commit", "-q", "--allow-empty", "-m", "fix on main")
        dev_git(self.cloud, "push", "-q", "origin", "main")
        self.write(
            "pulls.json",
            json.dumps(
                [
                    {
                        "number": 5,
                        "title": "[FIX] y",
                        "labels": [{"name": "backport/rc"}],
                    }
                ]
            ),
        )
        dev_git(self.cloud, "checkout", "-q", "-b", "release/1.7", "origin/release/1.7")

    def take_rc(self):
        r = self.run_step(
            inline("take-rc-build.yaml", "Plan checks"),
            BRANCH="release/1.7",
            TARGETS="on-prem",
            FORCE="true",
            REASON="customer ask",
        )
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        notes = self.read("notes.md")
        r = self.run_step(
            inline("take-rc-build.yaml", "Plan version and targets"),
            BRANCH="release/1.7",
            TARGETS="on-prem",
        )
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        return notes, self.read("output")

    def built(self, tag):  # the on-prem images, pushed after the cloud GA
        self.write(
            "reg-on-prem_backend.jsonl",
            json.dumps(
                {"digest": "sha256:p", "pushed_at": "2026-09-02T00:00:00Z", "tags": [tag]}
            )
            + "\n",
        )

    def state(self):
        r = self.run_step(
            "import datetime as dt, json, relstate as rs\n"
            "print(json.dumps(rs.derive('.', dt.datetime(2026, 9, 3, tzinfo=dt.UTC))))\n"
        )
        self.assertEqual(r.returncode, 0, r.stderr)
        return json.loads(r.stdout)

    def test_unchanged_tip_reuses_its_rc_and_promotes_onto_the_cloud_ga(self):
        notes, out = self.take_rc()
        self.assertIn(
            "| [#5](https://github.com/Zipstack/unstract-cloud/pull/5) | [FIX] y | rc |",
            notes,
        )  # owed, shown
        self.assertIn(
            "dispatch Backport with its commit, `patch_released_lines=true` and `lines=1.7`",
            notes,
        )
        self.assertEqual(
            out,
            "tag=v1.7.0-rc.3\nbump=false\ntargets=on-prem\nwant=on-prem\nnewest=release/1.7\nchart=true\n",
        )
        self.built("v1.7.0-rc.3")
        st = self.state()
        self.assertEqual(st["branches"][0]["state"], "stabilized")
        self.assertEqual(st["backport_targets"]["rc"], [])
        r = self.run_step(
            inline("promote.yaml", "Plan"),
            RC="v1.7.0-rc.3",
            TARGET="on-prem",
        )
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        out = dict(line.split("=", 1) for line in self.read("output").splitlines())
        ga = dev_git(self.cloud, "rev-parse", "v1.7.0^{commit}")
        self.assertEqual(
            (out["stable"], out["sha"], out["new_tag"], out["forced"]),
            ("v1.7.0", ga, "false", ""),
        )

    def test_after_a_patch_pick_builds_the_next_patch_rc(self):
        dev_git(self.cloud, "commit", "-q", "--allow-empty", "-m", "pick")
        dev_git(self.cloud, "push", "-q", "origin", "HEAD:refs/heads/release/1.7")
        _, out = self.take_rc()
        self.assertIn("tag=v1.7.1-rc.1\nbump=true\ntargets=on-prem\n", out)
        self.built("v1.7.1-rc.1")
        dev_git(self.cloud, "tag", "v1.7.1-rc.1")
        dev_git(self.cloud, "push", "-q", "origin", "v1.7.1-rc.1")
        st = self.state()
        self.assertEqual(
            (st["branches"][0]["state"], st["branches"][0]["targets"]["on-prem"]["late"]),
            ("stabilized", True),
        )

    def test_take_rc_never_reopens_a_line(self):
        with open(os.path.join(HERE, "..", "workflows", "take-rc-build.yaml")) as fh:
            self.assertNotIn("reopen", fh.read())
        self.assertFalse(hasattr(oss, "reopen"))
        self.assertFalse(hasattr(rs, "reopens"))


class TakeRcVersion(Workflow):
    def checks(self, **env):
        return self.run_step(
            inline("take-rc-build.yaml", "Plan checks"), BRANCH="release/1.7", **env
        )

    def test_late_target_on_a_stabilized_line_is_refused_unless_forced(self):
        self.line("1.7", "v1.7.0-rc.1", "v1.7.0")  # cloud GA: stabilized
        r = self.checks(TARGETS="cloud,on-prem")
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn(
            "::error::release/1.7 is stabilized: adding on-prem here skips every main fix merged while the line was "
            "stabilized (none were picked). Cut the next line (release/1.8)",
            r.stdout,
        )
        r = self.checks(TARGETS="cloud,on-prem", FORCE="true", REASON="customer ask")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn(
            "::warning::Forced late target on-prem on release/1.7 (stabilized): customer ask",
            r.stdout,
        )

    def test_new_target_while_stabilizing_is_not_late(self):
        self.line("1.7", "v1.7.0-rc.1")
        r = self.checks(TARGETS="cloud,on-prem")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertNotIn("Forced late target", r.stdout)

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
            "tag=v1.7.0-rc.2\nbump=true\ntargets=cloud\nwant=cloud\nnewest=release/1.7\nchart=false\n",
        )

    def test_allocates_past_a_kept_rc_chart(self):
        # An abandon kept the on-prem RC chart 1.7.0-rc.1 and deleted its images: a re-cut must not reuse rc.1.
        self.line("1.7")
        dev_git(self.cloud, "checkout", "-q", "-b", "release/1.7", "origin/release/1.7")
        self.write("reg-on-prem_backend.jsonl", "")
        self.write(
            "reg-on-prem_unstract-platform.jsonl",
            '{"id": 1, "digest": "sha256:c", "pushed_at": "2026-09-01T00:00:00Z", "tags": ["1.7.0-rc.1"]}\n',
        )
        r = self.run_step(
            inline("take-rc-build.yaml", "Plan version and targets"),
            BRANCH="release/1.7",
            TARGETS="on-prem",
        )
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("tag=v1.7.0-rc.2\n", self.read("output"))
        self.assertIn("\nchart=true\n", self.read("output"))

    def test_plan_names_the_newest_line(self):
        self.line("1.7", "v1.7.0")
        self.line("1.8")
        dev_git(self.cloud, "checkout", "-q", "-b", "release/1.7", "origin/release/1.7")
        r = self.run_step(
            inline("take-rc-build.yaml", "Plan version and targets"),
            BRANCH="release/1.7",
            TARGETS="cloud",
        )
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("\nnewest=release/1.8\n", self.read("output"))

    def test_a_failed_rc_chart_fails_the_summary(self):
        def summary(chart, version="v1.7.1-rc.1"):
            out = os.path.join(self.d, "summary")
            with contextlib.suppress(FileNotFoundError):
                os.remove(out)
            r = subprocess.run(
                ["bash", "-e", "-c", step("take-rc-build.yaml", "Summary")],
                cwd=os.path.join(HERE, "..", ".."),
                env={
                    **os.environ,
                    "TAG": "v1.7.1-rc.1",
                    "BUILD": "on-prem",
                    "RESULT": "success",
                    "CHART": chart,
                    "CHART_VERSION": version,
                    "BRANCH": "release/1.7",
                    "NEWEST": "release/1.7",
                    "GITHUB_STEP_SUMMARY": out,
                },
                capture_output=True,
                text=True,
            )
            return r.returncode, self.read("summary")

        code, text = summary("success")
        self.assertEqual(code, 0)
        self.assertIn("On-prem RC chart `unstract-platform:v1.7.1-rc.1`: success", text)
        self.assertIn("QA tests", text)
        # A chart bumped before the v came back is reported under the version it was pushed as.
        self.assertIn(
            "unstract-platform:1.7.1-rc.1`: success", summary("success", "1.7.1-rc.1")[1]
        )
        code, text = summary("failure")
        self.assertEqual(code, 1)
        self.assertNotIn("QA tests", text)
        self.assertEqual(summary("skipped")[0], 0)

    def test_staging_is_left_alone_for_an_older_line(self):
        def summary(build, newest, **env):
            out = os.path.join(self.d, "summary")
            with contextlib.suppress(FileNotFoundError):
                os.remove(out)
            r = subprocess.run(
                ["bash", "-e", "-c", step("take-rc-build.yaml", "Summary")],
                cwd=os.path.join(HERE, "..", ".."),
                env={
                    **os.environ,
                    "TAG": "v1.7.1-rc.1",
                    "BUILD": build,
                    "RESULT": "success",
                    "BRANCH": "release/1.7",
                    "NEWEST": newest,
                    "GITHUB_STEP_SUMMARY": out,
                    **env,
                },
                capture_output=True,
                text=True,
            )
            self.assertEqual(r.returncode, 0, r.stderr)
            return self.read("summary")

        with open(os.path.join(HERE, "..", "workflows", "build-push.yaml")) as fh:
            (staging,) = set(
                re.findall(r"\n +app_name: (\S+)\n", fh.read())
            )  # the app the build deploys
        note = f"gh workflow run sync-argocd.yaml -f app_name={staging} -f target_revision=v1.7.1-rc.1"
        self.assertIn(
            "Staging not updated: it runs the newest line, `release/1.8`",
            summary("cloud", "release/1.8", GITHUB_SERVER_URL=""),
        )
        self.assertIn(note, summary("cloud on-prem", "release/1.8"))
        web = "https://github.com/Zipstack/unstract-cloud"
        self.assertIn(
            f"newest line, [`release/1.8`]({web}/tree/release/1.8). To deploy "
            f"[`v1.7.1-rc.1`]({web}/releases/tag/v1.7.1-rc.1) there anyway:",
            summary("cloud", "release/1.8", GITHUB_SERVER_URL="https://github.com"),
        )
        self.assertIn(
            note, summary("cloud", "release/1.8", GITHUB_SERVER_URL="https://github.com")
        )
        self.assertNotIn(note, summary("cloud", "release/1.7"))
        self.assertNotIn(note, summary("on-prem", "release/1.8"))
        with open(os.path.join(HERE, "..", "workflows", "take-rc-build.yaml")) as fh:
            text = fh.read()
        for wire in (
            "\n      newest: ${{ steps.plan.outputs.newest }}\n",  # the job output both of these read
            "\n      skip_argocd_deployment: ${{ inputs.skip_argocd_deployment || "
            "needs.take-rc.outputs.newest != needs.take-rc.outputs.branch }}\n",
            "\n      NEWEST: ${{ needs.take-rc.outputs.newest }}\n",
            "\n      branch: ${{ needs.line.outputs.branch }}\n",  # release/X.Y, as newest is
            "\n      BRANCH: ${{ needs.take-rc.outputs.branch }}\n",
        ):
            self.assertIn(wire, text)

    def test_patch_rc_on_a_ga_line(self):
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
            "tag=v1.7.1-rc.1\nbump=true\ntargets=cloud\nwant=cloud\nnewest=release/1.7\nchart=false\n",
        )

    def test_rerun_on_a_tagged_tip_builds_only_the_missing_target(self):
        # Tip tagged v1.7.1-rc.1 for both targets, on-prem built, cloud failed.
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
            "tag=v1.7.1-rc.1\nbump=false\ntargets=cloud\nwant=cloud on-prem\nnewest=release/1.7\nchart=true\n",  # on-prem built earlier: still push its chart
        )


@unittest.skipUnless(
    os.path.exists(os.path.join(HERE, "..", "workflows", "take-rc-build.yaml")),
    "take-rc-build.yaml is cloud-only",
)
class TakeRcPrerelease(unittest.TestCase):
    def test_lists_every_ticked_target(self):
        # A rerun builds only what an earlier run missed; the release it creates must still list every ticked target.
        with open(os.path.join(HERE, "..", "workflows", "take-rc-build.yaml")) as fh:
            wf = fh.read()
        self.assertIn("      want: ${{ steps.plan.outputs.want }}\n", wf)
        job = wf[wf.index("- name: Create the RC prerelease") :]
        self.assertIn(
            "TARGETS: ${{ needs.take-rc.outputs.want }}\n", job[: job.index("run: |")]
        )


@unittest.skipUnless(
    os.path.exists(os.path.join(HERE, "..", "workflows", "take-rc-build.yaml")),
    "the cloud repo's workflows",
)
class InputSteps(unittest.TestCase):
    """Each dispatch input step normalises through relmgr: a line to release/X.Y, a version tag to its leading v."""

    def run_step(self, workflow, name, **env):
        with tempfile.TemporaryDirectory() as d:
            out = os.path.join(d, "out")
            r = subprocess.run(
                ["bash", "-e", "-c", step(workflow, name)],
                cwd=os.path.join(HERE, "..", ".."),
                env={**os.environ, **env, "GITHUB_OUTPUT": out},
                capture_output=True,
                text=True,
            )
            with open(out, "a+") as fh:
                fh.seek(0)
                return r.returncode, fh.read(), r.stderr

    def test_take_rc_line(self):
        for line in ("1.7", "release/1.7"):
            self.assertEqual(
                self.run_step("take-rc-build.yaml", "Check line", LINE=line),
                (0, "branch=release/1.7\n", ""),
            )
        # Padded: the concurrency group is keyed on the raw input, so " 1.7 " must not pass as 1.7.
        for line in ("release/1.7.0", " 1.7 "):
            code, out, err = self.run_step("take-rc-build.yaml", "Check line", LINE=line)
            self.assertEqual((code, out), (1, ""))
            self.assertIn("::error::not a release line X.Y", err)

    def test_promote_rc(self):
        for rc in ("v1.7.0-rc.2", "1.7.0-rc.2"):
            self.assertEqual(
                self.run_step("promote.yaml", "RC tag", RC=rc),
                (0, "rc=v1.7.0-rc.2\n", ""),
            )

    def test_raw_input_feeds_only_its_check(self):
        # Every job reads the normalised output; the raw input is left to the names a run shows.
        for wf, raw, uses in (
            ("take-rc-build.yaml", "inputs.line", ("run-name:", "group:", "LINE:")),
            ("promote.yaml", "inputs.rc", ("run-name:", "RC:")),
            ("publish.yaml", "inputs.version", ("run-name:", "VERSION:")),
        ):
            with open(os.path.join(HERE, "..", "workflows", wf)) as fh:
                seen = sorted(
                    line.split()[0]
                    for line in fh
                    if raw in line and not line.lstrip().startswith("#")
                )
            self.assertEqual(seen, sorted(uses), wf)

    def test_retire_form(self):
        form = dispatch_inputs("retire.yaml")
        self.assertEqual(list(form), ["action", "line", "reason", "force", "dry_run"])
        self.assertEqual(
            form["action"],
            [
                'description: "What to retire"',
                "type: choice",
                "options:",
                f'- "{PAST_EOS}"',
                f'- "{ONE}"',
                f'- "{ABANDON}"',
                f'default: "{PAST_EOS}"',
            ],
        )
        self.assertEqual(
            form["force"][0],
            'description: "Force: retire a line that is still supported (on-prem in window, or a late target)"',
        )
        with open(os.path.join(HERE, "..", "workflows", "retire.yaml")) as fh:
            text = fh.read()
        for gone in ("abandon", "retire_line", "now"):
            self.assertNotIn(f"inputs.{gone}", text)
        self.assertIn("\n      FORCE: ${{ inputs.force }}\n", text)

    def test_retire_run_name(self):
        for action, line, dry, want in (
            (PAST_EOS, "", True, "Retire past end of support (dry run)"),
            (PAST_EOS, "", False, "Retire past end of support"),
            (
                "",
                "",
                False,
                "Retire past end of support",
            ),  # an API dispatch may omit action
            (ONE, "1.7", True, "Retire 1.7 (dry run)"),
            (ONE, "1.7", False, "Retire 1.7"),
            (ONE, "", False, "Retire (no line)"),
            (ABANDON, "1.7", True, "Abandon 1.7 (dry run)"),
            (ABANDON, "1.7", False, "Abandon 1.7"),
            (ABANDON, "", False, "Abandon (no line)"),
        ):
            ctx = {"inputs.action": action, "inputs.line": line, "inputs.dry_run": dry}
            self.assertEqual(run_name("retire.yaml", **ctx), want)
        self.assertEqual(
            run_name(
                "retire.yaml",
                **{
                    "inputs.action": ONE,
                    "inputs.line": "1.7",
                    "inputs.dry_run": True,
                    "inputs.force": True,
                },
            ),
            "Retire 1.7 (dry run) (forced)",
        )

    def test_advisory_sync_run_name(self):
        wf = "security-advisory-sync.yaml"
        self.assertEqual(run_name(wf), "Security advisory sync")  # schedule: no inputs
        self.assertEqual(
            run_name(
                wf, **{"github.event_name": "workflow_dispatch", "inputs.dry_run": False}
            ),
            "Security advisory sync",
        )
        self.assertEqual(
            run_name(
                wf, **{"github.event_name": "workflow_dispatch", "inputs.dry_run": True}
            ),
            "Security advisory sync (dry run)",
        )

    def test_forced_run_name(self):
        for wf, key, value, want in (
            (
                "take-rc-build.yaml",
                "inputs.line",
                "0.186",
                "Take RC · release/0.186 · cloud",
            ),
            (
                "promote.yaml",
                "inputs.rc",
                "v0.186.0-rc.2",
                "Promote v0.186.0-rc.2 · cloud",
            ),
        ):
            ctx = {key: value, "inputs.cloud": True, "inputs.force": False}
            self.assertEqual(run_name(wf, **ctx), want)
            self.assertEqual(
                run_name(wf, **{**ctx, "inputs.force": True}), want + " (forced)"
            )
            form = dispatch_inputs(wf)
            self.assertTrue(
                form["force"][0].startswith('description: "Force: overrides '), wf
            )
            self.assertEqual(
                form["reason"][0], 'description: "Reason (required with Force)"', wf
            )

    def test_backport_form(self):
        form = dispatch_inputs("backport.yaml")
        self.assertEqual(list(form), ["commits", "patch_released_lines", "lines"])
        self.assertIn("required: true", form["commits"])
        with open(os.path.join(HERE, "..", "workflows", "backport.yaml")) as fh:
            text = fh.read()
        for old in ("confirm_stabilized", "confirm-stabilized", "CONFIRM:"):
            self.assertNotIn(old, text)

    def test_backport_run_name(self):
        dispatch = {"github.event_name": "workflow_dispatch", "inputs.commits": "#12 #13"}
        self.assertEqual(
            run_name("backport.yaml", **dispatch), "Backport · #12 #13 → default lines"
        )
        self.assertEqual(
            run_name("backport.yaml", **dispatch, **{"inputs.lines": "0.186,0.188"}),
            "Backport · #12 #13 → 0.186,0.188",
        )
        self.assertEqual(
            run_name(
                "backport.yaml",
                **{
                    "github.event_name": "pull_request_target",
                    "github.event.pull_request.number": 7,
                },
            ),
            "record #7",
        )
        self.assertEqual(
            run_name(
                "backport.yaml", **{"github.event_name": "push", "github.sha": "abc123"}
            ),
            "picks abc123",
        )

    def test_publish_version(self):
        for v in ("v1.7.0", "1.7.0"):
            self.assertEqual(
                self.run_step("publish.yaml", "Version", VERSION=v),
                (0, "version=v1.7.0\n", ""),
            )


@unittest.skipUnless(
    os.path.exists(os.path.join(HERE, "..", "workflows", "cut.yaml")),
    "the cloud repo's workflows",
)
class CutPickLine(unittest.TestCase):
    """Cut's line input: X.Y or release/X.Y; empty takes relstate's next minor."""

    def pick(self, line):
        with tempfile.TemporaryDirectory() as d:
            work, bin_ = os.path.join(d, "work"), os.path.join(d, "bin")
            rm.git(d, "init", "-q", "--bare", os.path.join(d, "origin.git"))
            rm.git(d, "init", "-q", work)
            rm.git(work, "remote", "add", "origin", os.path.join(d, "origin.git"))
            os.makedirs(os.path.join(work, ".github"))
            os.symlink(HERE, os.path.join(work, ".github", "release"))
            os.makedirs(bin_)
            with open(
                os.path.join(bin_, "python3"), "w"
            ) as fh:  # relstate reads registries: stub it
                fh.write(
                    "#!/bin/sh\n"
                    'case "$1$2" in\n'
                    """.github/release/relstate.py) echo '{"branches": [], "next_minor": "1.8"}' ;;\n"""
                    "*used_tags*) echo ;;\n"
                    f'*) exec {sys.executable} "$@" ;;\n'
                    "esac\n"
                )
            os.chmod(os.path.join(bin_, "python3"), 0o755)
            out = os.path.join(d, "out")
            r = subprocess.run(
                ["bash", "-e", "-c", step("cut.yaml", "Pick line")],
                cwd=work,
                env={
                    **os.environ,
                    "PATH": f"{bin_}:{os.environ['PATH']}",
                    "LINE": line,
                    "GITHUB_OUTPUT": out,
                },
                capture_output=True,
                text=True,
            )
            with open(out, "a+") as fh:
                fh.seek(0)
                return r.returncode, fh.read(), r.stderr

    def test_line(self):
        self.assertEqual(self.pick("")[:2], (0, "line=1.8\n"))
        for line in ("1.9", "release/1.9"):
            self.assertEqual(self.pick(line)[:2], (0, "line=1.9\n"))
        code, out, err = self.pick("1.9.0")
        self.assertEqual((code, out), (1, ""))
        self.assertIn("::error::not a release line X.Y", err)


class TakeRcBump(Workflow):
    """Take RC's bump step on release/1.7."""

    CHART, VALUES = (
        "charts/unstract-platform/Chart.yaml",
        "charts/unstract-platform/values.yaml",
    )

    def setUp(self):
        super().setUp()
        os.makedirs(os.path.join(self.cloud, "charts", "unstract-platform"))
        self.chart("v0.1.0")
        dev_git(self.cloud, "add", "charts")
        dev_git(self.cloud, "commit", "-q", "-m", "chart")
        dev_git(self.cloud, "push", "-q", "origin", "main")
        self.line("1.7")
        dev_git(self.cloud, "checkout", "-q", "-b", "release/1.7", "origin/release/1.7")

    def chart(self, ver):
        with open(os.path.join(self.cloud, self.CHART), "w") as fh:
            fh.write(f'name: unstract-platform\nversion: {ver}\nappVersion: "{ver}"\n')
        with open(os.path.join(self.cloud, self.VALUES), "w") as fh:
            fh.write(f"tag: &UNSTRACT_APPS_VERSION {ver}\n")

    def bump(self, tag="v1.7.0-rc.1"):
        return subprocess.run(
            ["bash", "-e", "-c", step("take-rc-build.yaml", "Bump chart, push, tag")],
            cwd=self.cloud,
            env={
                **os.environ,
                "PATH": self.path,
                "PYTHONPATH": self.site,
                "TAG": tag,
                "BRANCH": "release/1.7",
                "GITHUB_WORKSPACE": self.cloud,
                "SLACK_URL": "",
            },
            capture_output=True,
            text=True,
        )

    def origin(self, *args):
        return rm.git(self.repos["cloud"][0], *args)

    def tagged(self, r, subject):
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        tip = self.origin("rev-parse", "release/1.7")
        self.assertEqual(self.origin("rev-parse", "v1.7.0-rc.1^{commit}"), tip)
        self.assertEqual(
            self.origin("log", "-1", "--format=%ae %s", tip),
            f"releases@unstract.com {subject}",
        )
        return tip

    def test_fresh_tip_bumps_the_chart(self):
        self.tagged(self.bump(), "release: chart v1.7.0-rc.1")
        chart = self.origin("show", f"release/1.7:{self.CHART}")
        self.assertRegex(
            chart, r'(?m)^version: v1\.7\.0-rc\.1\nappVersion: "v1\.7\.0-rc\.1"$'
        )
        self.assertEqual(
            self.origin("show", f"release/1.7:{self.VALUES}"),
            "tag: &UNSTRACT_APPS_VERSION v1.7.0-rc.1",
        )

    def test_already_bumped_tip_is_tagged_as_it_is(self):
        # An earlier run pushed the bump and stopped before the tag push.
        self.chart("v1.7.0-rc.1")
        dev_git(
            self.cloud,
            "-c",
            "user.email=releases@unstract.com",
            "commit",
            "-q",
            "-am",
            "release: chart v1.7.0-rc.1",
        )
        dev_git(self.cloud, "push", "-q", "origin", "HEAD:release/1.7")
        before = self.origin("rev-parse", "release/1.7")
        r = self.bump()
        self.assertEqual(self.tagged(r, "release: chart v1.7.0-rc.1"), before)
        self.assertIn("is already the bump commit for v1.7.0-rc.1", r.stdout)

    def test_chart_already_at_the_version_gets_an_empty_bump(self):
        self.chart("v1.7.0-rc.1")
        dev_git(self.cloud, "commit", "-q", "-am", "chart by hand")
        dev_git(self.cloud, "push", "-q", "origin", "HEAD:release/1.7")
        before = self.origin("rev-parse", "release/1.7")
        r = self.bump()
        tip = self.tagged(r, "release: chart v1.7.0-rc.1")
        self.assertEqual(self.origin("rev-parse", f"{tip}^"), before)
        self.assertEqual(self.origin("diff", "--name-only", before, tip), "")
        self.assertIn("made an empty bump commit", r.stdout)

    def test_rc_taken_after_plan_refuses_the_push(self):
        # Another run tagged v1.7.0-rc.1 between Plan and this step.
        dev_git(self.cloud, "tag", "v1.7.0-rc.1")
        before = self.origin("rev-parse", "release/1.7")
        r = self.bump()
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn(
            "::error::version moved after bump: v1.7.0-rc.1 -> v1.7.0-rc.2", r.stdout
        )
        self.assertEqual(self.origin("rev-parse", "release/1.7"), before)
        self.assertEqual(self.origin("tag", "-l", "v1.7.*"), "")


class PublishWorkflow(Workflow):
    """Publish's Changelog reads this repo and the OSS repo with one token, the release bot's."""

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

    def test_exclude_is_what_the_previous_stable_shipped(self):
        # Fix #5 merged on main and was picked into v1.6.0; v1.7.0 has it from main, so its notes drop #5.
        base = dev_git(self.cloud, "rev-parse", "HEAD")
        with open(os.path.join(self.cloud, "y.txt"), "w") as fh:
            fh.write("y")
        dev_git(self.cloud, "add", "y.txt")
        dev_git(self.cloud, "commit", "-q", "-m", "[FIX] y (#5)")
        fix = dev_git(self.cloud, "rev-parse", "HEAD")
        dev_git(self.cloud, "checkout", "-q", "-b", "release/1.6", base)
        dev_git(self.cloud, "cherry-pick", "-x", fix)
        dev_git(self.cloud, "tag", "v1.6.0")
        dev_git(self.cloud, "push", "-q", "origin", "release/1.6", "v1.6.0")
        dev_git(self.cloud, "checkout", "-q", "main")
        with open(os.path.join(self.d, "reg.jsonl"), "a") as fh:
            fh.write(
                '{"digest": "sha256:v1.6.0", "pushed_at": "2026-09-01T00:00:00Z", "tags": ["v1.6.0"]}\n'
            )
        self.release(None, "v1.7.0-rc.1", "v1.7.0")
        out, o = self.plan()
        self.assertEqual((o["prev"], o["exclude"]), ("v1.6.0", "5"), out)

    def test_oss_range_is_the_two_pins(self):
        self.release("ee-v1.6.0", "v1.6.0")
        self.release("ee-v1.7.0-rc.1", "v1.7.0-rc.1", "v1.7.0")
        log, out = self.plan()
        self.assertEqual((out["prev_oss"], out["oss"]), ("ee-v1.6.0", "ee-v1.7.0-rc.1"))
        self.assertNotIn("::warning::no OSS pin", log)

    def test_publish_needs_the_version_on_every_image(self):
        self.release("ee-v1.6.0", "v1.6.0")
        self.release("ee-v1.7.0-rc.1", "v1.7.0-rc.1", "v1.7.0")
        self.write("reg-cloud_runner.jsonl", "")  # its retag failed
        r = self.run_step(
            inline("publish.yaml", "Plan"),
            VERSION="v1.7.0",
            TARGET="cloud",
            OWNER_REPO="Zipstack/unstract-cloud",
        )
        self.assertEqual(r.returncode, 1)
        self.assertIn(
            "::error::cloud/runner lack v1.7.0: cloud has not promoted v1.7.0", r.stdout
        )

    def test_a_side_with_no_pin_skips_oss(self):
        self.release(None, "v1.6.0")
        self.release("ee-v1.7.0-rc.1", "v1.7.0-rc.1", "v1.7.0")
        log, out = self.plan()
        self.assertIn("::warning::no OSS pin at v1.6.0: OSS changelog skipped", log)
        self.assertEqual(
            (out["prev_oss"], out["oss"]), ("ee-v1.7.0-rc.1", "ee-v1.7.0-rc.1")
        )  # same pin: skipped

    def test_changelog_reads_both_repos_with_one_token(self):
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


@unittest.skipUnless(
    os.path.exists(os.path.join(HERE, "..", "workflows", "take-rc-build.yaml")),
    "the cloud repo's workflows",
)
class TakeRcGate(unittest.TestCase):
    """The Convergence gate step, against a stub convgate that exits with GATE_RC."""

    STUB = """import os, subprocess, sys
a = sys.argv[1:]
tagged = subprocess.run(["git", "rev-parse", "-q", "--verify", "refs/tags/" + os.environ["TAG"]], capture_output=True).returncode == 0
with open(a[a.index("--out") + 1], "a") as f:
    f.write(f"stub {a[a.index('--target') + 1]} annotate={a[a.index('--annotate') + 1]} tagged={tagged}\\n")
codes = os.environ["GATE_RC"].split()  # one for every target, or one per target in BUILD order
t = a[a.index("--target") + 1]
sys.exit(int(codes[os.environ["BUILD"].split().index(t)] if len(codes) > 1 else codes[0]))
"""

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.d = tmp.name
        self.repo = os.path.join(self.d, "repo")
        rm.git(self.d, "init", "-q", "-b", "main", self.repo)
        dev_git(self.repo, "commit", "-q", "--allow-empty", "-m", "tip")
        stub = os.path.join(self.repo, ".relmgr", ".github", "release")
        os.makedirs(stub)
        with open(os.path.join(stub, "convgate.py"), "w") as f:
            f.write(self.STUB)

    def gate(self, code, force="false", tags=""):
        for name in ("summary", "output", "notes.md", "preview.md"):
            with contextlib.suppress(FileNotFoundError):
                os.remove(os.path.join(self.d, name))
        r = subprocess.run(
            ["bash", "-e", "-c", step("take-rc-build.yaml", "Convergence gate")],
            cwd=self.repo,
            env={
                **os.environ,
                "TAG": "v1.7.1-rc.1",
                "BUILD": "cloud on-prem",
                "BRANCH": "release/1.7",
                "FORCE": force,
                "REASON": "known gap",
                "GATE_RC": str(code),
                "RUNNER_TEMP": self.d,
                "GITHUB_STEP_SUMMARY": os.path.join(self.d, "summary"),
                "GITHUB_OUTPUT": os.path.join(self.d, "output"),
            },
            capture_output=True,
            text=True,
        )
        self.assertEqual(
            rm.git(self.repo, "tag", "-l").strip(), tags
        )  # the gate's own tag never stays
        return r

    def read(self, name):
        try:
            with open(os.path.join(self.d, name)) as f:
                return f.read()
        except FileNotFoundError:
            return ""

    def test_a_clean_line_passes(self):
        r = self.gate(0)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(self.read("output"), "result=ok\n")
        self.assertEqual(
            self.read("preview.md"),
            "#### Promote preview · cloud\n\nstub cloud annotate=error tagged=True\n"
            "#### Promote preview · on-prem\n\nstub on-prem annotate=error tagged=True\n",
        )
        self.assertEqual(self.read("notes.md") + self.read("summary"), "")

    def test_missing_picks_fail(self):
        r = self.gate(2)
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn(
            "::error::convergence gate: MISSING picks; to override, rerun with force and a reason",
            r.stdout,
        )
        summary = self.read("summary")
        self.assertTrue(summary.startswith("### ⛔ No RC built · release/1.7\n"), summary)
        self.assertIn("stub cloud annotate=error tagged=True", summary)
        self.assertTrue(
            summary.endswith(
                "**Next:** pick or decline each MISSING pick, then run Take RC build again\n"
            ),
            summary,
        )
        self.assertEqual(self.read("output") + self.read("notes.md"), "")

    def test_force_passes_with_a_warning_and_a_notes_line(self):
        r = self.gate(2, force="true")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn(
            "::warning::convergence gate: MISSING picks, forced on: known gap", r.stdout
        )
        self.assertEqual(
            self.read("notes.md"),
            "Forced past the convergence gate (MISSING picks, see the Promote preview in the run summary): known gap\n\n",
        )
        self.assertIn("stub cloud annotate=warning", self.read("preview.md"))
        self.assertEqual(self.read("output"), "result=block\n")
        self.assertEqual(self.read("summary"), "")

    def test_a_gate_error_fails_even_when_forced(self):
        for force in ("false", "true"):
            r = self.gate(1, force=force)
            self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
            self.assertIn(
                "::error::convergence gate did not run (see the run log)", r.stdout
            )
            self.assertEqual(self.read("notes.md"), "")

    def test_a_gate_error_on_any_target_wins_over_missing_picks(self):
        for codes in ("1 2", "2 1"):
            r = self.gate(codes, force="true")
            self.assertEqual(r.returncode, 1, codes + r.stdout + r.stderr)
            self.assertIn(
                "::error::convergence gate did not run (see the run log)", r.stdout
            )
            self.assertEqual(self.read("notes.md"), "")

    def test_an_existing_tag_is_kept(self):
        dev_git(self.repo, "tag", "v1.7.1-rc.1")  # a rerun on a tagged tip
        r = self.gate(0, tags="v1.7.1-rc.1")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_the_gate_runs_before_the_tag_push(self):
        with open(os.path.join(HERE, "..", "workflows", "take-rc-build.yaml")) as fh:
            text = fh.read()
        self.assertLess(
            text.index("      - name: Convergence gate\n"),
            text.index("      - name: Bump chart, push, tag\n"),
        )
        gate = text.split("      - name: Convergence gate\n", 1)[1].split("\n\n", 1)[0]
        self.assertNotIn("continue-on-error", gate)
        self.assertNotIn("if:", gate.split("run: |", 1)[0])

    def test_a_forced_rc_says_promote_blocks_again(self):
        def next_line(force):
            with contextlib.suppress(FileNotFoundError):
                os.remove(os.path.join(self.d, "summary"))
            r = subprocess.run(
                ["bash", "-e", "-c", step("take-rc-build.yaml", "Summary")],
                cwd=os.path.join(HERE, "..", ".."),
                env={
                    **os.environ,
                    "TAG": "v1.7.1-rc.1",
                    "BUILD": "cloud",
                    "RESULT": "success",
                    "CHART": "skipped",
                    "BRANCH": "release/1.7",
                    "NEWEST": "release/1.7",
                    "FORCE": force,
                    "GITHUB_SERVER_URL": "",
                    "GITHUB_STEP_SUMMARY": os.path.join(self.d, "summary"),
                },
                capture_output=True,
                text=True,
            )
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            return next(
                x for x in self.read("summary").splitlines() if x.startswith("**Next:**")
            )

        with open(os.path.join(HERE, "..", "workflows", "take-rc-build.yaml")) as fh:
            job = fh.read().split("\n  summary:\n", 1)[1].split("\n    steps:\n", 1)[0]
        self.assertIn("\n      FORCE: ${{ inputs.force }}\n", job)
        self.assertEqual(
            next_line("false"), "**Next:** QA tests `v1.7.1-rc.1`, then run Promote."
        )
        self.assertEqual(
            next_line("true"),
            "**Next:** QA tests `v1.7.1-rc.1`, then run Promote. A gate forced here blocks Promote "
            "again unless forced there too; see the RC notes.",
        )

    def test_the_oss_pin_passes_force_and_fails_with_a_summary(self):
        bin_ = os.path.join(self.d, "bin")
        os.makedirs(bin_)
        with open(os.path.join(bin_, "python3"), "w") as f:
            f.write('#!/bin/sh\necho "$*" > "$RUNNER_TEMP/args"\nexit "$RC"\n')
        os.chmod(os.path.join(bin_, "python3"), 0o755)

        def pin(force, code):
            for name in ("summary", "args"):
                with contextlib.suppress(FileNotFoundError):
                    os.remove(os.path.join(self.d, name))
            return subprocess.run(
                ["bash", "-e", "-c", step("take-rc-build.yaml", "OSS pin")],
                cwd=self.repo,
                env={
                    **os.environ,
                    "PATH": f"{bin_}:{os.environ['PATH']}",
                    "BRANCH": "release/1.7",
                    "SLACK_URL": "",
                    "FORCE": force,
                    "REASON": "known gap",
                    "RC": str(code),
                    "RUNNER_TEMP": self.d,
                    "GITHUB_STEP_SUMMARY": os.path.join(self.d, "summary"),
                },
                capture_output=True,
                text=True,
            ).returncode

        self.assertEqual(pin("false", 1), 1)
        self.assertNotIn("--force", self.read("args"))
        self.assertIn("### ⛔ No RC built · release/1.7", self.read("summary"))
        self.assertIn(
            "**Next:** pick or decline each MISSING pick on the OSS line",
            self.read("summary"),
        )
        self.assertEqual(pin("true", 1), 1)
        self.assertIn(
            f"--force --reason known gap --notes {self.d}/notes.md", self.read("args")
        )


@unittest.skipUnless(
    os.path.exists(os.path.join(HERE, "..", "workflows", "take-rc-build.yaml")),
    "the cloud repo's workflows",
)
class TakeRcNotes(unittest.TestCase):
    """Take RC's notes reach the prerelease, which another runner writes."""

    GH = """#!/usr/bin/env python3
import os, shutil, sys
a = sys.argv[1:]
d = os.environ["RUNNER_TEMP"]
with open(os.path.join(d, "calls"), "a") as f:
    f.write(" ".join(a[:2]) + "\\n")
if a[:2] == ["release", "view"]:
    if "VIEW_BODY" not in os.environ:
        sys.exit("release not found")
    print(os.environ["VIEW_BODY"])
elif a[:2] in (["release", "edit"], ["release", "create"]):
    shutil.copy(a[a.index("--notes-file") + 1], os.path.join(d, "sent"))
"""

    NOTES = "Forced past X: known gap\n\nConflict PRs: #7"

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.d = tmp.name
        bin_ = os.path.join(self.d, "bin")
        os.makedirs(bin_)
        with open(os.path.join(bin_, "gh"), "w") as f:
            f.write(self.GH)
        os.chmod(os.path.join(bin_, "gh"), 0o755)
        self.path = bin_ + os.pathsep + os.environ["PATH"]

    def read(self, name):
        try:
            with open(os.path.join(self.d, name)) as f:
                return f.read()
        except FileNotFoundError:
            return ""

    def output(self, notes=None):
        if notes is not None:
            with open(os.path.join(self.d, "notes.md"), "w") as f:
                f.write(notes)
        out = os.path.join(self.d, "output")
        r = subprocess.run(
            ["bash", "-e", "-c", step("take-rc-build.yaml", "Notes output")],
            env={**os.environ, "RUNNER_TEMP": self.d, "GITHUB_OUTPUT": out},
            capture_output=True,
            text=True,
        )
        self.assertEqual(r.returncode, 0, r.stderr)
        head, rest = self.read("output").split("\n", 1)
        delim = head.removeprefix("notes<<")
        self.assertRegex(delim, r"^[0-9a-f]{32}$")
        self.assertTrue(rest.endswith(delim + "\n"), rest)
        return rest[: -len(delim) - 1]

    def prerelease(self, rc_notes, view_body=None, targets="cloud"):
        env = {
            **os.environ,
            "PATH": self.path,
            "TAG": "v1.7.1-rc.1",
            "SHA": "a" * 40,
            "OSS": "v0.9.0",
            "BRANCH": "release/1.7",
            "TARGETS": targets,
            "RC_NOTES": rc_notes,
            "RUNNER_TEMP": self.d,
            "GITHUB_REPOSITORY": "Zipstack/unstract-cloud",
            "GITHUB_SERVER_URL": "https://github.com",
            "GITHUB_RUN_ID": "42",
            "GITHUB_STEP_SUMMARY": os.path.join(self.d, "summary"),
        }
        env.pop("VIEW_BODY", None)
        if view_body is not None:
            env["VIEW_BODY"] = view_body
        r = subprocess.run(
            ["bash", "-e", "-c", step("take-rc-build.yaml", "Create the RC prerelease")],
            env=env,
            capture_output=True,
            text=True,
        )
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        return self.read("sent")

    SECTION = (
        "\n## Take RC notes\n\nFrom [Take RC run 42]"
        "(https://github.com/Zipstack/unstract-cloud/actions/runs/42).\n\n"
    )

    def test_the_output_carries_every_line(self):
        self.assertEqual(self.output("a: b\n\nc\n\n"), "a: b\n\nc\n")

    def test_no_notes_give_an_empty_output(self):
        self.assertEqual(self.output(), "")

    def test_the_outputs_are_wired_to_the_prerelease(self):
        with open(os.path.join(HERE, "..", "workflows", "take-rc-build.yaml")) as fh:
            wf = fh.read()
        self.assertIn("      notes: ${{ steps.notes.outputs.notes }}\n", wf)
        job = wf[wf.index("- name: Create the RC prerelease") :]
        self.assertIn(
            "RC_NOTES: ${{ needs.take-rc.outputs.notes }}\n", job[: job.index("run: |")]
        )

    def test_create_appends_the_notes(self):
        sent = self.prerelease(self.NOTES)
        self.assertTrue(sent.endswith(self.SECTION + self.NOTES + "\n"), sent)
        self.assertIn("release create", self.read("calls"))

    def test_create_without_notes_adds_no_heading(self):
        sent = self.prerelease("")
        self.assertNotIn("Take RC notes", sent)
        self.assertTrue(sent.endswith("> None: still v0.9.0.\n"), sent)

    def test_a_rerun_adds_new_notes_once(self):
        body = "| targets | cloud |\n\n## Enterprise changes"
        sent = self.prerelease(self.NOTES, view_body=body, targets="on-prem")
        self.assertEqual(
            sent,
            "| targets | cloud on-prem |\n\n## Enterprise changes"
            + self.SECTION
            + self.NOTES
            + "\n",
        )
        os.remove(os.path.join(self.d, "calls"))
        self.prerelease(self.NOTES, view_body=sent.rstrip("\n"), targets="on-prem")
        self.assertEqual(self.read("calls"), "release view\n")

    def test_a_rerun_with_nothing_new_does_not_edit(self):
        self.prerelease("", view_body="| targets | cloud |\n\nbody", targets="cloud")
        self.assertEqual(self.read("calls"), "release view\n")


class LintPrStep(unittest.TestCase):
    """The Classify PR step judges each PR against its own base."""

    def classify(self, title, labels, base, gh_exit=0, body="", files=(), files_exit=0):
        """labels: what the API returns now; the event payload's labels are a stale decoy. files: the PR's files,
        in the pulls files API's shape; the advice reads them and the PR itself.
        """
        with tempfile.TemporaryDirectory() as d:
            pr = {
                "base": {"ref": base},
                "head": {"ref": "dev"},
                "title": title,
                "labels": [{"name": n} for n in labels],
            }
            for name, data in (("labels", labels), ("pr", pr), ("files", [list(files)])):
                with open(os.path.join(d, name), "w") as fh:
                    json.dump(data, fh)
            with open(os.path.join(d, "gh"), "w") as fh:  # fake gh, jq already applied
                fh.write(f"""#!/bin/sh
echo "$*" >> "{d}/calls"
case "$*" in
  *"/issues/7/labels"*) cat "{d}/labels"; exit {gh_exit};;
  *"/pulls/7/files"*) cat "{d}/files"; exit {files_exit};;
  *"/pulls/7/commits"*) echo '[[{{"commit": {{"message": "x"}}}}]]';;
  *"/pulls/7") cat "{d}/pr";;
  *"/branches?per_page=100 --jq .[].name") echo release/0.186;;
  *"/git/trees/release/0.186?recursive=1") echo '{{"truncated": false, "tree": [{{"path": "backend/x.py"}}]}}';;
  *) exit 1;;
esac
""")
            os.chmod(os.path.join(d, "gh"), 0o755)
            r = subprocess.run(
                ["bash", "-e", "-c", step("lint-pr.yaml", "Classify PR")],
                cwd=os.path.join(HERE, "..", ".."),
                env={
                    **os.environ,
                    "PATH": f"{d}:{os.environ['PATH']}",
                    "TITLE": title,
                    "LABELS": json.dumps(["main-only", "backport/rc"]),
                    "GITHUB_REPOSITORY": "Zipstack/unstract-cloud",
                    "PR": "7",
                    "BASE": base,
                    "BODY": body,
                    "GITHUB_STEP_SUMMARY": os.path.join(d, "summary"),
                    "GITHUB_OUTPUT": os.path.join(d, "output"),
                },
                capture_output=True,
                text=True,
            )
            with open(os.path.join(d, "calls")) as fh:
                self.assertEqual(
                    fh.readline(),
                    "api repos/Zipstack/unstract-cloud/issues/7/labels?per_page=100 --jq [.[].name]\n",
                )
            return r.returncode, r.stdout

    def test_a_decided_label_differing_warns_only(self):
        docs = [{"filename": "docs/x.md"}, {"filename": ".github/workflows/y.yaml"}]
        rc, out = self.classify("UN-1 [FIX] x", ["backport/rc"], "main", files=docs)
        self.assertEqual(rc, 0, out)
        self.assertIn(
            "::warning title=Lint PR::the advice is `main-only` (only docs, tests or repo tooling change; "
            "none ships); this PR has backport/rc",
            out,
        )

    def test_a_suggestion_is_never_checked(self):
        # The code is on release/0.186, so the advice only suggests backport/rc: main-only is the author's call.
        rc, out = self.classify(
            "UN-1 [FIX] x", ["main-only"], "main", files=[{"filename": "backend/x.py"}]
        )
        self.assertEqual((rc, out), (0, "class=none\n"))

    def test_a_failed_advice_lookup_neither_fails_nor_warns(self):
        rc, out = self.classify("UN-1 [FIX] x", ["main-only"], "main", files_exit=1)
        self.assertEqual(rc, 0, out)
        self.assertIn("::notice title=Lint PR::label advice unavailable", out)
        self.assertNotIn("::warning", out)

    def test_a_malformed_declaration_fails(self):
        rc, out = self.classify(
            "UN-1 [FIX] x",
            ["main-only"],
            "main",
            body="x\r\nBackport-also: release/0.186\r\n",
        )
        self.assertEqual(rc, 1, out)
        self.assertIn(
            "::error title=Lint PR::malformed `Backport-also: release/0.186`: write exactly "
            "`Backport-also: X.Y`",
            out,
        )
        rc, out = self.classify(
            "UN-1 [FIX] x", ["backport/rc"], "main", body="Backport-also: 0.186\r\n"
        )
        self.assertEqual(rc, 0, out)
        # Backport never picks a main-only PR, so a declaration there could never be met.
        rc, out = self.classify(
            "UN-1 [FIX] x", ["main-only"], "main", body="Backport-also: 0.186\r\n"
        )
        self.assertEqual(rc, 1, out)
        self.assertIn(
            "::error title=Lint PR::`main-only` with a `Backport-also` line", out
        )

    def test_the_newest_event_run_reports(self):
        with open(os.path.join(HERE, "..", "workflows", "lint-pr.yaml")) as fh:
            self.assertIn(
                "\nconcurrency:\n  group: lint-pr-${{ github.event.pull_request.number }}\n"
                "  cancel-in-progress: true\n",
                fh.read(),
            )

    def test_a_failed_label_read_fails_the_step(self):
        # A release base: there an empty label list would pass, so only the failed read can fail the step.
        rc, out = self.classify("UN-1 [FIX] x", [], "release/0.186", gh_exit=1)
        self.assertEqual(rc, 1, out)
        self.assertIn("could not read this PR's labels", out)
        self.assertNotIn("class=", out)

    def test_a_release_failure_omits_the_main_label_menu(self):
        rc, out = self.classify("fix: x", [], "release/0.186")
        self.assertEqual(rc, 1, out)
        self.assertIn("no recognised '[TYPE]'", out)
        self.assertNotIn("A PR into main needs", out)
        self.assertIn("Title: `[TYPE] text`", out)

    def test_a_main_pr_needs_a_backport_label(self):
        rc, out = self.classify("UN-1 [FIX] x", [], "main")
        self.assertEqual(rc, 1, out)
        self.assertIn("::error title=Lint PR::no backport label", out)
        self.assertIn("`main-only`: keep it on main", out)
        self.assertEqual(
            self.classify("UN-1 [FIX] x", ["main-only"], "main"), (0, "class=none\n")
        )

    def test_calls_only_what_every_relmgr_has(self):
        # The rule is read from main, and release lines keep older copies of this step: both sides must accept these calls.
        body = step("lint-pr.yaml", "Classify PR")
        self.assertEqual(
            re.findall(r"relmgr\.\w+\([^)]*\)", body),
            [
                "relmgr.pr_fix_class(title, labels)",
                'relmgr.release_only_refusal(os.environ["BASE"], labels)',
            ],
        )

    def test_a_release_pr_needs_none_and_refuses_main_only(self):
        rc, out = self.classify("UN-1 [FIX] x", [], "release/0.186")
        self.assertEqual(rc, 0, out)  # the label advice only warns
        self.assertTrue(out.startswith("class=none\n"), out)
        rc, out = self.classify("UN-1 [FIX] x", ["main-only"], "release/0.186")
        self.assertEqual(rc, 1, out)
        self.assertIn("label `main-only` is for PRs into main", out)

    def test_one_run_names_a_bad_title_and_a_missing_label(self):
        rc, out = self.classify("fix: x", [], "main")
        self.assertEqual(rc, 1, out)
        self.assertIn("::error title=Lint PR::no recognised '[TYPE]'", out)
        self.assertIn("%0Ano backport label", out)


class ReleaseBranchCiLabels(unittest.TestCase):
    """Release-branch-only is read from the PR's live labels."""

    WF = os.path.join(HERE, "..", "workflows", "release-branch-ci.yaml")

    def test_each_label_reader_grants_the_read(self):
        # A private repo answers 403 to the issue labels API for a PR without it.
        for wf in ("release-branch-ci.yaml", "lint-pr.yaml"):
            with open(os.path.join(HERE, "..", "workflows", wf)) as fh:
                self.assertRegex(
                    fh.read().split("\njobs:", 1)[0], r"\n  pull-requests: read", wf
                )

    def labels(self, answer, gh_exit=0):
        with tempfile.TemporaryDirectory() as d:
            with open(os.path.join(d, "gh"), "w") as fh:  # fake gh: jq already applied
                fh.write(
                    f'#!/bin/sh\necho "$*" >> "{d}/calls"\necho {answer}\nexit {gh_exit}\n'
                )
            os.chmod(os.path.join(d, "gh"), 0o755)
            r = subprocess.run(
                ["bash", "-e", "-c", step("release-branch-ci.yaml", "Labels")],
                env={
                    **os.environ,
                    "PATH": f"{d}:{os.environ['PATH']}",
                    "GITHUB_REPOSITORY": "o/r",
                    "PR": "7",
                    "GITHUB_OUTPUT": os.path.join(d, "output"),
                },
                capture_output=True,
                text=True,
            )
            with open(os.path.join(d, "calls")) as fh:
                self.assertEqual(
                    fh.read(),
                    "api repos/o/r/issues/7/labels?per_page=100 "
                    '--jq any(.[]; .name == "release-branch-only")\n',
                )
            out = os.path.join(d, "output")
            return r.returncode, r.stdout, open(out).read() if os.path.exists(out) else ""

    def test_the_live_label_reaches_both_steps(self):
        self.assertEqual(self.labels("true"), (0, "", "rbo=true\n"))
        self.assertEqual(self.labels("false"), (0, "", "rbo=false\n"))
        with open(self.WF) as fh:
            wf = fh.read()
        self.assertEqual(
            wf.count("RBO_LABEL: ${{ steps.labels.outputs.rbo == 'true' }}\n"), 2
        )
        self.assertNotIn("pull_request.labels", wf)

    def test_a_failed_label_read_fails_the_step(self):
        rc, out, written = self.labels("true", gh_exit=1)
        self.assertEqual(rc, 1, out)
        self.assertIn("could not read this PR's labels", out)
        self.assertEqual(written, "")

    def test_the_newest_pr_event_run_reports(self):
        with open(self.WF) as fh:
            self.assertIn(
                "\nconcurrency:\n  group: release-branch-ci-${{ github.event.pull_request.number || github.run_id }}\n"
                "  cancel-in-progress: ${{ github.event_name == 'pull_request' }}\n",
                fh.read(),
            )


@unittest.skipUnless(
    os.path.exists(os.path.join(HERE, "..", "workflows", "take-rc-build.yaml")),
    "take-rc-build.yaml and promote.yaml are cloud-only",
)
@unittest.skipUnless(shutil.which("jq"), "needs jq")
class NoRetireRunning(unittest.TestCase):
    """Take RC build and Promote refuse while a real Retire run is unfinished."""

    def run_check(self, wf, runs, gh_exit=0):
        with tempfile.TemporaryDirectory() as d:
            with open(os.path.join(d, "runs.json"), "w") as fh:
                json.dump({"workflow_runs": runs}, fh)
            with open(
                os.path.join(d, "gh"), "w"
            ) as fh:  # fake gh: applies --jq to runs.json
                fh.write(
                    f'#!/bin/sh\n[ {gh_exit} = 0 ] || exit {gh_exit}\necho "$1 $2" >> "{d}/calls"\n'
                    f'jq -r "$4" "{d}/runs.json"\n'
                )
            os.chmod(os.path.join(d, "gh"), 0o755)
            r = subprocess.run(
                ["bash", "-e", "-c", step(wf, "No Retire running")],
                env={
                    **os.environ,
                    "PATH": f"{d}:{os.environ['PATH']}",
                    "GITHUB_REPOSITORY": "o/r",
                },
                capture_output=True,
                text=True,
            )
            calls = open(os.path.join(d, "calls")).read() if gh_exit == 0 else ""
            return r.returncode, r.stdout, calls

    # display_title is retire.yaml's run-name.
    DRY = {
        "status": "in_progress",
        "display_title": "Abandon 1.7 (dry run)",
        "html_url": "https://x/1",
    }
    DONE = {
        "status": "completed",
        "display_title": "Retire 1.6",
        "html_url": "https://x/2",
    }
    REAL = {
        "status": "queued",
        "display_title": "Retire 1.7 (forced)",
        "html_url": "https://x/3",
    }

    def test_a_real_retire_refuses_and_a_dry_one_does_not(self):
        for wf in ("take-rc-build.yaml", "promote.yaml"):
            rc, out, calls = self.run_check(wf, [self.DRY, self.DONE])
            self.assertEqual(rc, 0, (wf, out))
            self.assertEqual(
                calls, "api repos/o/r/actions/workflows/retire.yaml/runs?per_page=100\n"
            )
            rc, out, _ = self.run_check(wf, [self.DRY, self.DONE, self.REAL])
            self.assertEqual(rc, 1, (wf, out))
            self.assertIn("a Retire run is unfinished", out)
            self.assertIn("https://x/3", out)
            self.assertNotIn("https://x/1", out)

    def test_a_failed_run_list_refuses(self):
        for wf in ("take-rc-build.yaml", "promote.yaml"):
            rc, out, _ = self.run_check(wf, [], gh_exit=1)
            self.assertEqual(rc, 1, (wf, out))
            self.assertIn("could not list the Retire runs", out)

    def test_each_caller_grants_the_read(self):
        for wf in ("take-rc-build.yaml", "promote.yaml"):
            with open(os.path.join(HERE, "..", "workflows", wf)) as fh:
                self.assertRegex(fh.read().split("\njobs:", 1)[0], r"\n  actions: read")
        with open(os.path.join(HERE, "..", "workflows", "cut.yaml")) as fh:
            rc_job = fh.read().split("\n  rc:\n", 1)[1]
        self.assertRegex(rc_job.split("uses:", 1)[0], r"\n      actions: read")


if __name__ == "__main__":
    unittest.main()
