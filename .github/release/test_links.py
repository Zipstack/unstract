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
            self.assertEqual(
                rm.branch_link("release/0.192"),
                f"[`release/0.192`]({WEB}/tree/release/0.192)",
            )
            oss = "https://github.com/Zipstack/unstract"
            self.assertEqual(
                rm.tag_link("v0.192.0", "Zipstack/unstract"),
                f"[`v0.192.0`]({oss}/releases/tag/v0.192.0)",
            )
            self.assertEqual(
                rm.branch_link("release/0.192", "Zipstack/unstract"),
                f"[`release/0.192`]({oss}/tree/release/0.192)",
            )
            self.assertEqual(
                rm.pr_link(30, "Zipstack/unstract"),
                f"[Zipstack/unstract#30]({oss}/pull/30)",
            )
            self.assertEqual(
                rm.ref_link("refs/tags/v0.192.0"),
                f"[`refs/tags/v0.192.0`]({WEB}/releases/tag/v0.192.0)",
            )
            self.assertEqual(
                rm.ref_link("refs/remotes/origin/release/0.192", "Zipstack/unstract"),
                f"[`refs/remotes/origin/release/0.192`]({oss}/tree/release/0.192)",
            )
            self.assertEqual(
                rm.ref_link("refs/heads/release/0.192"),
                f"[`refs/heads/release/0.192`]({WEB}/tree/release/0.192)",
            )
            self.assertEqual(rm.ref_link(SHA), f"`{SHA}`")
            self.assertEqual(
                rm.image_link("on-prem", "v0.192.0-rc.1"),
                "[`on-prem:v0.192.0-rc.1`](https://console.cloud.google.com/artifacts/docker/p/l/r)",
            )

    def test_plain_outside_actions(self):
        with mock.patch.dict(os.environ, clear=True):
            self.assertEqual(rm.pr_link(246), "#246")
            self.assertEqual(rm.commit_link(SHA), "`6635951`")
            self.assertEqual(rm.tag_link("v0.192.0-rc.1"), "`v0.192.0-rc.1`")
            self.assertEqual(rm.pr_link(30, "Zipstack/unstract"), "Zipstack/unstract#30")
            self.assertEqual(rm.ref_link("refs/tags/v0.192.0"), "`refs/tags/v0.192.0`")
            self.assertEqual(
                rm.branch_link("release/0.192", "Zipstack/unstract"), "`release/0.192`"
            )
            self.assertEqual(
                rm.image_link("cloud", "v0.192.0-rc.1"), "`cloud:v0.192.0-rc.1`"
            )


if __name__ == "__main__":
    unittest.main()
