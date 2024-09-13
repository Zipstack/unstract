import os
import unittest

from unstract.connectors.filesystems.ucs import UnstractCloudStorage


class TestPCS_FS(unittest.TestCase):
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

        print(gcs.get_fsspec_fs().ls("unstract-user-storage"))  # type:ignore


if __name__ == "__main__":
    unittest.main()
