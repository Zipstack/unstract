import os
import unittest

from unstract.connectors.filesystems.box import BoxFS


class TestBoxFS(unittest.TestCase):
    def test_basic(self):
        box_app_settings = os.environ.get("TEST_BOX_APP_SETTINGS")
        box_fs = BoxFS(settings={"box_app_settings": box_app_settings})
        file_path = "/"
        try:
            files = box_fs.get_fsspec_fs().ls(file_path)
            print(files)
            self.assertIsNotNone(files)
        except Exception as e:
            self.fail(f"TestBoxFS.test_basic failed: {e}")


if __name__ == "__main__":
    unittest.main()
