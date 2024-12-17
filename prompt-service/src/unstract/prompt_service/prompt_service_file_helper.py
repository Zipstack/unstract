from typing import Union

from unstract.prompt_service.constants import FileStorageKeys, FileStorageType
from unstract.prompt_service.env_manager import EnvLoader
from unstract.sdk.file_storage import (
    FileStorageProvider,
    PermanentFileStorage,
    SharedTemporaryFileStorage,
)


class PromptServiceFileHelper:
    @staticmethod
    def initialize_file_storage(
        type: FileStorageType,
    ) -> Union[PermanentFileStorage, SharedTemporaryFileStorage]:
        provider_data = EnvLoader.load_provider_credentials()
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
