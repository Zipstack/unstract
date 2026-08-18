import os
import unittest

import pytest
from unstract.connectors.filesystems.ucs import UnstractCloudStorage

# Whole module needs live infra/credentials — integration tier only.
pytestmark = pytest.mark.integration


class TestPCS_FS(unittest.TestCase):
    @unittest.skipUnless(
        os.environ.get("GOOGLE_STORAGE_ACCESS_KEY_ID")
        and os.environ.get("GOOGLE_STORAGE_SECRET_ACCESS_KEY"),
        "Integration test requires GOOGLE_STORAGE_ACCESS_KEY_ID and GOOGLE_STORAGE_SECRET_ACCESS_KEY",
    )
    def test_pcs(self) -> None:
        self.assertEqual(UnstractCloudStorage.requires_oauth(), False)
        access_key = os.environ.get("GOOGLE_STORAGE_ACCESS_KEY_ID")
        secret_key = os.environ.get("GOOGLE_STORAGE_SECRET_ACCESS_KEY")
        gcs = UnstractCloudStorage(
            {
                "key": access_key,
                "secret": secret_key,
                "path": "/",
                "endpoint_url": "https://storage.googleapis.com",
            }
        )

        self.assertIsNotNone(gcs.get_fsspec_fs().ls("unstract-user-storage"))  # type:ignore


if __name__ == "__main__":
    unittest.main()
