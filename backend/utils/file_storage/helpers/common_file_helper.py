import json
from typing import Any, Union

from unstract.sdk.file_storage import (
    FileStorageProvider,
    PermanentFileStorage,
    SharedTemporaryFileStorage,
)
from utils.file_storage.constants import FileStorageKeys, FileStorageType

from unstract.core.utilities import UnstractUtils


class FileStorageHelper:
    # TODO : Optimize this to a singleton class
    @staticmethod
    def initialize_file_storage(
        type: FileStorageType,
    ) -> Union[PermanentFileStorage, SharedTemporaryFileStorage]:
        provider_data = FileStorageHelper.load_file_storage_envs()
        provider = provider_data[FileStorageKeys.FILE_STORAGE_PROVIDER]
        provider_value = FileStorageProvider(provider)
        credentials = provider_data[FileStorageKeys.FILE_STORAGE_CREDENTIALS]
        if type.value == FileStorageType.PERMANENT.value:
            file_storage = PermanentFileStorage(provider=provider_value, **credentials)
        elif type.value == FileStorageType.TEMPORARY.value:
            file_storage = SharedTemporaryFileStorage(
                provider=provider_value, **credentials
            )
        else:
            file_storage = PermanentFileStorage(
                provider=FileStorageProvider.LOCAL, **credentials
            )
        return file_storage

    @staticmethod
    def load_file_storage_envs() -> dict[str, Any]:
        cred_env_data: str = UnstractUtils.get_env(
            env_key=FileStorageKeys.FILE_STORAGE_CREDENTIALS
        )
        credentials = json.loads(cred_env_data)
        provider_data: dict[str, Any] = {}
        provider_data[FileStorageKeys.FILE_STORAGE_PROVIDER] = credentials["provider"]
        provider_data[FileStorageKeys.FILE_STORAGE_CREDENTIALS] = credentials[
            "credentials"
        ]
        return provider_data
