import json
import logging
import os

from unstract.sdk.exceptions import FileStorageError
from unstract.sdk.file_storage.constants import CredentialKeyword, StorageType
from unstract.sdk.file_storage.impl import FileStorage
from unstract.sdk.file_storage.permanent import PermanentFileStorage
from unstract.sdk.file_storage.provider import FileStorageProvider
from unstract.sdk.file_storage.shared_temporary import SharedTemporaryFileStorage

logger = logging.getLogger(__name__)


class EnvHelper:
    ENV_CONFIG_FORMAT = (
        '{"provider": "gcs", ' '"credentials": {"token": "/path/to/google/creds.json"}}'
    )

    @staticmethod
    def get_storage(storage_type: StorageType, env_name: str) -> FileStorage:
        """Helper function for clients to pick up remote storage configuration
        from env, initialise the file storage for the same and return the
        instance.

        Args:
            storage_type: Permanent / Temporary file storage
            env_name: Name of the env which has the file storage config

        Returns:
            FileStorage: FIleStorage instance initialised using the provider
            and credentials configured in the env
        """
        try:
            file_storage_creds = json.loads(os.environ.get(env_name, ""))
            provider = FileStorageProvider(
                file_storage_creds[CredentialKeyword.PROVIDER]
            )
            credentials = file_storage_creds.get(CredentialKeyword.CREDENTIALS, {})
            if storage_type == StorageType.PERMANENT:
                file_storage = PermanentFileStorage(provider=provider, **credentials)
            elif storage_type == StorageType.SHARED_TEMPORARY:
                file_storage = SharedTemporaryFileStorage(
                    provider=provider, **credentials
                )
            else:
                raise NotImplementedError()
            return file_storage
        except KeyError as e:
            logger.error(f"Required credentials are missing in the env: {str(e)}")
            logger.error(f"The configuration format is {EnvHelper.ENV_CONFIG_FORMAT}")
            raise e
        except FileStorageError as e:
            raise e
