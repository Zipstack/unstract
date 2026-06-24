import json
import logging
import os

from unstract.sdk1.exceptions import FileStorageError
from unstract.sdk1.file_storage.constants import CredentialKeyword, StorageType
from unstract.sdk1.file_storage.impl import FileStorage
from unstract.sdk1.file_storage.permanent import PermanentFileStorage
from unstract.sdk1.file_storage.provider import FileStorageProvider
from unstract.sdk1.file_storage.shared_temporary import SharedTemporaryFileStorage

logger = logging.getLogger(__name__)


class EnvHelper:
    ENV_CONFIG_FORMAT = (
        '{"provider": "gcs", "credentials": {"token": "/path/to/google/creds.json"}}'
    )

    @staticmethod
    def get_storage(storage_type: StorageType, env_name: str) -> FileStorage:
        """Helper function for clients to pick up remote storage configuration from env.

        Initialise the file storage for the same and return the instance.

        Args:
            storage_type: Permanent / Temporary file storage
            env_name: Name of the env which has the file storage config

        Returns:
            FileStorage: FIleStorage instance initialised using the provider
            and credentials configured in the env
        """
        raw = os.environ.get(env_name)
        if not raw:
            raise FileStorageError(
                f"Required env var '{env_name}' is unset or empty. "
                f"Expected JSON config of the form: {EnvHelper.ENV_CONFIG_FORMAT}"
            )
        try:
            file_storage_creds = json.loads(raw)
        except json.JSONDecodeError as e:
            raise FileStorageError(
                f"Env var '{env_name}' is not valid JSON: {e}. "
                f"Expected: {EnvHelper.ENV_CONFIG_FORMAT}"
            ) from e
        if not isinstance(file_storage_creds, dict):
            raise FileStorageError(
                f"Env var '{env_name}' must be a JSON object. "
                f"Expected: {EnvHelper.ENV_CONFIG_FORMAT}"
            )
        try:
            provider = FileStorageProvider(file_storage_creds[CredentialKeyword.PROVIDER])
        except (KeyError, ValueError) as e:
            logger.error(f"Invalid storage configuration in env: {str(e)}")
            logger.error(f"The configuration format is {EnvHelper.ENV_CONFIG_FORMAT}")
            raise FileStorageError(
                f"Invalid storage configuration in env var '{env_name}': {e}. "
                f"Expected: {EnvHelper.ENV_CONFIG_FORMAT}"
            ) from e
        credentials = file_storage_creds.get(CredentialKeyword.CREDENTIALS, {})
        if storage_type == StorageType.PERMANENT:
            return PermanentFileStorage(provider=provider, **credentials)
        elif storage_type == StorageType.SHARED_TEMPORARY:
            return SharedTemporaryFileStorage(provider=provider, **credentials)
        else:
            raise NotImplementedError()
