from typing import Any
from unstract.core.file_storage.fs_permanent import PermanentFileStorage
from unstract.core.file_storage.fs_shared_temporary import SharedTemporaryFileStorage
from unstract.sdk.file_storage.fs_impl import FileStorage
from unstract.core.file_storage.constants import FileStorageKeys,FileStorageType
from unstract.core.file_storage.common_utils import FileStorageUtil
from unstract.sdk.file_storage import FileStorage, FileStorageProvider

class FileStorageHelper:
    #TODO : Optimize this to a singleton class
    @staticmethod
    def initialize_file_storage(type: FileStorageType) -> FileStorage:
        provider_data = FileStorageHelper.load_file_storage_envs()
        provider = provider_data[FileStorageKeys.FILE_STORAGE_PROVIDER]
        credentials = provider_data[FileStorageKeys.FILE_STORAGE_CREDENTIALS]
        if type.value == FileStorageType.PERMANENT.value:
            file_storage = PermanentFileStorage(
                provider=provider, credentials=credentials
            )
        if type.value == FileStorageType.TEMPORARY.value:
            file_storage = SharedTemporaryFileStorage(
                provider=provider, credentials=credentials
            )
        file_storage = FileStorage(provider=FileStorageProvider.Local, credentials=credentials)
        return file_storage

    @staticmethod
    def load_file_storage_envs() -> dict[str, Any]:
        provider: str = FileStorageUtil.get_env_or_die(
            env_key=FileStorageKeys.FILE_STORAGE_PROVIDER
        )
        credentials: str = FileStorageUtil.get_env_or_die(
            env_key=FileStorageKeys.FILE_STORAGE_CREDENTIALS
        )
        provider_data: dict[str, Any] = {}
        provider_data[FileStorageKeys.FILE_STORAGE_PROVIDER] = provider
        provider_data[FileStorageKeys.FILE_STORAGE_CREDENTIALS] = credentials
        return provider_data
    