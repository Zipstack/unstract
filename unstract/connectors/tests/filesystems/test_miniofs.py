import os
import unittest

from unstract.connectors.filesystems.minio.minio import MinioFS


class TestMinoFS(unittest.TestCase):
    @unittest.skip("")
    def test_s3(self) -> None:
        self.assertEqual(MinioFS.requires_oauth(), False)
        access_key = os.environ.get("AWS_ACCESS_KEY_ID")
        secret_key = os.environ.get("AWS_SECRET_ACCESS_KEY")
        bucket_name = os.environ.get(
            "FREE_STORAGE_AWS_BUCKET_NAME", "pandora-user-storage"
        )
        s3 = MinioFS(
            {
                "key": access_key,
                "secret": secret_key,
                "bucket": bucket_name,
                "path": "/",
                "endpoint_url": "https://s3.amazonaws.com",
            }
        )

        print(s3.get_fsspec_fs().ls("pandora-user-storage"))

    # @unittest.skip("Minio is not running")
    def test_minio(self) -> None:
        self.assertEqual(MinioFS.requires_oauth(), False)
        access_key = os.environ.get("MINIO_ACCESS_KEY_ID")
        secret_key = os.environ.get("MINIO_SECRET_ACCESS_KEY")
        print(access_key, secret_key)
        bucket_name = os.environ.get("FREE_STORAGE_AWS_BUCKET_NAME", "minio-test")
        s3 = MinioFS(
            {
                "key": access_key,
                "secret": secret_key,
                "bucket": bucket_name,
                "endpoint_url": "http://localhost:9000",
                "path": "/minio-test",
            }
        )

        print(s3.get_fsspec_fs().ls("/minio-test"))  # type:ignore


if __name__ == "__main__":
    unittest.main()
