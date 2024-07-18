import logging
import os

import boto3
from botocore.exceptions import ClientError
from django.conf import settings

logger = logging.getLogger(__name__)


# TODO: UnstractAccount need to be pluggable
class UnstractAccount:
    def __init__(self, tenant: str, username: str) -> None:
        self.tenant = tenant
        self.username = username

    def provision_s3_storage(self) -> None:
        access_key = settings.GOOGLE_STORAGE_ACCESS_KEY_ID
        secret_key = settings.GOOGLE_STORAGE_SECRET_ACCESS_KEY
        bucket_name: str = settings.UNSTRACT_FREE_STORAGE_BUCKET_NAME

        s3 = boto3.client(
            "s3",
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key,
            endpoint_url="https://storage.googleapis.com",
        )

        # Check if folder exists and create if it is not available
        account_folder = f"{self.tenant}/{self.username}/input/examples/"
        try:
            logger.info(f"Checking if folder {account_folder} exists...")
            s3.head_object(Bucket=bucket_name, Key=account_folder)
            logger.info(f"Folder {account_folder} already exists")
        except ClientError as e:
            logger.info(f"{bucket_name} Folder {account_folder} does not exist")
            if e.response["Error"]["Code"] == "404":
                logger.info(f"Folder {account_folder} does not exist. Creating it...")
                s3.put_object(Bucket=bucket_name, Key=account_folder)
                account_folder_output = f"{self.tenant}/{self.username}/output/"
                s3.put_object(Bucket=bucket_name, Key=account_folder_output)
            else:
                logger.error(f"Error checking folder {account_folder}: {e}")
                raise e

    def upload_sample_files(self) -> None:
        access_key = settings.GOOGLE_STORAGE_ACCESS_KEY_ID
        secret_key = settings.GOOGLE_STORAGE_SECRET_ACCESS_KEY
        bucket_name: str = settings.UNSTRACT_FREE_STORAGE_BUCKET_NAME

        s3 = boto3.client(
            "s3",
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key,
            endpoint_url="https://storage.googleapis.com",
        )

        folder = f"{self.tenant}/{self.username}/input/examples/"

        local_path = f"{os.path.dirname(__file__)}/static"
        for root, dirs, files in os.walk(local_path):
            for file in files:
                local_file_path = os.path.join(root, file)
                s3_key = os.path.join(
                    folder, os.path.relpath(local_file_path, local_path)
                )
                logger.info(
                    f"Uploading: {local_file_path} => s3://{bucket_name}/{s3_key}"
                )
                s3.upload_file(local_file_path, bucket_name, s3_key)
                logger.info(f"Uploaded: {local_file_path}")
