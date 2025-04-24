from unstract.prompt_service.constants import ExecutionSource, FileStorageKeys
from unstract.sdk.file_storage import FileStorage
from unstract.sdk.file_storage.constants import StorageType
from unstract.sdk.file_storage.env_helper import EnvHelper


class FileUtils:
    @staticmethod
    def get_fs_instance(execution_source: str) -> FileStorage:
        """Returns a FileStorage instance based on the execution source.

        Args:
            execution_source (str): The source from which the execution is triggered.

        Returns:
            FileStorage: The file storage instance - Permanent/Shared temporary

        Raises:
            ValueError: If the execution source is invalid.
        """
        if execution_source == ExecutionSource.IDE.value:
            return EnvHelper.get_storage(
                storage_type=StorageType.PERMANENT,
                env_name=FileStorageKeys.PERMANENT_REMOTE_STORAGE,
            )

        if execution_source == ExecutionSource.TOOL.value:
            return EnvHelper.get_storage(
                storage_type=StorageType.SHARED_TEMPORARY,
                env_name=FileStorageKeys.TEMPORARY_REMOTE_STORAGE,
            )

        raise ValueError(f"Invalid execution source: {execution_source}")
