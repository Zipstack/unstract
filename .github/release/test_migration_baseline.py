"""Tests for migration_baseline, the Lint PR check that the migration baseline is current. Run: python test_migration_baseline.py"""

import contextlib
import io
import os
import subprocess
import tempfile
import unittest
from unittest import mock

import migration_baseline as mb

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, "..", "..")

FRESH = "# Released migrations.\n# released-through: origin/release/0.187 @ 3a76b8544\nab  account_v2/migrations/0001_initial.py\n"
BRANCHES = [
    "main",
    "release/0.186",
    "release/0.187",
    "release/v0.90",
    "backport/0.187/abc1234",
]


class NewestRelease(unittest.TestCase):
    def test_highest_line_by_number_not_by_text(self):
        self.assertEqual(
            mb.newest_release(["release/0.99", "release/0.100", "release/0.9"]),
            "release/0.100",
        )
        self.assertEqual(
            mb.newest_release(["release/1.2", "release/0.187"]), "release/1.2"
        )

    def test_only_release_lines_count(self):
        names = [
            "main",
            "release/v0.200",
            "release/0.187-hotfix",
            "x/release/0.999",
            "release/0.187",
            "release/0.188/x",
        ]
        self.assertEqual(mb.newest_release(names), "release/0.187")
        self.assertIsNone(mb.newest_release(["main", "release/v0.90"]))
        self.assertIsNone(mb.newest_release([]))


class TouchesMigrations(unittest.TestCase):
    def test_migration_files_under_backend(self):
        for path in (
            "backend/account_v2/migrations/0012_x.py",
            "backend/workflow_manager/workflow_v2/migrations/0030_x.py",
            "backend/tenant_account_v2/migrations/_helper.py",
        ):
            self.assertTrue(mb.touches_migrations(["README.md", path]), path)

    def test_everything_else(self):
        paths = [
            "backend/account_v2/models.py",
            "backend/account_v2/tests/test_migrations.py",
            "backend/account_v2/migrations/README.md",
            "backend/account_v2/migrations/data/rows.py",
            "backend/migrating/v2/unstract_migrations.py",
            "workers/shared/migrations/0001_x.py",
            "docs/backend/x/migrations/0001_x.py",
            "",
        ]
        self.assertFalse(mb.touches_migrations(paths))
        self.assertFalse(mb.touches_migrations([]))


class StaleError(unittest.TestCase):
    def test_current(self):
        self.assertIsNone(mb.stale_error(FRESH, BRANCHES))
        self.assertIsNone(mb.stale_error(FRESH.replace("origin/", ""), BRANCHES))

    def test_behind_the_newest_line(self):
        err = mb.stale_error(FRESH, [*BRANCHES, "release/0.188"])
        self.assertEqual(
            err,
            "backend/backend/tests/migration_baseline.txt says released-through release/0.187, but the newest "
            "release branch is release/0.188. Tables created in release/0.188 are still treated as new, so the "
            "migration guard would pass changes that break it. Advance the baseline first: "
            "python backend/backend/tests/update_migration_baseline.py --ref origin/release/0.188 "
            "(if main already has the advanced baseline, merge main into this branch instead)",
        )

    def test_a_longer_line_number_is_not_the_same_line(self):
        self.assertIn(
            "says released-through release/0.18,",
            mb.stale_error(FRESH.replace("0.187", "0.18"), BRANCHES),
        )
        self.assertIn(
            "says released-through release/0.1875,",
            mb.stale_error(FRESH.replace("0.187", "0.1875"), BRANCHES),
        )

    def test_no_usable_header(self):
        for text in (
            "",
            None,
            "ab  x/migrations/0001.py\n",
            "# released-through: HEAD @ abc\n",
            "x # released-through: origin/release/0.187 @ abc\n",
        ):
            self.assertIn(
                "says released-through nothing,", mb.stale_error(text, BRANCHES), text
            )

    def test_no_release_branch_yet(self):
        self.assertIsNone(mb.stale_error("", ["main", "release/v0.90"]))
        self.assertIsNone(mb.stale_error(FRESH, ["main"]))

    def test_names_the_file_it_read(self):
        self.assertTrue(
            mb.stale_error("", BRANCHES, "some/other/baseline.txt").startswith(
                "some/other/baseline.txt says"
            )
        )


class FakeGh:
    """Answers the three API reads main() makes; anything else is a test failure."""

    def __init__(self, files, branches=BRANCHES, baseline=FRESH, fail=None):
        self.files, self.branches, self.baseline, self.fail, self.calls = (
            files,
            branches,
            baseline,
            fail,
            [],
        )

    def __call__(self, *args):
        url = next(a for a in args if a.startswith("repos/"))
        self.calls.append(url)
        if self.fail and self.fail in url:
            raise RuntimeError("gh api (exit 1): HTTP 502")
        if url == "repos/Zipstack/example/pulls/7/files?per_page=100":
            return "\n".join(self.files) + "\n"
        if url == "repos/Zipstack/example/branches?per_page=100":
            return "\n".join(self.branches) + "\n"
        if url == f"repos/Zipstack/example/contents/{mb.BASELINE}?ref=refs/pull/7/head":
            assert "Accept: application/vnd.github.raw" in args, args
            if self.baseline is None:
                raise RuntimeError("gh api (exit 1): gh: Not Found (HTTP 404)")
            return self.baseline
        raise AssertionError(f"unexpected gh call: {args}")


class Main(unittest.TestCase):
    MIGRATION = [
        "backend/account_v2/models.py",
        "backend/account_v2/migrations/0012_x.py",
    ]

    def run_main(self, gh):
        out = io.StringIO()
        with tempfile.NamedTemporaryFile("r") as summary:
            env = {
                "GITHUB_REPOSITORY": "Zipstack/example",
                "PR": "7",
                "GITHUB_STEP_SUMMARY": summary.name,
            }
            with mock.patch.dict(os.environ, env), contextlib.redirect_stdout(out):
                code = mb.main(gh)
            return code, out.getvalue(), summary.read()

    def test_a_pr_without_a_migration_reads_nothing_else(self):
        gh = FakeGh(["backend/account_v2/models.py", "frontend/src/App.jsx"], baseline="")
        code, out, summary = self.run_main(gh)
        self.assertEqual((code, summary), (0, ""))
        self.assertEqual(gh.calls, ["repos/Zipstack/example/pulls/7/files?per_page=100"])
        self.assertNotIn("::error", out)

    def test_a_migration_with_a_current_baseline_passes(self):
        code, out, summary = self.run_main(FakeGh(self.MIGRATION))
        self.assertEqual((code, summary), (0, ""))
        self.assertNotIn("::error", out)

    def test_a_migration_with_a_stale_baseline_fails(self):
        gh = FakeGh(self.MIGRATION, branches=[*BRANCHES, "release/0.188"])
        code, out, summary = self.run_main(gh)
        self.assertEqual(code, 1)
        self.assertIn(
            "::error title=Lint PR::backend/backend/tests/migration_baseline.txt says released-through release/0.187",
            out,
        )
        self.assertIn("--ref origin/release/0.188", out)
        self.assertEqual(
            out.count("\n"), 1
        )  # a workflow command ends at the first newline
        self.assertIn("### Lint PR: migration baseline is stale", summary)
        self.assertIn("--ref origin/release/0.188", summary)

    def test_a_path_with_a_space_is_one_path(self):
        gh = FakeGh(["backend/odd dir/migrations/0001_x.py"], baseline=None)
        self.assertEqual(self.run_main(gh)[0], 1)

    def test_a_head_without_the_baseline_file_fails(self):
        code, out, _ = self.run_main(FakeGh(self.MIGRATION, baseline=None))
        self.assertEqual(code, 1)
        self.assertIn(
            "says released-through nothing, but the newest release branch is release/0.187",
            out,
        )

    def test_a_failed_read_fails_the_check_and_says_so(self):
        for part in ("/files", "/branches", "/contents/"):
            code, out, summary = self.run_main(FakeGh(self.MIGRATION, fail=part))
            self.assertEqual((code, summary), (1, ""), part)
            self.assertIn(
                "::error title=Lint PR::could not check the migration baseline; re-run the job",
                out,
            )
            self.assertIn("HTTP 502", out)

    def test_gh_errors_carry_the_exit_code_and_stderr(self):
        failed = mock.Mock(returncode=1, stdout="", stderr="gh: Not Found (HTTP 404)\n")
        with mock.patch.object(mb.subprocess, "run", return_value=failed) as run:
            with self.assertRaisesRegex(
                RuntimeError, r"gh api repos/x \(exit 1\): gh: Not Found \(HTTP 404\)"
            ):
                mb._gh("api", "repos/x", "--jq", ".")
        self.assertEqual(run.call_args.args[0], ["gh", "api", "repos/x", "--jq", "."])
        ok = mock.Mock(returncode=0, stdout="a\nb\n", stderr="")
        with mock.patch.object(mb.subprocess, "run", return_value=ok):
            self.assertEqual(mb._gh("api", "repos/x"), "a\nb\n")


def step(workflow, name):
    """(the `if:` of the named step, its `run:` script)."""
    with open(os.path.join(ROOT, ".github", "workflows", workflow)) as fh:
        lines = fh.read().split("\n")
    i = lines.index(f"      - name: {name}")
    condition = next(l.strip() for l in lines[i:] if l.strip().startswith("if: "))
    i = next(n for n in range(i, len(lines)) if lines[n].strip() == "run: |")
    indent = len(lines[i]) - len(lines[i].lstrip()) + 2
    body = []
    for line in lines[i + 1 :]:
        if line.strip() and len(line) - len(line.lstrip()) < indent:
            break
        body.append(line[indent:])
    return condition, "\n".join(body)


class LintPrStep(unittest.TestCase):
    """The Lint PR step, run as the runner runs it, against a fake gh."""

    GH = """#!/bin/sh
case "$*" in
  *"/pulls/7/files?per_page=100 --jq .[].filename") cat "$FIXTURE/files";;
  *"/branches?per_page=100 --jq .[].name") cat "$FIXTURE/branches";;
  *"/contents/backend/backend/tests/migration_baseline.txt?ref=refs/pull/7/head")
    [ -f "$FIXTURE/baseline" ] && cat "$FIXTURE/baseline" && exit 0
    echo "gh: Not Found (HTTP 404)" >&2; exit 1;;
  *) echo "unexpected gh call: $*" >&2; exit 2;;
esac
"""

    def lint(self, files, branches, baseline, cwd=ROOT):
        condition, script = step("lint-pr.yaml", "Migration baseline is current")
        self.assertEqual(
            condition, "if: ${{ !cancelled() && github.base_ref == 'main' }}"
        )
        with tempfile.TemporaryDirectory() as d:
            for name, text in (
                ("files", files),
                ("branches", branches),
                ("baseline", baseline),
            ):
                if text is not None:
                    with open(os.path.join(d, name), "w") as fh:
                        fh.write(text)
            with open(os.path.join(d, "gh"), "w") as fh:
                fh.write(self.GH)
            os.chmod(os.path.join(d, "gh"), 0o755)
            r = subprocess.run(
                ["bash", "-e", "-c", script],
                cwd=cwd,
                env={
                    **os.environ,
                    "PATH": f"{d}:{os.environ['PATH']}",
                    "FIXTURE": d,
                    "GITHUB_REPOSITORY": "Zipstack/example",
                    "PR": "7",
                    "GITHUB_STEP_SUMMARY": os.path.join(d, "summary"),
                },
                capture_output=True,
                text=True,
            )
            return r.returncode, r.stdout + r.stderr

    MIGRATION = "backend/account_v2/models.py\nbackend/account_v2/migrations/0012_x.py\n"
    BRANCHES = "main\nrelease/0.186\nrelease/0.187\nrelease/v0.90\n"

    def test_a_stale_baseline_fails_a_pr_that_changes_a_migration(self):
        rc, out = self.lint(self.MIGRATION, self.BRANCHES + "release/0.188\n", FRESH)
        self.assertEqual(rc, 1, out)
        self.assertIn(
            "::error title=Lint PR::backend/backend/tests/migration_baseline.txt says released-through "
            "release/0.187, but the newest release branch is release/0.188.",
            out,
        )
        self.assertIn(
            "python backend/backend/tests/update_migration_baseline.py --ref origin/release/0.188",
            out,
        )

    def test_a_current_baseline_passes(self):
        rc, out = self.lint(self.MIGRATION, self.BRANCHES, FRESH)
        self.assertEqual(
            (rc, out), (0, "backend/backend/tests/migration_baseline.txt is current.\n")
        )

    def test_a_head_without_a_baseline_fails(self):
        rc, out = self.lint(self.MIGRATION, self.BRANCHES, None)
        self.assertEqual(rc, 1, out)
        self.assertIn("says released-through nothing", out)

    def test_a_pr_without_a_migration_passes_whatever_the_baseline_says(self):
        rc, out = self.lint(
            "backend/account_v2/models.py\n", self.BRANCHES + "release/0.188\n", FRESH
        )
        self.assertEqual(
            (rc, out), (0, "No migration in this PR: the baseline is not checked.\n")
        )

    def test_a_main_that_predates_the_check_skips_it(self):
        # The step reads the module from main's checkout; until main has it there is nothing to import.
        with tempfile.TemporaryDirectory() as empty:
            rc, out = self.lint(
                self.MIGRATION, self.BRANCHES + "release/0.188\n", FRESH, cwd=empty
            )
        self.assertEqual(rc, 0, out)
        self.assertIn(
            "::notice title=Lint PR::migration baseline check skipped: No module named",
            out,
        )


class ReleaseBranchCiStep(unittest.TestCase):
    """A release-branch-only PR cannot carry a migration: no test tier runs on a release branch."""

    NAME = "No migration in a release-branch-only PR"

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.repo = tmp.name
        self.git("init", "-q", "-b", "main")
        self.commit(
            {
                "backend/app/migrations/0001_initial.py": "one\n",
                "backend/app/models.py": "m\n",
            }
        )
        self.git("update-ref", "refs/remotes/origin/release/1.0", "HEAD")
        self.git("checkout", "-q", "-b", "topic")

    def git(self, *args):
        env = {**os.environ, "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_NOSYSTEM": "1"}
        identity = ["-c", "user.name=Dev", "-c", "user.email=dev@example.com"]
        subprocess.run(
            ["git", "-C", self.repo, *identity, *args],
            check=True,
            env=env,
            capture_output=True,
        )

    def commit(self, files):
        """files: path -> content, None to delete."""
        for path, content in files.items():
            full = os.path.join(self.repo, path)
            if content is None:
                os.remove(full)
                continue
            os.makedirs(os.path.dirname(full), exist_ok=True)
            with open(full, "w") as fh:
                fh.write(content)
        self.git("add", "--", *files)
        self.git("commit", "-q", "-m", "change")

    def check(self):
        _, script = step("release-branch-ci.yaml", self.NAME)
        r = subprocess.run(
            ["bash", "-e", "-c", script],
            cwd=self.repo,
            env={**os.environ, "BRANCH": "release/1.0"},
            capture_output=True,
            text=True,
        )
        return r.returncode, r.stdout + r.stderr

    def test_only_a_labelled_pr_is_checked(self):
        condition, _ = step("release-branch-ci.yaml", self.NAME)
        self.assertEqual(
            condition,
            "if: github.event_name == 'pull_request' && steps.labels.outputs.rbo == 'true'",
        )

    def test_a_new_an_edited_and_a_deleted_migration_fail(self):
        for label, files in (
            ("new", {"backend/app/migrations/0002_more.py": "two\n"}),
            ("edited", {"backend/app/migrations/0001_initial.py": "one, edited\n"}),
            ("deleted", {"backend/app/migrations/0001_initial.py": None}),
            ("nested app", {"backend/a/b/migrations/0001_initial.py": "x\n"}),
        ):
            with self.subTest(label):
                self.git(
                    "checkout", "-q", "-B", "topic", "refs/remotes/origin/release/1.0"
                )
                self.commit({"backend/app/models.py": "changed\n", **files})
                rc, out = self.check()
                self.assertEqual(rc, 1, out)
                self.assertIn(
                    "::error title=Release branch CI::a release-branch-only PR cannot add or change "
                    f"a migration ({next(iter(files))}).",
                    out,
                )

    def test_a_pr_without_a_migration_passes(self):
        self.commit(
            {
                "backend/app/models.py": "changed\n",
                "backend/app/tests/test_migrations.py": "t\n",
            }
        )
        self.assertEqual(self.check(), (0, ""))

    def test_a_migration_that_only_the_release_branch_gained_is_not_the_prs(self):
        self.commit({"backend/app/models.py": "changed\n"})
        self.git("checkout", "-q", "-b", "line", "refs/remotes/origin/release/1.0")
        self.commit({"backend/app/migrations/0002_picked.py": "picked from main\n"})
        self.git("update-ref", "refs/remotes/origin/release/1.0", "HEAD")
        self.git("checkout", "-q", "topic")
        self.assertEqual(self.check(), (0, ""))

    def test_an_unreadable_base_fails_the_step(self):
        self.git("update-ref", "-d", "refs/remotes/origin/release/1.0")
        rc, out = self.check()
        self.assertNotEqual(rc, 0, out)


if __name__ == "__main__":
    unittest.main()
