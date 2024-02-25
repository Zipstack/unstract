import os
import unittest

from unstract.connectors.filesystems.zs_dropbox import DropboxFS


class TestDropboxFS(unittest.TestCase):
    def test_access_token(self):
        access_token = os.environ.get("TEST_DROPBOX_ACCESS_TOKEN")
        settings = {"token": access_token}
        dropbox_fs = DropboxFS(settings=settings)
        # Leave empty for root
        file_path = ""
        try:
            # print(dropbox_fs.get_fsspec_fs().ls(file_path))
            files = dropbox_fs.get_fsspec_fs().ls(file_path)
            print(files)
            self.assertIsNotNone(files)
        except Exception as e:
            self.fail(f"TestDropboxFS.test_access_token failed: {e}")


if __name__ == "__main__":
    unittest.main()
