from typing import Any

from unstract.sdk.file_storage.fs_impl import FileStorage
from unstract.sdk.file_storage.fs_permanent import PermanentFileStorage
from utils.common_utils import CommonUtils
from utils.constants import FileStorageKeys, FileStorageType


class FileStorageUtil:
    @staticmethod
    def initialize_file_storage(type: FileStorageType) -> FileStorage:
        provider_data = FileStorageUtil.load_file_storage_envs()
        provider = provider_data[FileStorageKeys.FILE_STORAGE_PROVIDER]
        credentials = provider_data[FileStorageKeys.FILE_STORAGE_CREDENTIALS]
        if type.value == FileStorageType.PERMANENT.value:
            file_storage = PermanentFileStorage(
                provider=provider, credentials=credentials
            )
        if type.value == FileStorageType.DEFAULT.value:
            file_storage = FileStorage(provider=provider, credentials=credentials)
        return file_storage

    @staticmethod
    def load_file_storage_envs() -> dict[str, Any]:
        provider: str = CommonUtils.get_env_or_die(
            env_key=FileStorageKeys.FILE_STORAGE_PROVIDER
        )
        credentials: str = CommonUtils.get_env_or_die(
            env_key=FileStorageKeys.FILE_STORAGE_CREDENTIALS
        )
        provider_data: dict[str, Any] = {}
        provider_data[FileStorageKeys.FILE_STORAGE_PROVIDER] = provider
        provider_data[FileStorageKeys.FILE_STORAGE_CREDENTIALS] = credentials
        return provider_data
