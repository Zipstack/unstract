import logging
from typing import Any

import fsspec
from fsspec import AbstractFileSystem
from unstract.sdk.exceptions import FileOperationError, FileStorageError
from unstract.sdk.file_storage.provider import FileStorageProvider

logger = logging.getLogger(__name__)


class FileStorageHelper:
    @staticmethod
    def file_storage_init(
        provider: FileStorageProvider, **storage_config: dict[str, Any]
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
                storage_config.update({"auto_mkdir": True})  # type: ignore
            elif provider in [FileStorageProvider.MINIO]:
                # Initialise using s3 for Minio
                protocol = FileStorageProvider.S3.value

            fs = fsspec.filesystem(
                protocol=protocol,
                **storage_config,
            )
            logger.debug(f"Connected to {provider.value} file system")
        except KeyError as e:
            logger.error(
                f"Error in initialising {provider.value} "
                f"file system because of missing config {e}"
            )
            raise FileStorageError(str(e)) from e
        except Exception as e:
            logger.error(f"Error in initialising {provider.value} " f"file system {e}")
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
            logger.debug(f"Connected to {FileStorageProvider.LOCAL.value} file system")
            return fs
        except Exception as e:
            logger.error(
                f"Error in initialising {FileStorageProvider.GCS.value}"
                f" file system {e}"
            )
            raise FileStorageError(str(e)) from e


def skip_local_cache(func):
    """Helper function/decorator for handling FileNotFound exception and making
    sure that the error is not because of stale cache.

    Args:
        func: The original function that is called in the context

    Returns:
        NA
    """

    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except FileNotFoundError:
            _handle_file_not_found(func, *args, **kwargs)
        except Exception as e:
            raise FileOperationError(str(e)) from e

    return wrapper


def _handle_file_not_found(func, *args, **kwargs):
    """Helper function for handling FileNotFound exception and making sure that
    the error is not because of stale cache.

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
