import base64
import json
import logging
import os
import threading
from typing import Any


class GCSHelperEnvNotSetException(Exception):
    def __init__(self, message: str):
        self.message = message


logger = logging.getLogger(__name__)

# Global lock for thread-safe Google API initialization
# Prevents deadlock when multiple threads simultaneously create gRPC clients
# (Secret Manager, GCS clients use gRPC which has internal locks)
_GOOGLE_API_INIT_LOCK = threading.Lock()


class GCSHelper:
    """Fork-safe and thread-safe helper for Google Cloud Storage and Secret Manager.

    IMPORTANT: This class ensures safety across ALL Celery pool types:
    - Thread pool: Global lock prevents gRPC deadlock
    - Prefork pool: Lazy initialization prevents SIGSEGV
    - Gevent pool: threading.Lock is gevent-compatible

    Credentials and clients are NOT created in __init__ to avoid creating
    gRPC connections before fork, which would cause SIGSEGV in child processes.
    """

    def __init__(self) -> None:
        # Only store JSON strings and config, NOT credential objects
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

        # Lazy initialization - credentials created only when needed (after fork)
        self._google_credentials: Any | None = None
        self._credentials_lock = threading.Lock()

    def _get_credentials(self) -> Any:
        """Lazily create credentials object (fork-safe).

        This method is called after fork, ensuring gRPC state is created
        in the child process, not inherited from parent.
        """
        if self._google_credentials is None:
            with self._credentials_lock:
                if self._google_credentials is None:
                    # Import inside method to avoid module-level initialization
                    from google.oauth2 import service_account

                    logger.debug("Creating Google credentials (lazy init after fork)")
                    self._google_credentials = (
                        service_account.Credentials.from_service_account_info(
                            json.loads(self.google_service_json)
                        )
                    )
        return self._google_credentials

    def get_google_credentials(self) -> Any:
        """Get Google credentials, creating them lazily if needed."""
        return self._get_credentials()

    def get_secret(self, secret_name: str) -> str:
        """Get secret from Google Secret Manager (lazy init after fork).

        Thread-safe: Uses global lock to prevent gRPC deadlock when multiple
        threads create Secret Manager clients simultaneously.
        """
        # Use global lock to serialize Secret Manager client creation ONLY
        # This prevents deadlock when multiple threads hit this simultaneously
        with _GOOGLE_API_INIT_LOCK:
            from google.cloud import secretmanager

            credentials = self._get_credentials()
            google_secrets_client = secretmanager.SecretManagerServiceClient(
                credentials=credentials
            )

        # Network I/O happens OUTSIDE the lock for better concurrency
        s = google_secrets_client.access_secret_version(
            request={
                "name": f"projects/{self.google_project_id}/secrets/{secret_name}/versions/latest"
            },
            timeout=30.0,  # Add reasonable timeout to prevent indefinite hangs
        )
        return s.payload.data.decode("UTF-8")

    def _get_storage_client(self) -> Any:
        """Lazily create GCS client (fork-safe and thread-safe)."""
        # Use global lock to serialize GCS client creation
        with _GOOGLE_API_INIT_LOCK:
            from google.cloud.storage import Client

            credentials = self._get_credentials()
            return Client(credentials=credentials)

    def get_object_checksum(self, bucket_name: str, object_name: str) -> str:
        """Get MD5 checksum of GCS object."""
        client = self._get_storage_client()
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
        """Upload file to GCS."""
        client = self._get_storage_client()
        bucket = client.bucket(bucket_name)
        blob = bucket.blob(object_name)
        blob.upload_from_filename(file_path)

    def upload_text(self, bucket_name: str, object_name: str, text: str) -> None:
        """Upload text to GCS."""
        client = self._get_storage_client()
        bucket = client.bucket(bucket_name)
        blob = bucket.blob(object_name)
        blob.upload_from_string(text)

    def upload_object(self, bucket_name: str, object_name: str, object: Any) -> None:
        """Upload object to GCS."""
        client = self._get_storage_client()
        bucket = client.bucket(bucket_name)
        blob = bucket.blob(object_name)
        blob.upload_from_string(object, content_type="application/octet-stream")

    def read_file(self, bucket_name: str, object_name: str) -> Any:
        """Read file from GCS."""
        logger.info(f"Reading file {object_name} from bucket {bucket_name}")
        client = self._get_storage_client()
        bucket = client.bucket(bucket_name)
        try:
            blob = bucket.get_blob(object_name)
            obj = blob.download_as_bytes()
            logger.info(f"Successfully read file {object_name} from bucket {bucket_name}")
            return obj
        except Exception:
            logger.error(f"Could not get blob {object_name} from bucket {bucket_name}")
