import json
from typing import Any

from unstract.sdk.file_storage import FileStorageProvider
from unstract.sdk.file_storage.fs_impl import FileStorage
from unstract.sdk.file_storage.fs_permanent import PermanentFileStorage
from unstract.sdk.file_storage.fs_shared_temporary import SharedTemporaryFileStorage
from utils.file_storage.common_utils import FileStorageUtil
from utils.file_storage.constants import FileStorageKeys, FileStorageType


class FileStorageHelper:
    # TODO : Optimize this to a singleton class
    @staticmethod
    def initialize_file_storage(type: FileStorageType) -> FileStorage:
        provider_data = FileStorageHelper.load_file_storage_envs()
        provider = provider_data[FileStorageKeys.FILE_STORAGE_PROVIDER]
        credentials = provider_data[FileStorageKeys.FILE_STORAGE_CREDENTIALS]
        if type.value == FileStorageType.PERMANENT.value:
            file_storage = PermanentFileStorage(provider, **credentials)
        elif type.value == FileStorageType.TEMPORARY.value:
            file_storage = SharedTemporaryFileStorage(provider, **credentials)
        else:
            file_storage = FileStorage(FileStorageProvider.LOCAL, **credentials)
        return file_storage

    @staticmethod
    def load_file_storage_envs() -> dict[str, Any]:
        file_storage = json.loads(
            FileStorageUtil.get_env_or_die(env_key="FILE_STORAGE_CREDENTIALS")
        )
        provider = FileStorageProvider(file_storage["provider"])
        credentials = file_storage["credentials"]

        provider_data: dict[str, Any] = {}
        provider_data[FileStorageKeys.FILE_STORAGE_PROVIDER] = provider
        provider_data[FileStorageKeys.FILE_STORAGE_CREDENTIALS] = credentials
        return provider_data
