import unittest

from unstract.connectors.filesystems.http.http import HttpFS


class TestHttpFS(unittest.TestCase):
    # Run a local HTTP server with
    # `python -m http.server -b localhost 8080`
    def test_basic(self):
        self.assertEqual(HttpFS.can_write(), False)
        # Assuming that the server is run locally
        # url = "http://localhost:8080/"
        url = "https://filesystem-spec.readthedocs.io/"
        http_fs = HttpFS(settings={"base_url": url})
        file_path = "/"
        try:
            # print(http_fs.get_fsspec_fs().ls(file_path))
            files = http_fs.get_fsspec_fs().ls(file_path)
            self.assertIsNotNone(files)
        except Exception as e:
            self.fail(f"TestHttpFS.test_basic failed: {e}")


if __name__ == "__main__":
    unittest.main()
