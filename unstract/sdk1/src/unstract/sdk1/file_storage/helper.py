import logging

import fsspec
from fsspec import AbstractFileSystem
from unstract.sdk1.exceptions import FileOperationError, FileStorageError
from unstract.sdk1.file_storage.provider import FileStorageProvider

logger = logging.getLogger(__name__)


class FileStorageHelper:
    @staticmethod
    def file_storage_init(
        provider: FileStorageProvider, **storage_config: object
    ) -> AbstractFileSystem:
        """Initialises file storage based on provider.

        Args:
            provider (FileStorageProvider): Provider
            storage_config : Storage config params based on the provider.
            Sent as-is to the provider implementation.

        Returns:
            NA
        """
        try:
            protocol = provider.value
            if provider == FileStorageProvider.LOCAL:
                # Hard set auto_mkdir to True as default
                storage_config.update({"auto_mkdir": True})
            elif provider in [FileStorageProvider.MINIO]:
                # Initialise using s3 for Minio
                protocol = FileStorageProvider.S3.value

            if provider in (FileStorageProvider.S3, FileStorageProvider.MINIO):
                # Strip empty string values so boto3's credential chain
                # can work (e.g., IRSA on EKS)
                storage_config = {
                    k: v
                    for k, v in storage_config.items()
                    if not (isinstance(v, str) and v.strip() == "")
                }

            fs = fsspec.filesystem(
                protocol=protocol,
                **storage_config,
            )
            logger.debug("Connected to %s file system", provider.value)
        except KeyError as e:
            logger.error(
                "Error in initialising %s file system because of missing config %s",
                provider.value,
                e,
            )
            raise FileStorageError(str(e)) from e
        except Exception as e:
            logger.error("Error in initialising %s file system %s", provider.value, e)
            raise FileStorageError(str(e)) from e
        return fs

    @staticmethod
    def local_file_system_init() -> AbstractFileSystem:
        """Initialises FileStorage backed up by Local file system.

        Returns:
            NA
        """
        try:
            fs = fsspec.filesystem(protocol=FileStorageProvider.LOCAL.value)
            logger.debug("Connected to %s file system", FileStorageProvider.LOCAL.value)
            return fs
        except Exception as e:
            logger.error(
                "Error in initialising %s file system %s",
                FileStorageProvider.GCS.value,
                e,
            )
            raise FileStorageError(str(e)) from e


def skip_local_cache(func: object) -> object:
    """Helper function/decorator for handling FileNotFound exception.

    Making sure that the error is not because of stale cache.

    Args:
        func: The original function that is called in the context

    Returns:
        NA
    """

    def wrapper(*args: object, **kwargs: object) -> object:
        try:
            return func(*args, **kwargs)
        except FileNotFoundError:
            _handle_file_not_found(func, *args, **kwargs)
        except Exception as e:
            raise FileOperationError(str(e)) from e

    return wrapper


def _handle_file_not_found(func: object, *args: object, **kwargs: object) -> object:
    """Helper function for handling FileNotFound exception.

    Making sure that the error is not because of stale cache.

    Args:
        func: The original function that is called in the context
        args: The context of the function call as an array
        kwargs: args to the function being called in this context

    Returns:
        NA
    """
    try:
        # FileNotFound could have been caused by stale cache.
        # Hence invalidate cache and retry again
        args[0].fs.invalidate_cache()
        return func(*args, **kwargs)
    except Exception as e:
        if isinstance(e, FileNotFoundError):
            raise e
        else:
            raise FileOperationError(str(e)) from e
