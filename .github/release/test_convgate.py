"""Synthetic-repo tests for convgate (2b-2d revert of a pick = decline; 2g-2h DECLINED rows and decline_records; 5 a plain fix is owed to a stabilized line; 7a-7e MISSING messages; 7f-7g a promoted stable tag is read before its GA; 9a-9h checks table, release-branch-only window, count line, next steps; 10a-10d OSS pins). Run: python test_convgate.py"""

import contextlib
import datetime as dt
import io
import json
import os
import tempfile
import unittest
from unittest import mock

os.environ["GITHUB_REPOSITORY"] = (
    "Zipstack/unstract-cloud"  # relstate loads the cloud config, whatever the runner sets
)
import convgate as cg
import relmgr as rm
import relstate as rs

os.environ.update(GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_NOSYSTEM="1")
os.environ.pop("GITHUB_OUTPUT", None)
os.environ.pop("GITHUB_STEP_SUMMARY", None)
os.environ.pop("OSS_REPO", None)
NOW = dt.datetime(2026, 9, 29, tzinfo=dt.UTC)


class Gate(unittest.TestCase):
    """Row 1 base: 1.5 and 1.6 cut, then C lands on main and is picked to 1.5 only; cloud RCs on both."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.repo, self.reg = self._tmp.name, {}
        rm.git(self.repo, "init", "-q", "-b", "main")
        self.change("base", None)  # unborn main: nothing to check out
        for line in ("1.5", "1.6"):
            self.g("branch", f"release/{line}", "main")
            self.change(f"work on {line}", f"release/{line}")
        self.c = self.change("C: the fix", "main")
        self.pick(self.c, "release/1.5")
        self.push("cloud/release", "v1.5.0-rc.1", "release/1.5")
        self.push("cloud/release", "v1.6.0-rc.1", "release/1.6")

    def g(self, *args):
        return rm.git(
            self.repo, "-c", "user.name=Dev", "-c", "user.email=dev@example.com", *args
        )

    def change(self, msg, branch):
        if branch:
            self.g("checkout", "-q", branch)
        with open(
            os.path.join(self.repo, f"{msg.split(':')[0].replace(' ', '_')}.txt"), "w"
        ) as f:
            f.write(msg)
        self.g("add", "-A")
        self.g("commit", "-q", "-m", msg)
        return self.g("rev-parse", "HEAD")

    def pick(self, sha, branch):
        self.g("checkout", "-q", branch)
        self.g("cherry-pick", "-x", sha)

    def decline(self, sha, branch):
        self.g("checkout", "-q", branch)
        self.g(
            "commit",
            "-q",
            "--allow-empty",
            "-m",
            f"decline C\n\n(cherry picked from commit {sha})",
        )

    def revert(self, sha, branch, short=False):
        """The Revert button's commit on `branch`; short=True names the reverted commit abbreviated."""
        self.g("checkout", "-q", branch)
        self.g("revert", "--no-commit", sha)
        self.g(
            "commit",
            "-q",
            "-m",
            f'Revert "x"\n\nThis reverts commit {sha[:7] if short else sha}.',
        )
        return self.g("rev-parse", "HEAD")

    def tip(self, branch):
        return self.g("rev-parse", branch)

    def push(self, artifact, tag, ref):
        self.g("tag", tag, ref)
        self.reg.setdefault(artifact, {})[tag] = {
            "digest": f"sha256:{len(self.reg):064x}{tag}",
            "pushed_at": "2026-09-28T00:00:00Z",
        }

    def run_gate(
        self,
        branch,
        target="cloud",
        annotate="warning",
        prs=None,
        promote_ref=None,
        failures=None,
    ):
        """prs: {conflict PR head: (number, url)}, failures: {(source PR, line): run url}; injected (no network)."""
        state = rs.derive(self.repo, NOW, lambda a: self.reg.get(a, {}))
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            code, out, self.lines = cg.gate(
                self.repo,
                branch,
                target,
                state,
                promote_ref=promote_ref,
                annotate=annotate,
                lookup=(prs or {}).get,
                failure=lambda n, b: (failures or {}).get((n, b)),
            )
        self.printed = buf.getvalue()
        return code, "\n".join(out)

    def test_1_both_directions(self):
        code, out = self.run_gate("release/1.5")
        self.assertEqual(code, 2)
        self.assertIn(", 1 missing,", out)
        code, out = self.run_gate("release/1.6")
        self.assertEqual(code, 2)
        self.assertIn("**release/1.5** (older", out)

    def test_2_decline_converges(self):
        self.decline(self.c, "release/1.6")
        for b in ("release/1.5", "release/1.6"):
            code, out = self.run_gate(b)
            self.assertEqual(code, 0, out)
            self.assertIn(
                "1 picks, 0 in the RC, 1 declined on release/1.6, 1 unclassifiable", out
            )

    def test_2b_revert_of_pick_declines_on_newer(self):
        self.pick(self.c, "release/1.6")
        r = self.revert(self.tip("release/1.6"), "release/1.6")
        self.assertEqual(rm.classify_commit(self.repo, r), "declined")
        self.assertEqual(rm.declined_originals(self.repo, "release/1.6"), {self.c})
        for b in ("release/1.5", "release/1.6"):
            code, out = self.run_gate(b)
            self.assertEqual(code, 0, out)
            self.assertIn(
                "1 picks, 0 in the RC, 1 declined on release/1.6, 1 unclassifiable", out
            )

    def test_2c_revert_of_pick_on_older_owes_nothing(self):
        r = self.revert(self.tip("release/1.5"), "release/1.5", short=True)
        self.assertEqual(rm.classify_commit(self.repo, r), "declined")
        rows = rm.convergence_report(self.repo, "release/1.5", "release/1.6")
        self.assertEqual(
            [st for _, st in rows], ["UNCLASSIFIABLE"]
        )  # the fixture's plain work commit only
        for b in ("release/1.5", "release/1.6"):
            code, out = self.run_gate(b)
            self.assertEqual(code, 0, out)

    def test_2e_pick_after_decline_ships(self):
        """A decline undone by merging the reopened PR: the newest trailer wins, the fix counts as picked."""
        self.decline(self.c, "release/1.6")
        self.pick(self.c, "release/1.6")
        self.assertEqual(
            rm.trailer_states(self.repo, "release/1.6"), {self.c: "cherry-pick"}
        )
        self.assertEqual(rm.declined_originals(self.repo, "release/1.6"), set())
        for b in ("release/1.5", "release/1.6"):
            code, out = self.run_gate(b)
            self.assertEqual(code, 0, out)
            self.assertIn("1 picks, 1 in the RC, 1 unclassifiable", out)

    def test_2f_pick_after_decline_past_ga_still_owed(self):
        """Newer is GA at a tag without the fix; its decline was undone by a later pick: older's promote waits for
        newer's next patch instead of reading the stale decline as converged.
        """
        self.reg["cloud/release"]["v1.6.0"] = self.reg["cloud/release"]["v1.6.0-rc.1"]
        self.g("tag", "v1.6.0", "v1.6.0-rc.1")
        self.decline(self.c, "release/1.6")
        self.pick(self.c, "release/1.6")
        code, out = self.run_gate("release/1.5")
        self.assertEqual(code, 2, out)
        self.assertIn("into `refs/tags/v1.6.0`", out)

    def test_2g_declined_row(self):
        """A decline converges (exit 0) and its row names the reason and the decline commit."""
        self.g("checkout", "-q", "release/1.6")
        self.g(
            "commit",
            "-q",
            "--allow-empty",
            "-m",
            f"x\n\n(cherry picked from commit {self.c})\n\nDeclined: not needed on 1.6",
        )
        d = self.tip("release/1.6")
        pick = self.g("rev-list", "-1", "release/1.5")
        for b in ("release/1.5", "release/1.6"):
            code, out = self.run_gate(b)
            self.assertEqual(code, 0, out)
            self.assertIn(
                "1 picks, 0 in the RC, 1 declined on release/1.6, 1 unclassifiable", out
            )
            self.assertIn(
                f"- `{pick[:12]}` DECLINED on release/1.6 original {self.c[:12]}: not needed on 1.6 ({d[:7]})",
                out,
            )

    def test_2g2_declined_on_older(self):
        """A decline on the older line owes the newer line nothing: no row, nothing counted."""
        self.g("checkout", "-q", "release/1.5")
        self.g(
            "commit",
            "-q",
            "--allow-empty",
            "-m",
            f"x\n\n(cherry picked from commit {self.c})\n\nDeclined: not needed on 1.5",
        )
        d = self.tip("release/1.5")
        for b in ("release/1.5", "release/1.6"):
            code, out = self.run_gate(b)
            self.assertEqual(code, 0, out)
            self.assertNotIn("DECLINED", out)
            self.assertNotIn(d[:12], out)
            self.assertIn("0 in the RC, 1 unclassifiable\n", out)

    def test_2h_decline_records(self):
        """Empty decline: its last `Declined:` line (subject without one); revert of a pick: the revert's subject;
        a later pick clears the record.
        """
        self.decline(self.c, "release/1.6")
        d = self.tip("release/1.6")
        self.assertEqual(
            rm.decline_records(self.repo, "release/1.6"), {self.c: (d, "decline C")}
        )
        self.g(
            "commit",
            "-q",
            "--allow-empty",
            "-m",
            f"x\n\n(cherry picked from commit {self.c})\n\nDeclined: first\nDeclined: second",
        )
        self.assertEqual(
            rm.decline_records(self.repo, "release/1.6"),
            {self.c: (self.tip("release/1.6"), "second")},
        )
        self.pick(self.c, "release/1.6")
        self.assertEqual(rm.decline_records(self.repo, "release/1.6"), {})
        r = self.revert(self.tip("release/1.6"), "release/1.6")
        self.assertEqual(
            rm.decline_records(self.repo, "release/1.6"), {self.c: (r, 'Revert "x"')}
        )
        self.assertEqual(
            set(rm.decline_records(self.repo, "release/1.6")),
            rm.declined_originals(self.repo, "release/1.6"),
        )

    def test_2d_revert_of_non_pick_is_invalid(self):
        work = self.tip("release/1.6")  # the fixture's "work on 1.6": not a pick
        r = self.revert(work, "release/1.6")
        self.assertEqual(rm.classify_commit(self.repo, r), "invalid")
        self.assertIn(r, rm.check_branch(self.repo, "release/1.6"))

    def test_8a_backport_pr_judged_as_its_squash(self):
        """A plain resolution commit after the pick passes on a backport/* PR; any other PR still classifies all."""
        self.g("checkout", "-q", "-b", "backport/1.6/abcdef0", "release/1.6")
        self.g("cherry-pick", "-x", self.c)
        first = self.tip("backport/1.6/abcdef0")
        self.change("fixup: resolve", "backport/1.6/abcdef0")
        self.assertEqual(
            rm.pr_commits(self.repo, "release/1.6", "backport/1.6/abcdef0"), [first]
        )
        both = rm.pr_commits(self.repo, "release/1.6", "dev/x")
        self.assertEqual(len(both), 2)
        self.assertEqual(rm.classify_commit(self.repo, both[1]), "invalid")

    def test_8b_conflict_markers(self):
        self.assertEqual(rm.conflict_markers(self.repo), [])
        self.g("checkout", "-q", "release/1.6")
        with open(os.path.join(self.repo, "f.txt"), "w") as f:
            f.write("a\n<<<<<<< HEAD\nours\n=======\ntheirs\n>>>>>>> c (fix)\n")
        with open(os.path.join(self.repo, "g.txt"), "w") as f:
            f.write("<<<<<<<< not a marker\n=======\n")
        self.g("add", "f.txt", "g.txt")
        self.g("commit", "-q", "-m", "markers")
        self.assertEqual(rm.conflict_markers(self.repo), ["f.txt"])

    def test_7a_older_promote_names_conflict_pr(self):
        c7 = self.c[:7]
        code, out = self.run_gate(
            "release/1.5", annotate="error", prs={f"backport/1.6/{c7}": (12, "u")}
        )
        self.assertEqual(code, 2)
        msg = (
            f"Cannot promote release/1.5 for cloud: fix {c7} is not on newer release/1.6 yet. "
            "Conflict PR #12 on release/1.6: resolve, get one approval and merge, or close the PR to decline (the close comment is the reason)."
        )
        self.assertIn(f"::error::{msg}", self.printed)
        self.assertIn(msg, out)

    def test_7b_newer_promote_conflict_pr_on_itself(self):
        c7 = self.c[:7]
        code, _ = self.run_gate(
            "release/1.6", annotate="error", prs={f"backport/1.6/{c7}": (12, "u")}
        )
        self.assertEqual(code, 2)
        self.assertIn(
            f"::error::Cannot promote release/1.6 for cloud: fix {c7} is on older release/1.5 but not on "
            "this line. Conflict PR #12 is on this branch: resolve, get one approval and merge, or close the PR to decline (the close comment is the reason).",
            self.printed,
        )

    def test_7c_no_pr_fallback_warns(self):
        d = self.change("D: another fix (#9)", "main")
        self.decline(self.c, "release/1.6")  # leave D as the only MISSING row
        self.pick(d, "release/1.5")
        code, out = self.run_gate("release/1.5")
        self.assertEqual(code, 2)
        msg = (
            f"Promote of release/1.5 for cloud will be blocked: fix {d[:7]} (PR #9) is not on newer release/1.6 "
            f"yet. No Backport PR found for it: run Backport for {d[:7]}, or decline it on release/1.6."
        )
        self.assertIn(f"::warning::{msg}", self.printed)
        self.assertNotIn("::error::", self.printed)
        # Backport's push-failure comment on PR #9 names the cause and the rerun instead; another line's does not
        _, out = self.run_gate(
            "release/1.5", failures={(9, "release/1.6"): "https://x/runs/5"}
        )
        self.assertIn(
            f"(PR #9) is not on newer release/1.6 yet. Backport for {d[:7]} to release/1.6 failed: push "
            f"rejected (run https://x/runs/5). Rerun Backport for {d[:7]} on release/1.6.",
            out,
        )
        _, out = self.run_gate(
            "release/1.5", failures={(9, "release/1.7"): "https://x/runs/5"}
        )
        self.assertIn(msg, out)

    def test_7d_on_newer_tip_not_shipped(self):
        self.reg["cloud/release"]["v1.6.0"] = self.reg["cloud/release"][
            "v1.6.0-rc.1"
        ]  # 1.6 GA at v1.6.0
        self.g("tag", "v1.6.0", "v1.6.0-rc.1")
        self.pick(self.c, "release/1.6")  # on the tip after GA, so not in v1.6.0
        code, _ = self.run_gate("release/1.5")
        self.assertEqual(code, 2)
        self.assertIn(
            f"fix {self.c[:7]} is on release/1.6 but not in its latest stable v1.6.0: "
            "promote a release/1.6 patch first.",
            self.printed,
        )

    def test_7e_on_promoted_tip_not_in_its_rc(self):
        self.pick(self.c, "release/1.6")  # on 1.6's tip after v1.6.0-rc.1 was cut
        code, _ = self.run_gate(
            "release/1.6", annotate="error", promote_ref="v1.6.0-rc.1"
        )
        self.assertEqual(code, 2)
        self.assertIn(
            f"::error::Cannot promote release/1.6 for cloud: fix {self.c[:7]} is on release/1.6 "
            "but not in RC v1.6.0-rc.1: take a new RC build first.",
            self.printed,
        )

    def onprem(self):
        """On-prem RCs on both lines (the cloud RC commits), then on-prem Promote of 1.6 at v1.6.0, chart not published."""
        for tag in ("v1.5.0-rc.1", "v1.6.0-rc.1"):
            self.reg.setdefault("on-prem/release", {})[tag] = self.reg["cloud/release"][
                tag
            ]
        self.g("tag", "v1.6.0", "v1.6.0-rc.1")
        self.reg["on-prem/release"]["v1.6.0"] = self.reg["on-prem/release"]["v1.6.0-rc.1"]

    def test_7f_promoted_not_published_read_at_its_tag(self):
        self.onprem()
        self.pick(
            self.c, "release/1.6"
        )  # after the Promote: the tip has it, v1.6.0 does not
        code, out = self.run_gate("release/1.5", "on-prem")
        self.assertEqual(code, 2, out)
        self.assertIn(
            "**release/1.6** (newer, stabilizing for on-prem; `refs/heads/release/1.5` into `refs/tags/v1.6.0`)",
            out,
        )
        self.assertIn(
            f"fix {self.c[:7]} is on release/1.6 but not in its latest stable v1.6.0: "
            "promote a release/1.6 patch first.",
            self.printed,
        )

    def test_7g_patch_promoted_read_over_published(self):
        self.onprem()
        self.reg["on-prem/chart"] = {
            "v1.6.0": self.reg["on-prem/release"]["v1.6.0"]
        }  # Publish v1.6.0
        self.pick(self.c, "release/1.6")
        self.g("tag", "v1.6.1-rc.1", "release/1.6")
        self.g("tag", "v1.6.1", "release/1.6")
        self.reg["on-prem/release"]["v1.6.1-rc.1"] = self.reg["on-prem/release"][
            "v1.6.1"
        ] = {
            "digest": "sha256:61",
            "pushed_at": "2026-09-28T00:00:00Z",
        }  # patch promoted, not published
        code, out = self.run_gate("release/1.5", "on-prem")
        self.assertEqual(code, 0, out)
        self.assertIn(
            "(newer, stabilized for on-prem; `refs/heads/release/1.5` into `refs/tags/v1.6.1`)",
            out,
        )

    def checks(self, out, order=(), split=True):
        table, detail = cg.checks(self.lines, list(order), out.splitlines(), split=split)
        self.assertEqual(detail[0], "<details><summary>Gate detail</summary>")
        self.assertIn(out.splitlines()[0], detail)
        return table

    def test_9a_checks_clean(self):
        self.decline(self.c, "release/1.6")
        _, out = self.run_gate("release/1.5")
        self.assertEqual(
            self.checks(out)[2:],
            [
                "| ✅ fixes match newer lines | `release/1.6` 1 picks, 0 in the RC, 1 declined on release/1.6, 1 unclassifiable | - |",
                "| ✅ fixes match older lines | no other supported line | - |",
                "| ✅ promote order | no older line is waiting to go GA | - |",
                "| ✅ release-branch-only to check | none | - |",
            ],
        )
        self.assertEqual(
            self.checks(out, split=False)[2],
            "| ✅ fixes match the other lines | `release/1.6` 1 picks, 0 in the RC, 1 declined on release/1.6, "
            "1 unclassifiable | - |",
        )

    def test_9b_checks_missing_with_conflict_pr(self):
        _, out = self.run_gate(
            "release/1.6", prs={f"backport/1.6/{self.c[:7]}": (12, "u")}
        )
        table = self.checks(
            out,
            [
                "release/1.5 is not GA for cloud yet: promote and publish it first, retire it, "
                "or force with a reason"
            ],
        )
        self.assertEqual(
            table[3],
            "| ⛔ fixes match older lines | `release/1.5` 1 picks, 0 in the RC, 1 missing, 1 unclassifiable | merge or close "
            f"conflict PR {rm.pr_link(12)}, then Take RC again |",
        )
        self.assertEqual(
            table[4],
            "| ⛔ promote order | release/1.5 is not GA for cloud yet | "
            "promote or retire `release/1.5` |",
        )
        _, out = self.run_gate(
            "release/1.5", prs={f"backport/1.6/{self.c[:7]}": (12, "u")}
        )  # the PR is on newer
        self.assertIn(
            f"merge or close conflict PR {rm.pr_link(12)} on `release/1.6` |",
            self.checks(out)[2],
        )

    def rbo(
        self, title, date="2030-01-01T00:00:00Z", path="pin.txt", branch="release/1.5"
    ):
        """A Release-branch-only squash on `branch` committed at `date`, changing `path`."""
        self.g("checkout", "-q", branch)
        os.makedirs(os.path.join(self.repo, os.path.dirname(path)), exist_ok=True)
        with open(os.path.join(self.repo, path), "a") as f:
            f.write(title)
        self.g("add", path)
        with mock.patch.dict(
            os.environ, GIT_COMMITTER_DATE=date
        ):  # a squash lists the bot's commit and keeps
            self.g(
                "commit",
                "-q",
                "-m",
                f"{title}\n\n* Release-branch-only: UN-37\n\nRelease-branch-only: UN-37",
            )
        return self.tip(branch)

    def test_9c_checks_rbo_absent(self):
        self.decline(self.c, "release/1.6")
        rbo = self.rbo("pin the base image")  # its trailer twice: one ticket
        _, out = self.run_gate("release/1.5")
        what = f"UN-37 pin the base image ({rm.commit_link(rbo)})"
        self.assertIn(f"- `{rbo[:12]}` RBO-ABSENT {what}", out)
        self.assertNotIn("RBO-ABSENT original", out)
        self.assertEqual(
            self.checks(out)[5],
            f"| ⚠ release-branch-only to check | on `release/1.5`: {what}, not on "
            "`release/1.6` | check whether the newer line needs its own equivalent |",
        )
        # a title that already starts with the ticket names it once
        rbo = self.rbo("UN-37 [MISC] pin the base image")
        _, out = self.run_gate("release/1.5")
        self.assertIn(
            f"- `{rbo[:12]}` RBO-ABSENT UN-37 [MISC] pin the base image ({rm.commit_link(rbo)})\n",
            out,
        )

    def test_9e_rbo_window(self):
        self.decline(self.c, "release/1.6")
        old = self.rbo(
            "before the cut", "2020-01-01T00:00:00Z"
        )  # 1.6 has no GA: its cut is the window
        new = self.rbo("after the cut")
        workflow = self.rbo(
            "seed a workflow", path=".github/workflows/x.yaml"
        )  # nothing outside .github/
        _, out = self.run_gate("release/1.5")
        self.assertIn(" · 1 release-branch-only to check\n", out)
        self.assertIn(new[:12], out)
        self.assertNotIn(old[:12], out)
        self.assertNotIn(workflow[:12], out)
        # 1.6 GA for cloud: its GA tag's date is the window
        self.reg["cloud/release"]["v1.6.0"] = self.reg["cloud/release"]["v1.6.0-rc.1"]
        with mock.patch.dict(os.environ, GIT_COMMITTER_DATE="2031-01-01T00:00:00Z"):
            self.g("tag", "-a", "v1.6.0", "-m", "promote", "v1.6.0-rc.1")
        later = self.rbo("after the GA", "2032-01-01T00:00:00Z")
        _, out = self.run_gate("release/1.5")
        self.assertIn(" · 1 release-branch-only to check\n", out)
        self.assertIn(later[:12], out)
        self.assertNotIn(new[:12], out)

    def test_9f_checks_name_lines_as_needed(self):
        self.reg["cloud/release"]["v1.5.0"] = self.reg["cloud/release"][
            "v1.5.0-rc.1"
        ]  # 1.5 GA: stabilized
        self.g("tag", "v1.5.0", "v1.5.0-rc.1")
        self.decline(self.c, "release/1.6")
        _, out = self.run_gate("release/1.6")
        self.assertEqual(
            self.checks(out)[3],
            "| ✅ fixes match older lines | 1 older line converged (1 picks) | - |",
        )
        self.assertIn("**release/1.5** (older", out)  # the detail keeps every line
        self.rbo("pin the base image")
        _, out = self.run_gate("release/1.6")
        self.assertIn(
            "| ✅ fixes match older lines | `release/1.5` 1 picks,", self.checks(out)[3]
        )

    def test_9g_count_line(self):
        self.pick(self.c, "release/1.6")
        _, out = self.run_gate("release/1.5")
        self.assertIn(
            "**release/1.6** (newer, stabilizing for cloud; `refs/heads/release/1.5` into `refs/heads/release/1.6`): "
            "1 picks, 1 in the RC, 1 unclassifiable\n",
            out,
        )
        _, out = self.run_gate(
            "release/1.6", promote_ref="v1.6.0-rc.1"
        )  # the RC being promoted: still "the RC"
        self.assertIn(
            "into `refs/tags/v1.6.0-rc.1`): 1 picks, 0 in the RC, 1 missing, 1 unclassifiable\n",
            out,
        )
        self.reg["cloud/release"]["v1.6.0"] = self.reg["cloud/release"]["v1.6.0-rc.1"]
        self.g(
            "tag", "v1.6.0", "release/1.6"
        )  # 1.6 GA at a tag with the pick: named by its tag
        self.rbo("pin the base image")
        _, out = self.run_gate("release/1.5")
        self.assertIn(
            "**release/1.6** (newer, stabilized for cloud; `refs/heads/release/1.5` into `refs/tags/v1.6.0`): "
            "1 picks, 1 in v1.6.0, 1 unclassifiable · 1 release-branch-only to check\n",
            out,
        )
        self.assertIn(
            "| `release/1.6` 1 picks, 1 in v1.6.0, 1 unclassifiable · 1 release-branch-only to check |",
            self.checks(out)[2],
        )
        self.push(
            "cloud/release", "v1.6.1-rc.1", "release/1.6"
        )  # a patch RC of a GA line: "the RC" again
        _, out = self.run_gate("release/1.6", promote_ref="v1.6.1-rc.1")
        self.assertIn(
            "into `refs/tags/v1.6.1-rc.1`): 1 picks, 1 in the RC, 1 unclassifiable · 1 release-branch-only "
            "to check\n",
            out,
        )

    def test_9h_next_steps(self):
        """The do-this items in table order, each once; the table cells are built from the same list."""
        _, out = self.run_gate(
            "release/1.6", prs={f"backport/1.6/{self.c[:7]}": (12, "u")}
        )
        self.lines.append(dict(self.lines[0]))  # a second line with the same todo
        self.lines.append(
            dict(self.lines[0], todo=["take a new RC build first."])
        )  # a message's full stop goes
        order = [
            "release/1.5 is not GA for cloud yet: promote and publish it first, retire it, or force with a reason"
        ]
        todo = f"merge or close conflict PR {rm.pr_link(12)}, then Take RC again"
        self.assertEqual(
            cg.next_steps(self.lines, order),
            [todo, "take a new RC build first", "promote or retire `release/1.5`"],
        )
        self.assertEqual(
            cg.next_steps(self.lines, []), [todo, "take a new RC build first"]
        )
        table = self.checks(out, order)
        self.assertTrue(
            table[3].endswith(f"| {todo}<br>take a new RC build first |"), table[3]
        )
        self.assertTrue(
            table[4].endswith("| promote or retire `release/1.5` |"), table[4]
        )

    def test_9d_main_blocks_on_promote_order(self):
        self.decline(
            self.c, "release/1.6"
        )  # no MISSING row: only 1.5, not GA yet, holds 1.6 back
        path, md = (
            os.path.join(self.repo, "state.json"),
            os.path.join(self.repo, "out.md"),
        )
        with open(path, "w") as f:
            json.dump(rs.derive(self.repo, NOW, lambda a: self.reg.get(a, {})), f)
        with (
            contextlib.redirect_stdout(io.StringIO()),
            mock.patch.object(rs, "PINS", None),
        ):
            code = cg.main(
                [
                    "--repo",
                    self.repo,
                    "--branch",
                    "release/1.6",
                    "--target",
                    "cloud",
                    "--state",
                    path,
                    "--out",
                    md,
                ]
            )
        self.assertEqual(code, 2)
        with open(md) as f:
            self.assertIn(
                "| ⛔ promote order | release/1.5 is not GA for cloud yet |", f.read()
            )

    def test_3_scope_is_the_target(self):
        self.push("on-prem/release", "v1.5.0-rc.2", "release/1.5")
        code, out = self.run_gate("release/1.5", "on-prem")
        self.assertEqual(code, 0)
        self.assertIn("scanned branches: none", out)
        self.assertEqual(self.run_gate("release/1.5", "cloud")[0], 2)

    def test_4_ga_branch_scanned_at_its_ga_tag(self):
        self.reg["cloud/release"]["v1.6.0"] = self.reg["cloud/release"][
            "v1.6.0-rc.1"
        ]  # promote, same digest
        self.g("tag", "v1.6.0", "v1.6.0-rc.1")
        self.pick(self.c, "release/1.6")  # after GA: the tip has it, v1.6.0 does not
        code, out = self.run_gate("release/1.5")
        self.assertEqual(code, 2, out)
        self.assertIn("into `refs/tags/v1.6.0`", out)
        self.decline(self.c, "release/1.6")  # newer_branch carries the decline
        code, out = self.run_gate("release/1.5")
        self.assertEqual(code, 0, out)

    def test_5_plain_fix_owed_to_stabilized(self):
        self.reg["cloud/release"]["v1.6.0"] = self.reg["cloud/release"]["v1.6.0-rc.1"]
        self.g("tag", "v1.6.0", "v1.6.0-rc.1")  # 1.6 GA = stabilized for cloud
        code, out = self.run_gate("release/1.5")
        self.assertEqual(code, 2, out)
        self.assertIn(
            f"- `{self.tip('release/1.5')[:12]}` MISSING original {self.c[:12]}", out
        )

    def test_6_shipped_prs(self):
        """shipped_prs: a pick counts, a decline and a main-only commit do not; C has no (#n), so lookup decides."""
        d, e = (
            self.change("D: picked (#7)", "main"),
            self.change("E: declined (#8)", "main"),
        )
        self.change("F: main only (#9)", "main")
        self.pick(d, "release/1.5")
        self.g(
            "commit",
            "-q",
            "--allow-empty",
            "-m",
            f"decline E\n\n(cherry picked from commit {e})",
        )
        self.g("tag", "v1.5.1", "release/1.5")
        self.g("checkout", "-q", "main")
        self.assertEqual(
            rm.shipped_prs(self.repo, ["v1.5.1"], lookup={self.c: 5}.get), {5, 7}
        )
        with self.assertRaisesRegex(RuntimeError, "no PR number"):
            rm.shipped_prs(self.repo, ["v1.5.1"])
        self.assertEqual(rm.shipped_prs(self.repo, []), set())

    def test_7_shipped_prs_newest_trailer(self):
        """shipped_prs: newest trailer wins. A pick backed out by a later decline or revert is not shipped; a pick
        after a decline is.
        """
        d, r, p = (
            self.change(f"{x}: fix (#{n})", "main")
            for x, n in (("D", 21), ("R", 22), ("P", 23))
        )
        self.pick(d, "release/1.5")
        self.decline(d, "release/1.5")  # (a) pick, then decline
        self.pick(r, "release/1.5")
        self.revert(
            self.tip("release/1.5"), "release/1.5"
        )  # (b) pick, then the Revert button's commit
        self.decline(p, "release/1.5")
        self.pick(p, "release/1.5")  # (c) decline, then pick
        self.g("checkout", "-q", "main")
        self.assertEqual(
            rm.shipped_prs(self.repo, ["release/1.5"], lookup={self.c: 5}.get), {5, 23}
        )
        self.assertEqual(
            rm.shipped_prs(
                self.repo, ["release/1.5", "release/1.6"], lookup={self.c: 5}.get
            ),
            {5, 23},
        )

    def test_7b_shipped_prs_line_picks(self):
        """shipped_prs(line=): the new line's picks of shipped originals drop too, by lookup (clean pick, original's
        subject) or by their own (#n) (conflict squash); a pick of an original declined on the previous line, a
        release-branch-only commit and line=None do not change.
        """
        d, e = self.change("D: fix (#21)", "main"), self.change("E: fix (#22)", "main")
        f = self.change("F: fix (#23)", "main")
        self.pick(d, "release/1.5")
        self.pick(f, "release/1.5")
        self.decline(e, "release/1.5")
        self.g("tag", "v1.5.1", "release/1.5")
        self.pick(d, "release/1.6")
        pd = self.tip(
            "release/1.6"
        )  # clean pick: subject keeps (#21); its PR is found by lookup
        self.change(
            "F_squash: resolved", None
        )  # conflict pick, squashed under its PR's title; trailer abbreviated
        self.g(
            "commit",
            "-q",
            "--amend",
            "-m",
            f"UN-9 [FIX] F (#41)\n\n(cherry picked from commit {f[:12]})",
        )
        self.pick(e, "release/1.6")
        pe = self.tip("release/1.6")
        self.change("RBO: line only (#50)", "release/1.6")
        self.g("tag", "v1.6.0-rc.2", "release/1.6")
        self.g("checkout", "-q", "main")
        prs = {self.c: 5, pd: 40, pe: 42}.get
        self.assertEqual(rm.shipped_prs(self.repo, ["v1.5.1"], lookup=prs), {5, 21, 23})
        self.assertEqual(
            rm.shipped_prs(self.repo, ["v1.5.1"], lookup=prs, line="v1.6.0-rc.2"),
            {5, 21, 23, 40, 41},
        )
        self.assertEqual(
            rm.shipped_prs(
                self.repo, ["v1.5.1"], lookup={self.c: 5}.get, line="v1.6.0-rc.2"
            ),
            {5, 21, 23, 41},
        )  # no lookup hit for the clean pick: its (#21) only, nothing raised


class OssPins(unittest.TestCase):
    """Cloud 1.5 pins OSS ee-v1.5.1, which carries OSS fix F; cloud 1.6 pins ee-v1.6.0, cut before F."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.reg = {}
        self.cloud, self.oss = (os.path.join(self._tmp.name, d) for d in ("cloud", "oss"))
        for r in (self.cloud, self.oss):
            os.mkdir(r)
            rm.git(r, "init", "-q", "-b", "main")
            self.commit(r, "base")
        o = self.oss
        self.g(o, "branch", "release/1.5", "main")
        self.g(o, "branch", "release/1.6", "main")
        self.f = self.commit(o, "F: oss fix (#7)", file="f.txt")
        self.g(o, "checkout", "-q", "release/1.5")
        self.g(o, "cherry-pick", "-x", self.f)
        self.g(o, "tag", "ee-v1.5.1")
        self.g(o, "checkout", "-q", "release/1.6")
        self.commit(o, "release: ee-v1.6.0", bot=True)
        self.g(o, "tag", "ee-v1.6.0")
        self.g(o, "checkout", "-q", "main")
        self.sync()
        for line, pin in (("1.5", "ee-v1.5.1"), ("1.6", "ee-v1.6.0")):
            self.g(self.cloud, "branch", f"release/{line}", "main")
            self.repin(line, pin, f"v{line}.0-rc.1")

    def g(self, repo, *args):
        return rm.git(
            repo, "-c", "user.name=Dev", "-c", "user.email=dev@example.com", *args
        )

    def commit(self, repo, msg, file="x.txt", text=None, bot=False):
        with open(os.path.join(repo, file), "w") as f:
            f.write(text or msg)
        self.g(repo, "add", file)
        who = ["-c", "user.name=bot", "-c", f"user.email={rm.BOT_EMAIL}"] if bot else []
        rm.git(
            repo,
            *(who or ["-c", "user.name=Dev", "-c", "user.email=dev@example.com"]),
            "commit",
            "-q",
            "-m",
            msg,
        )
        return self.g(repo, "rev-parse", "HEAD")

    def sync(self):  # the OSS clone's origin/* refs, as `gh repo clone` leaves them
        for b in self.g(
            self.oss, "for-each-ref", "--format=%(refname:short)", "refs/heads/"
        ).split():
            self.g(self.oss, "update-ref", f"refs/remotes/origin/{b}", b)

    def repin(self, line, pin, rc):
        self.g(self.cloud, "checkout", "-q", f"release/{line}")
        self.commit(
            self.cloud,
            f"release: pin OSS {pin}",
            "pyproject.toml",
            f'unstract-platform-version = "{pin}"\n',
            bot=True,
        )
        self.g(self.cloud, "tag", rc)
        self.g(self.cloud, "checkout", "-q", "main")
        reg = self.reg.setdefault("cloud/release", {})
        reg[rc] = {
            "digest": f"sha256:{len(reg):064x}",
            "pushed_at": "2026-09-28T00:00:00Z",
        }

    def run_gate(self, branch):
        state = rs.derive(self.cloud, NOW, lambda a: self.reg.get(a, {}))
        with contextlib.redirect_stdout(io.StringIO()):
            code, out, lines = cg.gate(
                self.cloud,
                branch,
                "cloud",
                state,
                annotate="error",
                lookup=lambda h: None,
                failure=lambda n, b: None,
                oss_repo=self.oss,
            )
        return code, "\n".join(out), lines

    def test_10a_missing_oss_fix_names_the_oss_line_then_the_rc(self):
        code, out, lines = self.run_gate("release/1.6")
        self.assertEqual(code, 2)
        self.assertIn(
            "Cannot promote release/1.6 for cloud: OSS fix "
            + self.f[:7]
            + " (OSS PR #7) is in release/1.5's "
            "OSS pin ee-v1.5.1 but not in release/1.6's pin ee-v1.6.0: pick it onto OSS release/1.6 (OSS "
            "Backport), then take a new RC of release/1.6.",
            out,
        )
        self.assertEqual(
            [(x["line"], x["side"], x["summary"]) for x in lines if x.get("oss")],
            [("release/1.5", "older", "1 OSS picks, 0 in ee-v1.6.0, 1 missing")],
        )
        table, _ = cg.checks(lines, [], out.splitlines(), split=True)
        self.assertTrue(
            any(r.startswith("| ⛔ OSS pins match the other lines |") for r in table),
            table,
        )
        self.assertEqual(
            table[3],
            "| ✅ fixes match older lines | `release/1.5` 0 picks, 0 in the RC | - |",
        )  # cloud rows: cloud only
        # The fix reaches the OSS line: the pin, not OSS, is behind now.
        self.g(self.oss, "checkout", "-q", "release/1.6")
        self.g(self.oss, "cherry-pick", "-x", self.f)
        self.g(self.oss, "checkout", "-q", "main")
        self.sync()
        code, out, _ = self.run_gate("release/1.5")  # same scan from the older side
        self.assertEqual(code, 2)
        self.assertIn(": take a new RC of release/1.6 to pin OSS release/1.6's tip.", out)

    def test_10b_repinned_newer_line_converges(self):
        self.g(self.oss, "checkout", "-q", "release/1.6")
        self.g(self.oss, "cherry-pick", "-x", self.f)
        self.g(self.oss, "tag", "ee-v1.6.1")
        self.g(self.oss, "checkout", "-q", "main")
        self.sync()
        self.repin("1.6", "ee-v1.6.1", "v1.6.0-rc.2")
        code, out, lines = self.run_gate("release/1.6")
        self.assertEqual(code, 0, out)
        self.assertEqual(
            [x["summary"] for x in lines if x.get("oss")], ["1 OSS picks, 1 in ee-v1.6.1"]
        )
        self.repin("1.6", "ee-v1.5.1", "v1.6.0-rc.3")  # one shared pin: nothing to scan
        self.assertEqual(
            [x["summary"] for x in self.run_gate("release/1.6")[2] if x.get("oss")],
            ["0 OSS picks, 0 in ee-v1.5.1"],
        )

    def test_10d_decline_on_the_oss_line_converges(self):
        # Declined on OSS release/1.6 after ee-v1.6.0: the line owes nothing, though the pinned tag predates the decline.
        self.g(self.oss, "checkout", "-q", "release/1.6")
        self.g(
            self.oss,
            "commit",
            "-q",
            "--allow-empty",
            "-m",
            f"decline F\n\n(cherry picked from commit {self.f})",
        )
        self.g(self.oss, "checkout", "-q", "main")
        self.sync()
        code, out, _ = self.run_gate("release/1.6")
        self.assertEqual(code, 0, out)

    def test_10c_pinning_repo_needs_the_oss_clone(self):
        with (
            contextlib.redirect_stdout(io.StringIO()) as buf,
            contextlib.redirect_stderr(io.StringIO()) as err,
        ):
            code = cg.main(
                ["--repo", self.cloud, "--branch", "release/1.6", "--target", "cloud"]
            )
        self.assertEqual(code, 1)
        self.assertIn(
            "::error::convgate: RuntimeError: --oss-repo (or OSS_REPO) is required",
            buf.getvalue(),
        )
        self.assertIn("Traceback", err.getvalue())  # where it failed, not only what
        self.g(self.oss, "tag", "-d", "ee-v1.6.0")
        with self.assertRaisesRegex(RuntimeError, "no OSS tag ee-v1.6.0"):
            self.run_gate("release/1.6")


if __name__ == "__main__":
    unittest.main()
