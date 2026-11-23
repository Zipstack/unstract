import contextlib
import io
import json
import unittest
from unittest import mock

import relabel_line_labels as rl


class Relabel(unittest.TestCase):
    """The one-time switch, against a fake gh."""

    PRS = {
        "is:open": [
            {
                "number": 1,
                "title": "both",
                "state": "OPEN",
                "labels": [{"name": "backport/rc"}, {"name": "backport/ga"}],
            },
            {"number": 2, "title": "plain", "state": "OPEN", "labels": [{"name": "bug"}]},
            {
                "number": 3,
                "title": "has a line",
                "state": "OPEN",
                "labels": [{"name": "backport/rc"}, {"name": "backport/0.188"}],
            },
        ],
        "merged": [
            {
                "number": 1,
                "title": "both",
                "state": "OPEN",
                "labels": [{"name": "backport/rc"}, {"name": "backport/ga"}],
            },
            {
                "number": 4,
                "title": "rc fix",
                "state": "MERGED",
                "labels": [{"name": "backport/rc"}],
            },
        ],
    }

    def gh(self, *args):
        self.calls.append(args)
        if "matching-refs/heads/release/" in " ".join(args):
            return "refs/heads/release/0.188\nrefs/heads/release/0.187\nrefs/heads/release/0.186"
        if args[:2] == ("pr", "list"):
            search = args[args.index("--search") + 1]
            return json.dumps(self.PRS["is:open" if search == "is:open" else "merged"])
        if args in self.fail:
            raise RuntimeError("gh: Server Error (HTTP 502)")
        return ""

    def run_main(self, *argv, fail=()):
        self.calls, self.fail = [], set(fail)
        err = io.StringIO()
        with (
            mock.patch.object(rl, "gh", side_effect=self.gh),
            contextlib.redirect_stdout(io.StringIO()),
            contextlib.redirect_stderr(err),
        ):
            code = rl.main(
                [
                    "--rc",
                    "0.187",
                    "--ga",
                    "0.186",
                    "--since",
                    "2026-11-03",
                    "--repo",
                    "o/r",
                    *argv,
                ]
            )
        return (
            code,
            [
                c
                for c in self.calls
                if c[0] == "api" and "matching-refs" not in " ".join(c)
            ],
            err.getvalue(),
        )

    def add(self, n, label):
        return ("api", f"repos/o/r/issues/{n}/labels", "-f", f"labels[]={label}")

    def drop(self, n, label):
        return (
            "api",
            "-X",
            "DELETE",
            f"repos/o/r/issues/{n}/labels/{label.replace('/', '%2F')}",
        )

    def test_plan_maps_each_pr_to_the_oldest_line(self):
        code, api, _ = self.run_main()
        self.assertEqual(code, 0)
        self.assertEqual(api, [])  # a dry run writes nothing
        code, api, _ = self.run_main("--apply")
        self.assertEqual(code, 0)
        self.assertEqual(
            api,
            [
                self.add(1, "backport/0.186"),  # ga is the older line
                self.drop(1, "backport/ga"),
                self.drop(1, "backport/rc"),
                self.drop(
                    3, "backport/rc"
                ),  # already has a line label: only the old one goes
                self.add(4, "backport/0.187"),
                self.drop(4, "backport/rc"),
            ],
        )  # #1 comes from both searches once; #2 has no old label

    def test_a_failed_add_keeps_the_old_labels(self):
        code, api, err = self.run_main("--apply", fail=[self.add(1, "backport/0.186")])
        self.assertEqual(code, 1)
        self.assertNotIn(self.drop(1, "backport/rc"), api)
        self.assertNotIn(self.drop(1, "backport/ga"), api)
        self.assertIn(self.drop(4, "backport/rc"), api)  # other PRs carry on
        self.assertIn("old one stays", err)

    def test_no_line_in_rc_maps_rc_to_main_only(self):
        _, api, _ = self.run_main("--apply", "--rc", "main-only")
        self.assertIn(self.add(4, "main-only"), api)
        self.assertIn(self.add(1, "backport/0.186"), api)

    def test_lines_must_be_active(self):
        with self.assertRaises(SystemExit) as e:
            self.run_main("--ga", "0.185")
        self.assertIn("0.185 is not an active line", str(e.exception))
        with self.assertRaises(SystemExit), contextlib.redirect_stderr(io.StringIO()):
            self.run_main("--ga", "main-only")


if __name__ == "__main__":
    unittest.main()
