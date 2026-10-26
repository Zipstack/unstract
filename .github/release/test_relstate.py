"""Synthetic-repo tests for relstate (derive 1-11, cutover fallback 12, retired-line history 13, tip_rc 14, summary 15, tip_rc Slack link 20, Release-branch-only line in a squash message 21, abandon_plan 16-17, pr_fix_class 18, revert titles 18b, ahead_of_ga 19, promote order per target 22, enable a target on the newest line only 23, already_bumped 24, promoted from the build artifact 25, OSS repo config 26 (ee- git tags, plain v* ignored, lines kept while the branch exists), next_minor past a stable tag on main 27, bump with no chart 28, retire_line refusals and the retired line's minor 29, RC allocation past registry RCs 30, a reused minor past its kept RC 31, shallow clone refused 32, conflict-marker grep error 33, a revert of another line's pick 34, release-branch CI commit selection 35, backport head names 36, unknown repo config 37). Run: python test_relstate.py"""

import contextlib
import datetime as dt
import io
import os
import tempfile
import unittest

os.environ["GITHUB_REPOSITORY"] = (
    "Zipstack/unstract-cloud"  # relstate loads the cloud config, whatever the runner sets
)
import relmgr as rm
import relstate as rs

# Isolate from the user's git config (signing, noprefix, hooks...).
os.environ.update(GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_NOSYSTEM="1")
os.environ.pop("GITHUB_OUTPUT", None)
NOW = dt.datetime(2026, 9, 29, tzinfo=dt.UTC)
CUT = {"branch": "release/1.5", "line": "1.5"}


def ago(days):
    return (NOW - dt.timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%SZ")


class Scenario(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.repo, self.reg, self.n = self._tmp.name, {}, 0
        rm.git(self.repo, "init", "-q", "-b", "main")
        self.commit("base")

    def g(self, *args):
        return rm.git(
            self.repo, "-c", "user.name=Dev", "-c", "user.email=dev@example.com", *args
        )

    def commit(self, msg, branch="main"):
        if branch != "main":
            self.g("checkout", "-q", branch)
        self.g("commit", "-q", "--allow-empty", "-m", msg)
        if branch != "main":
            self.g("checkout", "-q", "main")
        return self.g("rev-parse", branch)

    def cut(self, line):
        self.g("branch", f"release/{line}", "main")
        return self.commit(f"work on {line}", f"release/{line}")

    def push(self, artifact, tag, days=1, git_ref=None):
        if git_ref:
            self.g("tag", tag, git_ref)
        self.n += 1
        self.reg.setdefault(artifact, {})[tag] = {
            "digest": f"sha256:{self.n:064x}",
            "pushed_at": ago(days),
        }

    def state(self):
        return rs.derive(self.repo, NOW, lambda a: self.reg.get(a, {}))

    def branch(self, st, name):
        return next(b for b in st["branches"] if b["branch"] == name)

    def ga(self, artifact, tag):
        return {"tag": tag, **self.reg[artifact][tag]}

    # Scenarios build on each other as the table does.
    def s1(self):
        self.cut("1.5")
        self.push("cloud/release", "v1.5.0-rc.1", git_ref="release/1.5")

    def s2(self):
        self.s1()
        self.push("cloud/release", "v1.5.0", git_ref="release/1.5")

    def s3(self):
        self.s2()
        self.push("on-prem/release", "v1.5.0-rc.3", git_ref="release/1.5")

    def s4(self, chart_days=10):
        self.s3()
        self.push("on-prem/chart", "v1.5.1", days=chart_days)

    def s6(self, chart_days=10):
        self.s4(chart_days)
        self.cut("1.6")
        self.push("cloud/release", "v1.6.0-rc.1", git_ref="release/1.6")
        self.push("cloud/release", "v1.6.0", git_ref="release/1.6")

    def cloud_after_2(self, state):
        ga = self.ga("cloud/release", "v1.5.0")
        return {"state": state, "rcs": ["v1.5.0-rc.1"], "ga": ga, "promoted": ga}

    def onprem(self, state, chart=True):
        return {
            "state": state,
            "rcs": ["v1.5.0-rc.3"],
            "ga": self.ga("on-prem/chart", "v1.5.1") if chart else None,
            "promoted": None,
        }

    def test_1_cut_with_cloud_rc(self):
        self.s1()
        st = self.state()
        self.assertEqual(
            self.branch(st, "release/1.5"),
            {
                **CUT,
                "state": "stabilizing",
                "enabled": ["cloud"],
                "next_rc": None,
                "tip_rc": "v1.5.0-rc.1",
                "ahead_of_ga": None,
                "targets": {
                    "cloud": {
                        "state": "stabilizing",
                        "rcs": ["v1.5.0-rc.1"],
                        "ga": None,
                        "promoted": None,
                    }
                },
            },
        )
        self.assertEqual(st["backport_targets"]["fix"], ["release/1.5"])
        self.assertEqual(st["supported"], {"cloud": ["release/1.5"], "on-prem": []})

    def test_2_cloud_ga(self):
        self.s2()
        st = self.state()
        self.assertEqual(
            self.branch(st, "release/1.5"),
            {
                **CUT,
                "state": "stabilized",
                "enabled": ["cloud"],
                "next_rc": None,
                "tip_rc": "v1.5.0-rc.1",
                "ahead_of_ga": 0,
                "targets": {"cloud": self.cloud_after_2("stabilized")},
            },
        )
        self.assertEqual(
            st["backport_targets"],
            {
                "fix": [],
                "security_critical": [
                    {"branch": "release/1.5", "needs_rm_confirmation": True}
                ],
            },
        )

    def test_3_onprem_rc_reopens_branch(self):
        self.s3()
        st = self.state()
        self.assertEqual(
            self.branch(st, "release/1.5"),
            {
                **CUT,
                "state": "stabilizing",
                "enabled": ["cloud", "on-prem"],
                "next_rc": None,
                "tip_rc": "v1.5.0-rc.1",
                "ahead_of_ga": 0,
                "targets": {
                    "cloud": self.cloud_after_2("stabilized"),
                    "on-prem": self.onprem("stabilizing", chart=False),
                },
            },
        )
        self.assertEqual(st["backport_targets"]["fix"], ["release/1.5"])

    def test_4_both_stabilized(self):
        self.s4()
        st = self.state()
        self.assertEqual(
            self.branch(st, "release/1.5"),
            {
                **CUT,
                "state": "stabilized",
                "enabled": ["cloud", "on-prem"],
                "next_rc": None,
                "tip_rc": "v1.5.0-rc.1",
                "ahead_of_ga": 0,
                "targets": {
                    "cloud": self.cloud_after_2("stabilized"),
                    "on-prem": self.onprem("stabilized"),
                },
            },
        )
        self.assertEqual(st["supported"]["on-prem"], ["release/1.5"])

    def test_5_onprem_window_over(self):
        self.s4(chart_days=200)
        st = self.state()
        self.assertEqual(
            self.branch(st, "release/1.5"),
            {
                **CUT,
                "state": "stabilized",
                "enabled": ["cloud", "on-prem"],
                "next_rc": None,
                "tip_rc": "v1.5.0-rc.1",
                "ahead_of_ga": 0,
                "targets": {
                    "cloud": self.cloud_after_2("stabilized"),
                    "on-prem": self.onprem("past-eos"),
                },
            },
        )
        self.assertEqual(st["supported"], {"cloud": ["release/1.5"], "on-prem": []})
        self.assertEqual(st["retire"], [])

    def test_6_newer_cloud_ga(self):
        self.s6()
        st = self.state()
        self.assertEqual(
            self.branch(st, "release/1.5"),
            {
                **CUT,
                "state": "stabilized",
                "enabled": ["cloud", "on-prem"],
                "next_rc": None,
                "tip_rc": "v1.5.0-rc.1",
                "ahead_of_ga": 0,
                "targets": {
                    "cloud": self.cloud_after_2("past-eos"),
                    "on-prem": self.onprem("stabilized"),
                },
            },
        )
        self.assertEqual(
            st["supported"], {"cloud": ["release/1.6"], "on-prem": ["release/1.5"]}
        )

    def test_7_retire(self):
        self.s6(chart_days=200)
        st = self.state()
        self.assertEqual(
            self.branch(st, "release/1.5"),
            {
                **CUT,
                "state": "past-eos",
                "enabled": ["cloud", "on-prem"],
                "next_rc": None,
                "tip_rc": "v1.5.0-rc.1",
                "ahead_of_ga": 0,
                "targets": {
                    "cloud": self.cloud_after_2("past-eos"),
                    "on-prem": self.onprem("past-eos"),
                },
            },
        )
        self.assertEqual(st["retire"], ["release/1.5"])
        self.assertEqual(st["supported"], {"cloud": ["release/1.6"], "on-prem": []})

    def test_7b_onprem_newest_six(self):
        for y in range(1, 9):  # 1.1 .. 1.8, each with an on-prem chart inside the window
            self.cut(f"1.{y}")
            self.push("on-prem/release", f"v1.{y}.0-rc.1", git_ref=f"release/1.{y}")
            self.push("on-prem/chart", f"v1.{y}.0", days=10)
        self.cut("1.9")  # no on-prem GA: does not count toward the six
        self.push("on-prem/release", "v1.9.0-rc.1", git_ref="release/1.9")
        st = self.state()
        self.assertEqual(
            st["supported"]["on-prem"], [f"release/1.{y}" for y in range(9, 2, -1)]
        )
        self.assertEqual(st["retire"], ["release/1.2", "release/1.1"])

    def test_8_cut_no_artifacts(self):
        self.s4()
        self.cut("1.7")
        st = self.state()
        self.assertEqual(
            self.branch(st, "release/1.7"),
            {
                "branch": "release/1.7",
                "line": "1.7",
                "state": "stabilizing",
                "enabled": [],
                "next_rc": "v1.7.0-rc.1",
                "tip_rc": None,
                "ahead_of_ga": None,
                "targets": {},
            },
        )
        self.assertTrue(all("release/1.7" not in v for v in st["supported"].values()))
        self.assertIn("release/1.7", st["backport_targets"]["fix"])

    def test_9_tag_not_on_branch(self):
        self.s1()
        self.push("on-prem/release", "v1.5.0-rc.9", git_ref=self.commit("main-only"))
        st = self.state()
        self.assertEqual(self.branch(st, "release/1.5")["enabled"], ["cloud"])
        self.assertEqual(
            st["anomalies"],
            [
                {
                    "target": "on-prem",
                    "artifact": "on-prem/release",
                    "tag": "v1.5.0-rc.9",
                    "branch": "release/1.5",
                    "reason": "commit not on branch",
                }
            ],
        )

    def test_10_registry_failure(self):
        self.s1()

        def boom(artifact):
            raise RuntimeError("HTTP 403")

        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = rs.main(
                ["--repo", self.repo, "--now", "2026-09-29T00:00:00Z"], registry=boom
            )
        self.assertNotEqual(code, 0)
        self.assertEqual(out.getvalue(), "")
        self.assertIn("HTTP 403", err.getvalue())

    def test_11_next_minor_ignores_legacy(self):
        self.cut("1.5")
        self.cut("1.6")
        self.g("branch", "release/v0.148.1001", "main")
        st = self.state()
        self.assertEqual(st["next_minor"], "1.7")
        self.assertEqual(
            [b["branch"] for b in st["branches"]], ["release/1.6", "release/1.5"]
        )

    def test_13_retired_lines_are_history_not_anomalies(self):
        self.s4()  # only release/1.5 is live
        retired = self.commit("1.6 work")
        self.push(
            "cloud/release", "v1.6.0-rc.1", git_ref=retired
        )  # promoted, published, then retired: no branch
        self.push("cloud/release", "v1.6.0", git_ref=retired)
        self.push("on-prem/release", "v1.6.0")
        self.push("on-prem/chart", "v1.6.0", days=400)
        self.push(
            "cloud/release", "v1.9.0-rc.1", git_ref=self.commit("never promoted")
        )  # still an anomaly
        st = self.state()
        self.assertEqual(
            st["anomalies"],
            [
                {
                    "target": "cloud",
                    "artifact": "cloud/release",
                    "tag": "v1.9.0-rc.1",
                    "branch": "release/1.9",
                    "reason": "no branch",
                }
            ],
        )
        self.assertEqual([b["branch"] for b in st["branches"]], ["release/1.5"])

    def test_14_next_rc_moves_after_tip_is_built(self):
        self.s2()
        self.commit("pick", "release/1.5")
        self.assertEqual(
            {
                k: self.branch(self.state(), "release/1.5")[k]
                for k in ("next_rc", "tip_rc")
            },
            {"next_rc": "v1.5.1-rc.1", "tip_rc": None},
        )

    def test_15_summary(self):
        self.s6()
        out = rs.summary(self.state())
        self.assertIn(
            "| release/1.6 | stabilized | stabilized (GA v1.6.0) | - | v1.6.0-rc.1 | - | 0 |",
            out,
        )
        self.assertIn(
            "| release/1.5 | stabilized | past-eos | stabilized (GA v1.5.1) | v1.5.0-rc.1 | - | 0 |",
            out,
        )
        self.assertIn("next_minor: 1.7", out)

    def test_19_ahead_of_ga(self):
        self.s2()
        self.g("tag", "v1.5.1", "release/1.5")  # latest stable tag counts, not the first
        self.commit("pick 1", "release/1.5")
        self.commit("pick 2", "release/1.5")
        self.cut("1.6")  # no stable tag yet
        st = self.state()
        self.assertEqual(
            [self.branch(st, b)["ahead_of_ga"] for b in ("release/1.5", "release/1.6")],
            [2, None],
        )
        self.assertIn("| v1.5.2-rc.1 | 2 |", rs.summary(st))

    def test_21_rbo_line_in_squash_message(self):
        self.cut("1.5")
        squash = (
            "UN-37 [MISC] pin redis (#9)\n\n* chore: pin redis\n\nwhy it is pinned\n\n"
            "* Release-branch-only: UN-37\n\n---------\n\nCo-authored-by: x <x@example.com>"
        )
        cases = {
            squash: "release-branch-only",  # COMMIT_MESSAGES squash: the bot's subject-only commit as `* ...`
            "fix: pin\n\nbody\n\nRelease-branch-only: UN-37": "release-branch-only",  # a trailer
            "fix: pin\n\nsee the Release-branch-only: UN-37 note": "invalid",  # mid-line is not the line
            "fix: pin\n\n** Release-branch-only: UN-37": "invalid",
        }
        for msg, kind in cases.items():
            sha = self.commit(msg, "release/1.5")
            self.assertEqual(rm.classify_commit(self.repo, sha), kind, msg)
        self.assertEqual(rm.RBO_RE.findall(squash), ["UN-37"])

    def test_22_promote_blockers(self):
        """Promote order per target: only an older line with the target enabled and not GA for it blocks."""
        msg = "release/{} is not GA for {} yet: promote and publish it first, retire it, or force with a reason"
        self.s3()  # 1.5: cloud GA, on-prem RC only
        self.cut("1.6")
        self.push("cloud/release", "v1.6.0-rc.1", git_ref="release/1.6")
        self.cut("1.7")  # nothing built yet
        st = self.state()
        self.assertEqual(
            rs.promote_blockers(st, "release/1.5", "cloud"), []
        )  # no older line
        # (a) 1.5 is GA for cloud only: 1.6 cloud passes, 1.6 on-prem waits for 1.5
        self.assertEqual(rs.promote_blockers(st, "release/1.6", "cloud"), [])
        self.assertEqual(
            rs.promote_blockers(st, "release/1.6", "on-prem"),
            [msg.format("1.5", "on-prem")],
        )
        # (b) on-prem is not enabled on 1.6, so 1.6 never blocks on-prem
        # (c) 1.7, nothing built, waits per target only for older lines with that target enabled and not GA
        self.assertEqual(
            rs.promote_blockers(st, "release/1.7", "on-prem"),
            [msg.format("1.5", "on-prem")],
        )
        self.assertEqual(
            rs.promote_blockers(st, "release/1.7", "cloud"), [msg.format("1.6", "cloud")]
        )
        # and 1.7 itself, with nothing enabled, blocks nothing newer beyond those two
        self.assertEqual(
            rs.promote_blockers(st, "release/1.8", "cloud"), [msg.format("1.6", "cloud")]
        )
        # (d) 1.5 publishes on-prem (chart push): 1.6 on-prem is no longer blocked
        self.push("on-prem/chart", "v1.5.1")
        self.assertEqual(rs.promote_blockers(self.state(), "release/1.6", "on-prem"), [])
        # (e) a retired older line (branch gone) never blocks
        self.g("branch", "-D", "release/1.6")
        self.assertEqual(rs.promote_blockers(self.state(), "release/1.7", "cloud"), [])

    def test_23_enable_blockers(self):
        """A target is enabled only on a line newer than every line already GA for it."""
        msg = "release/{} is older than release/{}, already GA for {}: enable {} on a newer line instead"
        self.cut("1.4")
        self.push("cloud/release", "v1.4.0-rc.1", git_ref="release/1.4")
        self.s6()  # 1.5: cloud GA, on-prem GA (chart v1.5.1); 1.6: cloud GA, no on-prem
        st = self.state()
        # (a) an older line enabling on-prem behind a line GA for on-prem is refused
        self.assertEqual(
            rs.enable_blockers(st, "release/1.4", "on-prem"),
            [msg.format("1.4", "1.5", "on-prem", "on-prem")],
        )
        # (b) the newest line may enable it
        self.assertEqual(rs.enable_blockers(st, "release/1.6", "on-prem"), [])
        # (c) a target already enabled on the older line is not affected: a patch RC still builds
        self.assertEqual(rs.enable_blockers(st, "release/1.4", "cloud"), [])
        self.assertEqual(rs.enable_blockers(st, "release/1.5", "on-prem"), [])

    def test_23b_no_order_block_on_a_ga_line(self):
        """(d) Invariant: in a state reached only by moves the enable rule and the promote order allow, a patch on a
        line already GA for a target is never order-blocked. Without the enable rule it can be.
        """
        rc, ga = (
            {"cloud": ("cloud/release", ".0"), "on-prem": ("on-prem/release", ".1")},
            {"cloud": "cloud/release", "on-prem": "on-prem/chart"},
        )
        refused = []

        def enable(line, t):
            if rs.enable_blockers(self.state(), f"release/{line}", t):
                return refused.append(("enable", line, t))
            self.push(
                rc[t][0], f"v{line}{rc[t][1]}-rc.{self.n}", git_ref=f"release/{line}"
            )  # a later call is a patch RC

        def go_ga(line, t):
            st = self.state()
            if t not in self.branch(st, f"release/{line}")[
                "targets"
            ] or rs.promote_blockers(st, f"release/{line}", t):
                return refused.append(("ga", line, t))
            self.push(
                ga[t],
                f"v{line}{rc[t][1]}",
                git_ref=f"release/{line}" if t == "cloud" else None,
            )

        def check():
            st = self.state()
            for b in st["branches"]:
                for t, v in b["targets"].items():
                    if v["ga"]:
                        self.assertEqual(
                            rs.promote_blockers(st, b["branch"], t), [], (b["branch"], t)
                        )

        self.cut("1.4")
        self.cut("1.5")
        moves = [
            (enable, "1.5", "cloud"),
            (go_ga, "1.5", "cloud"),
            (enable, "1.5", "on-prem"),
            (self.cut, "1.6"),
            (enable, "1.6", "cloud"),
            (enable, "1.6", "on-prem"),
            (go_ga, "1.6", "on-prem"),
            (go_ga, "1.6", "cloud"),
            (go_ga, "1.5", "on-prem"),
            (enable, "1.4", "on-prem"),
            (enable, "1.4", "cloud"),
            (go_ga, "1.6", "on-prem"),
            (self.cut, "1.7"),
            (enable, "1.7", "on-prem"),
            (enable, "1.5", "on-prem"),
        ]
        for f, *args in moves:
            f(*args)
            check()
        self.assertEqual(
            refused,
            [
                ("ga", "1.6", "on-prem"),
                ("enable", "1.4", "on-prem"),
                ("enable", "1.4", "cloud"),
            ],
        )
        # enabling on-prem on 1.4 behind GA lines anyway order-blocks every newer GA line's patch
        self.push("on-prem/release", "v1.4.1-rc.1", git_ref="release/1.4")
        self.assertTrue(rs.promote_blockers(self.state(), "release/1.6", "on-prem"))

    def chart(self, ver, branch, msg, email="dev@example.com"):
        self.g("checkout", "-q", branch)
        os.makedirs(os.path.join(self.repo, os.path.dirname(rm.CHART)), exist_ok=True)
        with open(os.path.join(self.repo, rm.CHART), "w") as f:
            f.write(f"name: x\nversion: {ver}\n")
        self.g("add", rm.CHART)
        rm.git(
            self.repo,
            "-c",
            "user.name=bot",
            "-c",
            f"user.email={email}",
            "commit",
            "-q",
            "-m",
            msg,
        )
        self.g("checkout", "-q", "main")

    def test_24_already_bumped(self):
        self.cut("1.5")
        self.chart("1.5.0-rc.1", "release/1.5", "release: chart 1.5.0-rc.1", rm.BOT_EMAIL)
        self.assertTrue(rm.already_bumped(self.repo, "release/1.5", "v1.5.0-rc.1"))
        self.assertFalse(
            rm.already_bumped(self.repo, "release/1.5", "v1.5.0-rc.2")
        )  # chart not at the version
        self.commit(
            "fix after the bump", "release/1.5"
        )  # chart still at the version, tip is a normal commit
        self.assertFalse(rm.already_bumped(self.repo, "release/1.5", "v1.5.0-rc.1"))
        self.chart(
            "1.5.0-rc.2", "release/1.5", "release: chart 1.5.0-rc.2"
        )  # right subject, not the bot
        self.assertFalse(rm.already_bumped(self.repo, "release/1.5", "v1.5.0-rc.2"))

    def test_25_promoted_from_build_artifact(self):
        self.s3()
        self.push(
            "on-prem/release", "v1.5.1", git_ref="release/1.5"
        )  # Promote on-prem, chart not published
        onprem = self.branch(self.state(), "release/1.5")["targets"]["on-prem"]
        self.assertEqual(
            onprem,
            {
                "state": "stabilizing",
                "rcs": ["v1.5.0-rc.3"],
                "ga": None,
                "promoted": self.ga("on-prem/release", "v1.5.1"),
            },
        )
        self.push(
            "on-prem/chart", "v1.5.1"
        )  # Publish: GA and state move, promoted does not
        onprem = self.branch(self.state(), "release/1.5")["targets"]["on-prem"]
        self.assertEqual(
            (onprem["state"], onprem["ga"], onprem["promoted"]),
            (
                "stabilized",
                self.ga("on-prem/chart", "v1.5.1"),
                self.ga("on-prem/release", "v1.5.1"),
            ),
        )

    def test_20_tip_rc_slack(self):
        self.s1()
        self.assertNotIn(
            "tip_rc_slack", self.branch(self.state(), "release/1.5")
        )  # lightweight tag: no key
        url = "https://example.slack.com/archives/C0123ABC/p1759900000000100"
        self.g(
            "tag",
            "-f",
            "-a",
            "v1.5.0-rc.1",
            "-m",
            "rc: built for x",
            "-m",
            f"Slack: {url}",
            "release/1.5",
        )
        st = self.state()
        self.assertEqual(self.branch(st, "release/1.5")["tip_rc_slack"], url)
        self.assertIn(f"| v1.5.0-rc.1 ([Slack]({url})) |", rs.summary(st))

    def test_12_next_minor_cutover_fallback(self):
        self.g("tag", "v0.181.0")
        self.g("tag", "v0.181.1001")
        self.g("tag", "v0.182.0-rc.1")  # RC tags do not count
        self.g("branch", "side", "main")
        self.commit("off-main", "side")
        self.g("tag", "v0.190.0", "side")  # stable, but not reachable from main
        self.g(
            "branch", "release/v0.148.1001", "main"
        )  # legacy head: still the cutover case
        st = self.state()
        self.assertEqual((st["branches"], st["next_minor"]), ([], "0.182"))
        self.cut("0.182")
        self.assertEqual(self.state()["next_minor"], "0.183")

    def built_by_mistake(self):
        """release/1.9: cut, one bot commit, built once as v1.9.0-rc.1 on cloud and on-prem."""
        self.g("checkout", "-q", "-b", "release/1.9")
        rm.git(
            self.repo,
            "-c",
            "user.name=bot",
            "-c",
            f"user.email={rm.BOT_EMAIL}",
            "commit",
            "-q",
            "--allow-empty",
            "-m",
            "pin",
        )
        self.g("checkout", "-q", "main")
        self.push("cloud/release", "v1.9.0-rc.1", git_ref="release/1.9")
        self.push("on-prem/release", "v1.9.0-rc.1")
        self.push(
            "cloud/release", "v1.5.0"
        )  # other versions keep the cloud package non-empty

    def test_16_abandon_plan_built_by_mistake(self):
        self.built_by_mistake()
        self.push("cloud/release", "v1.9.0-rc.2")
        self.reg["cloud/release"]["edge"] = self.reg["cloud/release"][
            "v1.9.0-rc.2"
        ]  # mixed tags: kept
        plan = rs.abandon_plan(self.repo, "release/1.9", lambda a: self.reg.get(a, {}))
        rc1 = self.reg["cloud/release"]["v1.9.0-rc.1"]["digest"]
        self.assertEqual(
            plan,
            {
                "ga": [],
                "used": [],
                "rc_tags": ["v1.9.0-rc.1"],
                "versions": {
                    "cloud/release": [
                        {"id": None, "digest": rc1, "tags": ["v1.9.0-rc.1"]}
                    ]
                },
                "kept": ["on-prem/release:v1.9.0-rc.1"],
            },
        )  # last version of on-prem/release
        self.g("branch", "release/1.8", "main")  # never built: nothing to delete
        self.assertEqual(
            rs.abandon_plan(self.repo, "release/1.8", lambda a: {})["versions"], {}
        )

    def test_17_abandon_plan_refusals(self):
        self.built_by_mistake()
        plan = lambda: rs.abandon_plan(
            self.repo, "release/1.9", lambda a: self.reg.get(a, {})
        )
        self.push("on-prem/chart", "v1.9.0")
        self.assertEqual(plan()["ga"], ["on-prem/chart:v1.9.0"])
        self.g("tag", "v1.9.0", "release/1.9")
        self.assertEqual(plan()["ga"], ["v1.9.0", "on-prem/chart:v1.9.0"])
        human = self.commit("human RBO-less work", "release/1.9")
        self.assertEqual(plan()["used"], [human[:12]])

    def test_26_oss_repo_config(self):
        # The OSS repo runs this same file: one target, oss, read from the line's own ee- git tags (no registry),
        # supported while its branch exists. Plain v* tags are community releases from main and never count.
        self.addCleanup(rs.use, rs.PKG_PREFIX)
        rs.use("unstract")
        self.state = lambda: rs.derive(
            self.repo, NOW, lambda a: self.fail(f"registry read of {a}")
        )
        self.g("tag", "v1.9.0")  # a community release on main
        for line in ("1.5", "1.6"):
            self.cut(line)
            self.g("tag", f"ee-v{line}.0-rc.1", f"release/{line}")
            self.g("tag", f"ee-v{line}.0", f"release/{line}")
            self.g("tag", f"v{line}.7", f"release/{line}")  # never the line's GA
        self.cut("1.7")
        self.g("tag", "ee-v1.7.0-rc.1", "release/1.7")
        st = self.state()
        self.assertEqual(
            [(b["branch"], b["state"]) for b in st["branches"]],
            [
                ("release/1.7", "stabilizing"),
                ("release/1.6", "stabilized"),
                ("release/1.5", "stabilized"),
            ],
        )
        self.assertEqual(
            (st["retire"], st["backport_targets"]["fix"], st["anomalies"]),
            ([], ["release/1.7"], []),
        )
        self.assertEqual(
            st["next_minor"], "1.8"
        )  # the community v1.9.0 on main is not this repo's minor
        self.assertEqual(
            self.branch(st, "release/1.6")["targets"]["oss"]["ga"]["tag"], "ee-v1.6.0"
        )
        self.assertIn(
            "| branch | state | oss | tip_rc | next_rc | ahead_of_ga |", rs.summary(st)
        )
        self.assertIn(
            "| release/1.6 | stabilized | stabilized (GA ee-v1.6.0) | ee-v1.6.0-rc.1 | - | 0 |",
            rs.summary(st),
        )
        self.commit("fix on 1.6", "release/1.6")
        self.assertEqual(
            self.branch(self.state(), "release/1.6")["next_rc"], "ee-v1.6.1-rc.1"
        )
        # No promote order for OSS: 1.8 promotes while 1.7 is not GA; cloud's order would block it.
        self.cut("1.8")
        self.g("tag", "ee-v1.8.0-rc.1", "release/1.8")
        st = self.state()
        self.assertEqual(rs.promote_blockers(st, "release/1.8", "oss"), [])
        rs.KEPT = set()
        self.assertEqual(
            rs.promote_blockers(st, "release/1.8", "oss"),
            [
                "release/1.7 is not GA for oss yet: promote and publish it first, retire it, or force with a reason"
            ],
        )

    def test_27_next_minor_past_stable_tag_on_main(self):
        # A minor already shipped from main (tags before the first line) is never cut again.
        self.g("tag", "v1.5.14")
        self.commit("more main work")
        self.g("tag", "v1.6.0")
        self.g("branch", "release/1.5", "v1.5.14")
        self.assertEqual(self.state()["next_minor"], "1.7")

    def test_28_already_bumped_no_chart(self):
        self.cut("1.5")

        def bump(msg):
            rm.git(
                self.repo,
                "-c",
                "user.name=bot",
                "-c",
                f"user.email={rm.BOT_EMAIL}",
                "commit",
                "-q",
                "--allow-empty",
                "-m",
                msg,
            )

        self.g("checkout", "-q", "release/1.5")
        bump("release: 1.5.0-rc.1")
        self.assertTrue(rm.already_bumped(self.repo, "release/1.5", "v1.5.0-rc.1"))
        self.assertFalse(rm.already_bumped(self.repo, "release/1.5", "v1.5.0-rc.2"))
        bump("release: chart 1.5.0-rc.2")  # the chart subject needs a chart
        self.assertFalse(rm.already_bumped(self.repo, "release/1.5", "v1.5.0-rc.2"))

    def test_29_retire_line(self):
        refusal = lambda force=False: rs.retire_line_refusal(
            self.state(), "release/1.5", force
        )
        self.s3()  # cloud GA newest (production), on-prem RCs only
        self.assertEqual(
            refusal(True),
            "cloud is production (newest cloud GA); it retires once a newer line is promoted",
        )
        self.cut("1.6")
        self.push("cloud/release", "v1.6.0-rc.1", git_ref="release/1.6")
        self.push("cloud/release", "v1.6.0", git_ref="release/1.6")
        self.assertIsNone(refusal())  # cloud past-eos, on-prem never promoted: may go
        self.push("on-prem/chart", "v1.5.1")  # on-prem chart in its window
        self.assertEqual(
            refusal(),
            "on-prem still supported (stabilized); force to retire it inside the window",
        )
        self.assertIsNone(refusal(True))
        self.assertEqual(
            rs.retire_line_refusal(self.state(), "release/9.9"), "no such branch"
        )
        # The newest line retired before any GA (its RCs deleted): the next cut reuses its minor.
        self.cut("1.7")
        tip = self.g("rev-parse", "release/1.7")
        self.g("tag", f"retired/1.7-{tip[:7]}", tip)
        self.g("branch", "-D", "release/1.7")
        self.assertEqual(self.state()["next_minor"], "1.7")
        # Retired after a GA (forced on-prem, say): the minor shipped and is skipped.
        self.g("tag", "v1.7.0", tip)
        self.assertEqual(self.state()["next_minor"], "1.8")

    def pick_of(self, fix):  # a non-empty pick of fix on the checked-out branch
        with open(os.path.join(self.repo, "p.txt"), "a") as f:
            f.write("x\n")
        self.g("add", "p.txt")
        self.g("commit", "-q", "-m", f"fix on main\n\n(cherry picked from commit {fix})")

    def test_30_rc_version_skips_registry_rcs(self):
        # An artifact pushed by a run whose tag push failed: its RC is never allocated again once the tip moves.
        self.cut("1.5")
        taken = {"v1.5.0-rc.1", "v1.5.0-rc.2", "v1.4.0-rc.9", "v1.5.1-rc.7", "edge"}
        self.assertEqual(rm.rc_version(self.repo, "release/1.5"), "v1.5.0-rc.1")
        self.assertEqual(
            rm.rc_version(self.repo, "release/1.5", taken=taken), "v1.5.0-rc.3"
        )
        # A tip that is already the bot's bump for a pushed RC resumes that run, and so does a fresh bump.
        for n in (2, 3):
            self.chart(
                f"1.5.0-rc.{n}",
                "release/1.5",
                f"release: chart 1.5.0-rc.{n}",
                rm.BOT_EMAIL,
            )
            self.assertEqual(
                rm.rc_version(self.repo, "release/1.5", taken=taken), f"v1.5.0-rc.{n}"
            )
        self.chart(
            "1.5.0-rc.2", "release/1.5", "release: chart 1.5.0-rc.2"
        )  # not the bot: no resume
        self.assertEqual(
            rm.rc_version(self.repo, "release/1.5", taken=taken), "v1.5.0-rc.3"
        )
        # relstate allocates past every target's registry RCs.
        self.push("cloud/release", "v1.5.0-rc.3")
        self.push("on-prem/release", "v1.5.0-rc.4")
        self.assertEqual(
            self.branch(self.state(), "release/1.5")["next_rc"], "v1.5.0-rc.5"
        )

    def test_31_reused_minor_skips_its_kept_rc(self):
        # release/1.7 built once, then abandoned: its git RC tag deleted, its registry RC kept (the package's last
        # version). The minor is cut again, and its first RC is past the kept one.
        self.cut("1.6")
        tip = self.cut("1.7")
        self.push("on-prem/release", "v1.7.0-rc.1")
        self.g("tag", f"retired/1.7-{tip[:7]}", tip)
        self.g("branch", "-D", "release/1.7")
        self.assertEqual(self.state()["next_minor"], "1.7")
        self.cut("1.7")
        self.assertEqual(
            self.branch(self.state(), "release/1.7")["next_rc"], "v1.7.0-rc.2"
        )

    def test_32_shallow_clone_refused(self):
        clone = os.path.join(self._tmp.name, "shallow")
        self.commit("second")
        rm.git(
            self._tmp.name, "clone", "-q", "--depth", "1", f"file://{self.repo}", clone
        )
        with self.assertRaisesRegex(RuntimeError, "is a shallow clone"):
            rm.git(clone, "log", "-1")
        self.assertNotIn(clone, rm._FULL)

    def test_33_conflict_markers_git_error(self):
        with open(os.path.join(self.repo, "f.txt"), "w") as f:
            f.write("a\n<<<<<<< ours\nb\n=======\nc\n>>>>>>> theirs\n")
        self.g("add", "f.txt")
        self.g("commit", "-q", "-m", "markers")
        self.assertEqual(rm.conflict_markers(self.repo), ["f.txt"])
        with self.assertRaisesRegex(RuntimeError, r"git grep \(exit 128\)"):
            rm.conflict_markers(self.repo, "no-such-rev")

    def test_34_reverted_pick_only_on_its_own_branch(self):
        fix = self.commit("fix on main")
        self.cut("1.5")
        self.cut("1.6")
        self.g("checkout", "-q", "release/1.6")
        self.pick_of(fix)
        pick = self.g("rev-parse", "HEAD")
        self.g("checkout", "-q", "main")
        revert = f"Revert pick\n\nThis reverts commit {pick}."
        self.assertEqual(
            rm.reverted_pick(self.repo, self.commit(revert, "release/1.6")), pick
        )
        other = self.commit(
            revert, "release/1.5"
        )  # the pick is on another line, not this one
        self.assertIsNone(rm.reverted_pick(self.repo, other))
        self.assertEqual(rm.classify_commit(self.repo, other), "invalid")
        self.assertIsNone(
            rm.reverted_pick(
                self.repo,
                self.commit(f"Revert\n\nThis reverts commit {fix}.", "release/1.5"),
            )
        )

    def test_35_ci_commits(self):
        fix = self.commit("fix on main")
        self.cut("1.5")  # one invalid commit, `work on 1.5`
        before = self.g("rev-parse", "release/1.5")
        self.g("checkout", "-q", "-b", "head", "release/1.5")
        self.pick_of(fix)
        pick = self.g("rev-parse", "HEAD")
        self.g("commit", "-q", "--allow-empty", "-m", "resolution")
        human = self.g("rev-parse", "HEAD")
        work = self.g("rev-parse", "release/1.5")
        pr = "PR into release/1.5"
        ci = lambda event, **kw: rm.ci_commits(
            self.repo, "release/1.5", event, main="main", **kw
        )
        cases = [
            (
                ("pull_request",),
                {"head_ref": "fix/x"},
                [(pick, "cherry-pick"), (human, "invalid")],
                pr,
            ),
            (
                ("pull_request",),
                {"head_ref": "fix/x", "labelled": True},
                [(pick, "cherry-pick"), (human, "release-branch-only (label)")],
                pr,
            ),
            (
                ("pull_request",),
                {"head_ref": f"backport/1.5/{fix[:7]}"},
                [(pick, "cherry-pick")],
                pr,
            ),
            (
                ("pull_request",),
                {"head_ref": "backport/anything"},
                [(pick, "cherry-pick"), (human, "invalid")],
                pr,
            ),
            (
                ("push",),
                {"before": before, "labelled": True},
                [(pick, "cherry-pick"), (human, "invalid")],
                "push to release/1.5",
            ),
            (("push",), {"before": "0" * 40}, [(work, "invalid")], "release/1.5"),
            (
                ("push",),
                {"before": "f" * 40},
                [(work, "invalid")],
                "release/1.5",
            ),  # a force push: old tip gone
            (("push",), {}, [(work, "invalid")], "release/1.5"),
        ]
        for args, kw, rows, where in cases:
            self.assertEqual(ci(*args, **kw), (rows, where), (args, kw))
        self.g("checkout", "-q", "main")
        other = self.commit("other fix on main")
        self.g("checkout", "-q", "head")
        self.assertEqual(
            ci("pull_request", head_ref=f"backport/1.5/{other[:7]}")[0],
            [(pick, "invalid")],
        )  # not its fix
        self.g("checkout", "-q", "-B", "two", "release/1.5")
        self.commit(
            f"fix on main\n\n(cherry picked from commit {fix})\n(cherry picked from commit {other})"
        )
        self.assertEqual(
            ci("pull_request", head_ref=f"backport/1.5/{fix[:7]}")[0][0][1], "invalid"
        )  # names a second fix
        self.g("checkout", "-q", "head")
        with open(os.path.join(self.repo, "f.txt"), "w") as f:
            f.write(">>>>>>> theirs\n")
        self.g("add", "f.txt")
        self.g("commit", "-q", "-m", "left a marker")
        with self.assertRaisesRegex(ValueError, "conflict markers in f.txt"):
            ci("pull_request", head_ref=f"backport/1.5/{fix[:7]}")
        self.assertEqual(
            len(ci("pull_request", head_ref="fix/x")[0]), 3
        )  # only a backport PR's tree is checked
        self.g("checkout", "-q", "main")

    def test_36_is_backport(self):
        for ref, want in (
            ("backport/1.5/abcdef0", True),
            ("backport/0.192/1234567", True),
            ("backport/1.5/abcdef01", False),
            ("backport/1.5/ABCDEF0", False),
            ("backport/x", False),
            ("evil/backport/1.5/abcdef0", False),
            ("backport/1.5/abcdef0/x", False),
            ("", False),
        ):
            self.assertEqual(rm.is_backport(ref), want, ref)

    def test_37_unknown_repo_config(self):
        with self.assertRaisesRegex(
            RuntimeError, "relstate has no config for repo 'nope'"
        ):
            rs.use("nope")
        self.assertEqual(rs.PREFIX, "")  # the loaded config is untouched


class PrFixClass(unittest.TestCase):
    """Lint PR / Backport class rule: title type plus fix/ labels."""

    def test_18_pr_fix_class(self):
        c = rm.pr_fix_class
        self.assertEqual(c("UN-1 [FIX] x"), "fix")
        self.assertIsNone(c("UN-1 [MISC] x"))
        self.assertEqual(c("UN-1 [MISC] x", ["fix/needs-backport"]), "fix")
        self.assertEqual(
            c("UN-1 [FIX] x", ["fix/needs-backport"]), "fix"
        )  # no-op on a fix title
        self.assertEqual(
            c("UN-1 [MISC] x", ["fix/security", "fix/needs-backport"]), "security"
        )
        self.assertEqual(c("UN-1 [FEAT] x", ["fix/critical", "bug"]), "critical")
        for labels in (
            ["fix/typo"],
            ["fix-class/security"],
            ["Fix/security"],
            ["fixclass"],
            ["fix/security", "fix/critical"],
        ):
            with self.assertRaises(ValueError, msg=labels) as e:
                c("UN-1 [FIX] x", labels)
            if labels != ["fix/security", "fix/critical"]:
                self.assertIn(
                    "fix/security, fix/critical, fix/needs-backport", str(e.exception)
                )

    def test_18b_revert_takes_inner_class(self):
        c = rm.pr_fix_class
        self.assertEqual(c('Revert "UN-1 [FIX] x"'), "fix")
        self.assertIsNone(c('Revert "UN-1 [MISC] x"'))
        self.assertEqual(c('Revert "Revert "UN-1 [FIX] x""'), "fix")
        for title in ('Revert "fix x"', "Revert UN-1 [FIX] x", 'revert "UN-1 [FIX] x"'):
            with self.assertRaises(ValueError, msg=title):
                c(title)
        with self.assertRaises(ValueError):
            c("no prefix")
        self.assertEqual(c("no prefix", ["fix/needs-backport"]), "fix")

    def test_18c_ticketless_title_same_class(self):
        c = rm.pr_fix_class
        self.assertEqual(c("[FIX] x"), "fix")
        self.assertEqual(c("[HOT-FIX] x"), "fix")
        self.assertIsNone(c("[MISC] x"))
        self.assertEqual(c("[MISC] x", ["fix/needs-backport"]), "fix")
        self.assertEqual(c("[FEAT] x", ["fix/security"]), "security")
        self.assertEqual(c('Revert "[FIX] x"'), "fix")
        for title in ("[fix] x", "[FIX]x", " [FIX] x", "UN-1[FIX] x", "un-1 [FIX] x"):
            with self.assertRaises(ValueError, msg=title):
                c(title)

    def test_18d_rbo_key_ticket_else_pr(self):
        self.assertEqual(rm.rbo_key("UN-1 [FIX] x", "45"), "UN-1")
        self.assertEqual(rm.rbo_key("[FIX] x", "45"), "#45")
        self.assertEqual(rm.rbo_key("no prefix", "45"), "#45")
        self.assertEqual(rm.RBO_RE.findall("Release-branch-only: #45"), ["#45"])


if __name__ == "__main__":
    unittest.main()
