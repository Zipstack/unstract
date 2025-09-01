import logging
import os
from typing import Any

import azure.core.exceptions as AzureException
from adlfs import AzureBlobFileSystem

from unstract.connectors.exceptions import AzureHttpError
from unstract.connectors.filesystems.azure_cloud_storage.exceptions import (
    parse_azure_error,
)
from unstract.connectors.filesystems.unstract_file_system import UnstractFileSystem
from unstract.filesystem import FileStorageType, FileSystem

# Suppress verbose Azure SDK HTTP request/response logging
logging.getLogger("azurefs").setLevel(logging.ERROR)
logging.getLogger("azure.core.pipeline.policies.http_logging_policy").setLevel(
    logging.WARNING
)
logging.getLogger("azure.storage.blob").setLevel(logging.WARNING)
logging.getLogger("azure.storage").setLevel(logging.WARNING)
logging.getLogger("azure.core").setLevel(logging.WARNING)
# Keep ADLFS filesystem errors visible but suppress HTTP noise
logging.getLogger("adlfs").setLevel(logging.WARNING)

logger = logging.getLogger(__name__)


class AzureCloudStorageFS(UnstractFileSystem):
    class AzureFsError:
        INVALID_PATH = "The specifed resource name contains invalid characters."

    def __init__(self, settings: dict[str, Any]):
        super().__init__("AzureCloudStorageFS")
        account_name = settings.get("account_name", "")
        access_key = settings.get("access_key", "")
        self.bucket = settings.get("bucket", "")
        self.azure_fs = AzureBlobFileSystem(
            account_name=account_name, credential=access_key
        )

    @staticmethod
    def get_id() -> str:
        return "azure_cloud_storage|1476a54a-ed17-4a01-9f8f-cb7e4cf91c8a"

    @staticmethod
    def get_name() -> str:
        return "Azure Cloud Storage"

    @staticmethod
    def get_description() -> str:
        return "Access files in your Azure Cloud Storage"

    @staticmethod
    def get_icon() -> str:
        return "/icons/connector-icons/azure_blob_storage.png"

    @staticmethod
    def get_json_schema() -> str:
        f = open(f"{os.path.dirname(__file__)}/static/json_schema.json")
        schema = f.read()
        f.close()
        return schema

    @staticmethod
    def requires_oauth() -> bool:
        return False

    @staticmethod
    def python_social_auth_backend() -> str:
        return ""

    @staticmethod
    def can_write() -> bool:
        return True

    @staticmethod
    def can_read() -> bool:
        return True

    def get_fsspec_fs(self) -> AzureBlobFileSystem:
        return self.azure_fs

    def extract_metadata_file_hash(self, metadata: dict[str, Any]) -> str | None:
        """Extracts a unique file hash from metadata.

        Args:
            metadata (dict): Metadata dictionary obtained from fsspec.

        Returns:
            Optional[str]: The file hash in hexadecimal format or None if not found.
        """
        # Extracts content_md5 (Bytearray) for Azure Blob Storage
        content_md5 = metadata.get("content_settings", {}).get("content_md5")
        if content_md5:
            return content_md5.hex()
        logger.error(
            f"[Azure Blob Storage] File hash not found for the metadata: {metadata}"
        )
        return None

    def is_dir_by_metadata(self, metadata: dict[str, Any]) -> bool:
        """Check if the given path is a directory.

        Args:
            metadata (dict): Metadata dictionary obtained from fsspec or cloud API.

        Returns:
            bool: True if the path is a directory, False otherwise.
        """
        inner_metadata = metadata.get("metadata")
        if not isinstance(inner_metadata, dict):
            inner_metadata = {}

        is_dir = inner_metadata.get("is_directory") == "true"
        if not is_dir:
            is_dir = metadata.get("type") == "directory"
        return is_dir

    def test_credentials(self) -> bool:
        """To test credentials for Azure Cloud Storage."""
        try:
            self.get_fsspec_fs().info(self.bucket)
        except Exception as e:
            logger.error(
                f"Error from Azure Cloud Storage while testing connection: {str(e)}"
            )
            err = parse_azure_error(e)
            raise err from e
        return True

    def upload_file_to_storage(self, source_path: str, destination_path: str) -> None:
        """Method to upload filepath from tool to destination connector
        directory.

        Args:
            source_path (str): source file path from tool
            destination_path (str): destination azure directory file path

        Raises:
            AzureHttpError: returns error for invalid directory
        """
        normalized_path = os.path.normpath(destination_path)
        destination_connector_fs = self.get_fsspec_fs()
        try:
            file_system = FileSystem(FileStorageType.WORKFLOW_EXECUTION)
            workflow_fs = file_system.get_file_storage()
            data = workflow_fs.read(path=source_path, mode="rb")
            destination_connector_fs.write_bytes(normalized_path, data)
        except AzureException.HttpResponseError as e:
            self.raise_http_exception(e=e, path=normalized_path)

    def debug_directory_access(
        self, directory_path: str, execution_id: str = ""
    ) -> dict[str, Any]:
        """Azure-specific directory access debugging.

        Args:
            directory_path: The directory path being accessed
            execution_id: Execution ID for log correlation

        Returns:
            dict[str, Any]: Azure-specific debug information
        """
        debug_info = {
            "connector_type": "azure_cloud_storage",
            "directory_path": directory_path,
            "execution_id": execution_id,
            "debug_results": {},
        }

        try:
            # Extract container name (Azure equivalent of bucket)
            container_name = (
                directory_path.split("/")[0] if "/" in directory_path else directory_path
            )

            logger.info(
                f"[exec:{execution_id}] [Azure Debug] Checking container: '{container_name}'"
            )
            debug_info["container_name"] = container_name

            azure_fs = self.get_fsspec_fs()

            # Check if container exists and is accessible
            try:
                container_info = azure_fs.info(container_name)
                logger.info(
                    f"[exec:{execution_id}] [Azure Debug] Container '{container_name}' exists with info: {container_info}"
                )
                debug_info["debug_results"]["container_exists"] = True
                debug_info["debug_results"]["container_info"] = str(container_info)
            except Exception as container_error:
                logger.warning(
                    f"[exec:{execution_id}] [Azure Debug] Cannot access container '{container_name}': {container_error}"
                )
                debug_info["debug_results"]["container_exists"] = False
                debug_info["debug_results"]["container_error"] = str(container_error)

            # Try to list contents of the directory
            try:
                dir_contents = azure_fs.ls(directory_path, detail=False)
                logger.info(
                    f"[exec:{execution_id}] [Azure Debug] Directory '{directory_path}' contents: {dir_contents[:10]}..."
                )
                debug_info["debug_results"]["directory_accessible"] = True
                debug_info["debug_results"]["contents_count"] = len(dir_contents)
                debug_info["debug_results"]["sample_contents"] = dir_contents[
                    :5
                ]  # First 5 items
            except Exception as ls_error:
                logger.warning(
                    f"[exec:{execution_id}] [Azure Debug] Cannot list directory '{directory_path}': {ls_error}"
                )
                debug_info["debug_results"]["directory_accessible"] = False
                debug_info["debug_results"]["directory_error"] = str(ls_error)

            # Check container root access (diagnostic)
            try:
                root_contents = azure_fs.ls(container_name, detail=False)
                logger.info(
                    f"[exec:{execution_id}] [Azure Debug] Container root has {len(root_contents)} items"
                )
                debug_info["debug_results"]["container_root_accessible"] = True
                debug_info["debug_results"]["container_root_items"] = len(root_contents)
            except Exception as root_error:
                logger.warning(
                    f"[exec:{execution_id}] [Azure Debug] Cannot access container root: {root_error}"
                )
                debug_info["debug_results"]["container_root_accessible"] = False
                debug_info["debug_results"]["container_root_error"] = str(root_error)

            # Azure-specific checks
            debug_info["debug_results"]["account_name"] = getattr(
                azure_fs, "account_name", "unknown"
            )
            debug_info["debug_results"]["bucket_configured"] = bool(self.bucket)
            debug_info["debug_results"]["bucket_value"] = self.bucket

        except Exception as debug_error:
            logger.warning(
                f"[exec:{execution_id}] [Azure Debug] Debug check failed: {debug_error}"
            )
            debug_info["debug_results"]["debug_failed"] = True
            debug_info["debug_results"]["debug_error"] = str(debug_error)

        return debug_info

    def raise_http_exception(
        self, e: AzureException.HttpResponseError, path: str
    ) -> AzureHttpError:
        user_message = f"Error from Azure Cloud Storage connector. {e.reason} "
        if hasattr(e, "reason"):
            error_reason = e.reason
            if error_reason == self.AzureFsError.INVALID_PATH:
                user_message = (
                    f"Error from Azure Cloud Storage connector. "
                    f"Invalid resource name for path '{path}'. {e.reason}"
                )
        raise AzureHttpError(
            user_message,
            treat_as_user_message=True,
        ) from e
