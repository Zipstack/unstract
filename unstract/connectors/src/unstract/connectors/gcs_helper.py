import base64
import json
import logging
import os
from typing import Any

from google.cloud import secretmanager
from google.cloud.storage import Client
from google.oauth2 import service_account
from google.oauth2.credentials import Credentials


class GCSHelperEnvNotSetException(Exception):
    def __init__(self, message: str):
        self.message = message


logger = logging.getLogger(__name__)


class GCSHelper:
    def __init__(self) -> None:
        self.google_service_json = os.environ.get("GDRIVE_GOOGLE_SERVICE_ACCOUNT")
        self.google_project_id = os.environ.get("GDRIVE_GOOGLE_PROJECT_ID")
        if self.google_service_json is None:
            raise GCSHelperEnvNotSetException(
                "GDRIVE_GOOGLE_SERVICE_ACCOUNT environment variable not set"
            )
        if self.google_project_id is None:
            raise GCSHelperEnvNotSetException(
                "GDRIVE_GOOGLE_PROJECT_ID environment variable not set"
            )

        self.google_credentials = service_account.Credentials.from_service_account_info(
            json.loads(self.google_service_json)
        )

    def get_google_credentials(self) -> Credentials:
        return self.google_credentials

    def get_secret(self, secret_name: str) -> str:
        google_secrets_client = secretmanager.SecretManagerServiceClient(
            credentials=self.google_credentials
        )
        s = google_secrets_client.access_secret_version(
            request={
                "name": f"projects/{self.google_project_id}/secrets/{secret_name}/versions/latest"  # noqa: E501
            }
        )
        return s.payload.data.decode("UTF-8")

    def get_object_checksum(self, bucket_name: str, object_name: str) -> str:
        client = Client(credentials=self.google_credentials)
        bucket = client.bucket(bucket_name)
        md5_hash_hex = ""
        try:
            blob = bucket.get_blob(object_name)
            md5_hash_bytes = base64.b64decode(blob.md5_hash)
            md5_hash_hex = md5_hash_bytes.hex()
        except Exception:
            logger.error(f"Could not get blob {object_name} from bucket {bucket_name}")
        return md5_hash_hex

    def upload_file(self, bucket_name: str, object_name: str, file_path: str) -> None:
        client = Client(credentials=self.google_credentials)
        bucket = client.bucket(bucket_name)
        blob = bucket.blob(object_name)
        blob.upload_from_filename(file_path)

    def upload_text(self, bucket_name: str, object_name: str, text: str) -> None:
        client = Client(credentials=self.google_credentials)
        bucket = client.bucket(bucket_name)
        blob = bucket.blob(object_name)
        blob.upload_from_string(text)

    def upload_object(self, bucket_name: str, object_name: str, object: Any) -> None:
        client = Client(credentials=self.google_credentials)
        bucket = client.bucket(bucket_name)
        blob = bucket.blob(object_name)
        blob.upload_from_string(object, content_type="application/octet-stream")

    def read_file(self, bucket_name: str, object_name: str) -> Any:
        logger.info(f"Reading file {object_name} from bucket {bucket_name}")
        client = Client(credentials=self.google_credentials)
        bucket = client.bucket(bucket_name)
        logger.info(f"Reading file {object_name} from bucket {bucket_name}")
        try:
            blob = bucket.get_blob(object_name)
            logger.info(f"Reading file {object_name} from bucket {bucket_name}")
            obj = blob.download_as_bytes()
            logger.info(f"Reading file {object_name} from bucket {bucket_name}")
            return obj
        except Exception:
            logger.error(f"Could not get blob {object_name} from bucket {bucket_name}")
