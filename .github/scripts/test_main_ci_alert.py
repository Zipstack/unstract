"""Tests for main-ci-alert.sh, run with DRY_RUN=1 against a stub `gh`.

Run: python3 -m unittest discover -s .github/scripts -p 'test_main_ci_alert.py'

The fixtures in testdata/main-ci-alert are real API responses, trimmed to the
fields the script reads: compare.json is Zipstack/unstract e7da3686...332b4e3c
(four PRs), compare-long.json is 846fad54...119835db (300 commits, so compare
stops at 250), and each pulls-<sha>.json is repos/<repo>/commits/<sha>/pulls.
pulls-84ef6f7c is dependabot PR #2087. runs-after-failure.json is ci-test.yaml's
completed push runs on main created before 2026-09-24T09:59:38Z (newest one
failed). main has no cancelled push run, so runs-after-cancelled.json is
cancelled PR run 29990469171 followed by main's push runs created before it;
the stub ignores the query's filters. No startup_failure or timed_out run exists
in this repo to take one from.
"""

import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
SCRIPT = HERE / "main-ci-alert.sh"
DATA = HERE / "testdata" / "main-ci-alert"

BASE = "e7da36865f7da09e6692299f386c5c129ede6750"
HEAD = "332b4e3c0e5cb8237180f95f350d7c1aa7401bdb"
URL = "https://github.com/Zipstack/unstract"
GREEN = {"workflow_runs": [{"head_sha": BASE, "conclusion": "success"}]}

# Answers `gh api <path>` from the fixtures, applying --jq the way gh does, and
# logs each call's arguments to $CALLS.
STUB = r"""#!/usr/bin/env bash
set -euo pipefail
shift
echo "$*" >>"$CALLS"
expr=.
path=
while [ $# -gt 0 ]; do
  case $1 in
    -X|-f) shift 2 ;;
    --jq) expr=$2; shift 2 ;;
    *) path=$1; shift ;;
  esac
done
# GH_FAIL is a glob: calls whose path matches it fail.
if [ -n "${GH_FAIL:-}" ] && [[ $path == $GH_FAIL ]]; then
  echo "stub: forced failure" >&2; exit 1
fi
case $path in
  */runs) echo "$RUNS" | jq -r "$expr" ;;
  */compare/*) jq -r "$expr" "$DATA/$COMPARE" ;;
  */pulls)
    sha=${path%/pulls}
    file=$DATA/pulls-${sha##*/}.json
    if [ -f "$file" ]; then cat "$file"; else echo '[]'; fi ;;
  *) echo "stub: unexpected path $path" >&2; exit 1 ;;
esac
"""


class MainCiAlertTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        stub = Path(self.tmp.name) / "gh"
        stub.write_text(STUB)
        stub.chmod(0o755)
        # macOS has no `timeout`; the script's 20s limit is not under test.
        shim = Path(self.tmp.name) / "timeout"
        shim.write_text('#!/usr/bin/env bash\nshift\nexec "$@"\n')
        shim.chmod(0o755)
        self.calls = Path(self.tmp.name) / "calls"
        self.path = f"{self.tmp.name}:{os.environ['PATH']}"

    def tearDown(self):
        self.tmp.cleanup()

    def alert(self, runs=GREEN, head=HEAD, compare="compare.json", **env):
        if isinstance(runs, str):
            runs = json.loads((DATA / runs).read_text())
        result = subprocess.run(
            [str(SCRIPT)],
            env={
                "PATH": self.path,
                "CALLS": str(self.calls),
                "DRY_RUN": "1",
                "DATA": str(DATA),
                "RUNS": json.dumps(runs),
                "COMPARE": compare,
                "REPO": "Zipstack/unstract",
                "SERVER_URL": "https://github.com",
                "WORKFLOW_ID": "1",
                "WORKFLOW_NAME": "Run tests (unit + integration + e2e)",
                "RUN_URL": "https://example.invalid/run",
                "ALERT_RUN_URL": "https://example.invalid/alert",
                "RUN_CREATED": "2026-11-10T00:00:00Z",
                "HEAD_SHA": head,
                **env,
            },
            capture_output=True,
            text=True,
            check=True,
        )
        # Drop workflow commands such as ::warning:: ahead of the payload.
        payload = "\n".join(
            line for line in result.stdout.splitlines() if not line.startswith("::")
        )
        return json.loads(payload)["text"].split("\n")[1:]

    def call(self, prefix):
        return next(
            c for c in self.calls.read_text().splitlines() if c.startswith(prefix)
        )

    def test_lists_every_pr_since_the_green_run_newest_first(self):
        self.assertEqual(
            self.alert(),
            [
                "PRs merged since the last green run:",
                f"• <{URL}/pull/2430|#2430> UN-4616 [FIX] Leave the page for logout so its redirects complete by @athul-rs",
                f"• <{URL}/pull/2385|#2385> UN-4427 [FEAT] Remove the legacy 90-page / 14 MiB image-mode bound by @praveen-formido",
                f"• <{URL}/pull/2371|#2371> UN-4492 [FEAT] Image output mode: honour 'Pages to extract' and label pages with document page numbers by @praveen-formido",
                f"• <{URL}/pull/2399|#2399> UN-4299 [FEAT] v1 design tokens, themes and style isolation (P0-T04) by @praveen-formido",
            ],
        )

    def test_runs_query_asks_for_completed_push_runs_on_main_before_this_one(self):
        self.alert()
        args = self.call("-X GET repos/Zipstack/unstract/actions/workflows/1/runs")
        for f in (
            "branch=main",
            "event=push",
            "status=completed",
            "created=<2026-11-10T00:00:00Z",
            "per_page=100",
        ):
            self.assertIn(f"-f {f} ", args)

    def test_cancelled_runs_are_skipped_when_picking_the_baseline(self):
        lines = self.alert(runs="runs-after-cancelled.json")
        self.assertEqual(lines[0], "PRs merged since the last green run:")
        self.assertIn(
            "compare/a03fcf8e36b5664dd6ed901eac8b7a591af87dbf...",
            self.call("repos/Zipstack/unstract/compare/"),
        )

    def test_already_failing_main_lists_only_prs_since_that_failure(self):
        lines = self.alert(runs="runs-after-failure.json")
        self.assertEqual(
            lines[0], "`main` was already failing at 8333302. PRs merged since then:"
        )
        self.assertIn(
            "compare/8333302271b5ec407d6bbb8c07f991274de7ebb6...",
            self.call("repos/Zipstack/unstract/compare/"),
        )

    def test_cap_reports_the_commits_left_unchecked(self):
        lines = self.alert(MAX_LINES="2")
        self.assertEqual(len(lines), 4)
        self.assertEqual(lines[-1], "…2 older commits not checked")

    def test_time_budget_reports_the_commits_left_unchecked(self):
        self.assertEqual(
            self.alert(BUDGET="0"),
            ["PRs merged since the last green run:", "…4 older commits not checked"],
        )

    def test_without_a_decided_run_only_the_head_is_checked(self):
        self.assertEqual(
            self.alert(
                runs={"workflow_runs": []},
                head="3b08df2d55ae4813a09f78cfaaf479feb5234b41",
            ),
            [
                "No earlier passed or failed run on `main`, so only the head commit is checked:",
                f"• <{URL}/pull/2041|#2041> [FIX] Bump Authlib 1.2.1 -&gt; 1.6.12 &amp; PyMySQL 1.1.0 -&gt; 1.1.1 (clear critical Dependabot alerts) by @jaseemjaskp",
            ],
        )

    def test_angle_brackets_in_titles_are_escaped(self):
        lines = self.alert(
            runs={"workflow_runs": []},
            head="16bc41848012a770137f27613c94ef3d922a0578",
        )
        self.assertEqual(
            lines[1],
            f"• <{URL}/pull/1845|#1845> [FIX] Pin qdrant-client&lt;1.17.0 and enhance uv-lock transitive dep detection by @chandrasekharan-zipstack",
        )

    def test_bot_prs_are_left_out(self):
        lines = self.alert(
            runs={"workflow_runs": []},
            head="84ef6f7c29e5d41bc1a082fe75379d1fa56d13a1",
        )
        self.assertEqual(lines[1:], ["no human-authored PRs"])

    def test_compare_truncation_is_reported(self):
        lines = self.alert(compare="compare-long.json")
        self.assertEqual(
            lines[-1], "…50 older commits not listed: compare returns at most 250"
        )

    def test_a_failed_pr_lookup_skips_only_that_commit(self):
        lines = self.alert(
            GH_FAIL="*/commits/9f7c090652cf6857daa1d6ac0d2214ee49bc2758/pulls"
        )
        self.assertIn("• 9f7c090: could not look up its PR", lines)
        self.assertEqual(len(lines), 5)

    def test_alert_still_posts_when_the_list_fails(self):
        for call in ("*/runs", "*/compare/*"):
            with self.subTest(call=call):
                self.assertEqual(
                    self.alert(GH_FAIL=call),
                    [
                        "Could not list the PRs behind this failure; see <https://example.invalid/alert|the alert job's log>."
                    ],
                )

    def test_watched_workflows_exist_by_name(self):
        # workflow_run matches by display name, so a rename silently stops alerts.
        workflows = HERE.parent / "workflows"
        names = {
            line.removeprefix("name:").strip()
            for f in workflows.glob("*.y*ml")
            for line in f.read_text().splitlines()
            if line.startswith("name:")
        }
        alert = (workflows / "main-ci-alert.yaml").read_text().split("workflows:")[1]
        watched = [
            line.strip().removeprefix("- ").strip('"')
            for line in alert.split("types:")[0].splitlines()
            if line.strip()
        ]
        self.assertEqual(len(watched), 1)
        for name in watched:
            self.assertIn(name, names)


if __name__ == "__main__":
    unittest.main()
