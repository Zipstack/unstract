import unittest

from unstract.connectors.filesystems.google_drive.google_drive import GoogleDriveFS


class TestGoogleDriveFS(unittest.TestCase):
    def test_basic(self):
        self.assertEqual(GoogleDriveFS.requires_oauth(), True)
        drive = GoogleDriveFS(
            {
                "access_token": "",
                "refresh_token": "",
                "token_expiry": "2023-06-23T08:10:49Z",
            }
        )

        print(drive.get_fsspec_fs().ls(""))


if __name__ == "__main__":
    unittest.main()
