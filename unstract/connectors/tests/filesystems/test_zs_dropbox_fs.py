import os
import unittest

import pytest
from unstract.connectors.filesystems.zs_dropbox import DropboxFS

# Whole module needs live infra/credentials — integration tier only.
pytestmark = pytest.mark.integration


class TestDropboxFS(unittest.TestCase):
    @unittest.skipUnless(
        os.environ.get("TEST_DROPBOX_ACCESS_TOKEN"),
        "Integration test requires TEST_DROPBOX_ACCESS_TOKEN",
    )
    def test_access_token(self):
        access_token = os.environ.get("TEST_DROPBOX_ACCESS_TOKEN")
        settings = {"token": access_token}
        dropbox_fs = DropboxFS(settings=settings)
        # Leave empty for root
        file_path = ""
        try:
            files = dropbox_fs.get_fsspec_fs().ls(file_path)
            self.assertIsNotNone(files)
        except Exception as e:
            self.fail(f"TestDropboxFS.test_access_token failed: {e}")


if __name__ == "__main__":
    unittest.main()
