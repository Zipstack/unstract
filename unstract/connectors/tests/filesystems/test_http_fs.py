import os
import unittest

import pytest
from unstract.connectors.filesystems.http.http import HttpFS

# Live-HTTP test — integration tier only, so `unit-connectors` (-m "not
# integration") never selects it even when HTTP_FS_TEST_URL is set.
pytestmark = pytest.mark.integration


class TestHttpFS(unittest.TestCase):
    # Needs a reachable HTTP server. Start one locally, e.g.
    #   python -m http.server -b localhost 8080
    # then run with HTTP_FS_TEST_URL=http://localhost:8080/. Skip-guarded so it
    # never hits a hard-coded live URL during a plain unit run.
    @unittest.skipUnless(
        os.environ.get("HTTP_FS_TEST_URL"),
        "Integration test requires a reachable HTTP server via HTTP_FS_TEST_URL",
    )
    def test_basic(self):
        self.assertEqual(HttpFS.can_write(), False)
        http_fs = HttpFS(settings={"base_url": os.environ["HTTP_FS_TEST_URL"]})
        files = http_fs.get_fsspec_fs().ls("/")
        self.assertIsNotNone(files)


if __name__ == "__main__":
    unittest.main()
