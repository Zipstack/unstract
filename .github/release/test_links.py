import os
import unittest
from unittest import mock

import relmgr as rm

ACTIONS = {
    "GITHUB_SERVER_URL": "https://github.com",
    "GITHUB_REPOSITORY": "Zipstack/example",
    "RELSTATE_AR_ON_PREM": "projects/p/locations/l/repositories/r",
}
WEB = "https://github.com/Zipstack/example"
SHA = "6635951" + "0" * 33


class Links(unittest.TestCase):
    def test_actions(self):
        with mock.patch.dict(os.environ, ACTIONS):
            self.assertEqual(rm.pr_link(246), f"[#246]({WEB}/pull/246)")
            self.assertEqual(rm.commit_link(SHA), f"[`6635951`]({WEB}/commit/{SHA})")
            self.assertEqual(
                rm.tag_link("v0.192.0-rc.1"),
                f"[`v0.192.0-rc.1`]({WEB}/releases/tag/v0.192.0-rc.1)",
            )
            self.assertEqual(rm.run_link(9), f"[run]({WEB}/actions/runs/9)")
            self.assertEqual(
                rm.image_link("on-prem", "v0.192.0-rc.1"),
                "[`on-prem:v0.192.0-rc.1`](https://console.cloud.google.com/artifacts/docker/p/l/r)",
            )

    def test_plain_outside_actions(self):
        with mock.patch.dict(os.environ, clear=True):
            self.assertEqual(rm.pr_link(246), "#246")
            self.assertEqual(rm.commit_link(SHA), "`6635951`")
            self.assertEqual(rm.tag_link("v0.192.0-rc.1"), "`v0.192.0-rc.1`")
            self.assertEqual(rm.run_link(9), "run 9")
            self.assertEqual(
                rm.image_link("cloud", "v0.192.0-rc.1"), "`cloud:v0.192.0-rc.1`"
            )


if __name__ == "__main__":
    unittest.main()
