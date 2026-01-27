"""SharePoint/OneDrive filesystem connector.

Supports:
- SharePoint Online document libraries
- OneDrive for Business (Microsoft 365 work/school accounts)
- OneDrive Personal (consumer Microsoft accounts)

Uses Microsoft Graph API via Office365-REST-Python-Client library.
"""

import logging
import os
import threading
from datetime import UTC, datetime
from typing import Any

from fsspec import AbstractFileSystem
from fsspec.spec import AbstractBufferedFile

from unstract.connectors.exceptions import ConnectorError
from unstract.connectors.filesystems.unstract_file_system import UnstractFileSystem

logger = logging.getLogger(__name__)

# Global lock for thread-safe Microsoft Graph API initialization
# Prevents issues when multiple threads simultaneously create clients
_SHAREPOINT_INIT_LOCK = threading.Lock()


class SharePointFile(AbstractBufferedFile):
    """File-like object for SharePoint files."""

    def __init__(
        self,
        fs: "SharePointFS",
        path: str,
        mode: str = "rb",
        **kwargs: Any,
    ):
        self.fs = fs
        self.path = path
        self._file_content: bytes | None = None
        super().__init__(fs, path, mode, **kwargs)

    def _fetch_range(self, start: int, end: int) -> bytes:
        """Fetch a range of bytes from the file."""
        if self._file_content is None:
            self._file_content = self.fs._download_file(self.path)
        return self._file_content[start:end]

    def _upload_chunk(self, final: bool = False) -> bool:
        """Upload is handled by write_bytes."""
        return True


class SharePointFileSystem(AbstractFileSystem):
    """fsspec-compatible filesystem for SharePoint/OneDrive.

    This provides an fsspec interface on top of the Office365 REST API.
    """

    protocol = "sharepoint"

    def __init__(
        self,
        site_url: str,
        tenant_id: str,
        client_id: str,
        client_secret: str | None = None,
        access_token: str | None = None,
        refresh_token: str | None = None,
        drive_id: str | None = None,
        is_personal: bool = False,
        user_email: str | None = None,
        **kwargs: Any,
    ):
        super().__init__(**kwargs)
        self.site_url = site_url.rstrip("/") if site_url else ""
        self.tenant_id = tenant_id
        self.client_id = client_id
        self.client_secret = client_secret
        self.access_token = access_token
        self.refresh_token = refresh_token
        self.drive_id = drive_id
        self.is_personal = is_personal
        self.user_email = user_email

        # Lazy initialization
        self._ctx = None
        self._drive = None
        self._ctx_lock = threading.Lock()

    def _get_context(self) -> Any:
        """Get SharePoint client context with lazy initialization."""
        if self._ctx is None:
            with self._ctx_lock:
                if self._ctx is None:
                    # Import here for fork safety
                    from office365.graph_client import GraphClient

                    logger.info("Initializing SharePoint/OneDrive client")

                    if self.client_secret:
                        # Client credentials flow (app-only)
                        self._ctx = GraphClient(tenant=self.tenant_id).with_client_secret(
                            self.client_id,
                            self.client_secret,
                        )
                    elif self.access_token:
                        # OAuth token-based flow
                        def token_provider() -> dict[str, str]:
                            return {
                                "access_token": self.access_token,
                                "token_type": "Bearer",
                            }

                        self._ctx = GraphClient(token_provider)
                    else:
                        error_msg = (
                            "Provide either:\n"
                            "- client_secret (for app-only access)\n"
                            "- access_token (for delegated access)."
                        )
                        raise ConnectorError(
                            error_msg,
                            treat_as_user_message=True,
                        )

                    logger.info("SharePoint/OneDrive client initialized")

        return self._ctx

    def _get_drive(self) -> Any:
        """Get the drive object (SharePoint library or OneDrive)."""
        if self._drive is None:
            ctx = self._get_context()

            if self.drive_id:
                # Specific drive by ID
                self._drive = ctx.drives.get_by_id(self.drive_id)
            elif self.site_url and "sharepoint.com" in self.site_url.lower():
                # SharePoint site - get default document library
                self._drive = self._get_sharepoint_site_drive(ctx)
            else:
                # OneDrive - choose method based on auth type
                self._drive = self._get_onedrive_drive(ctx)

        return self._drive

    def _get_sharepoint_site_drive(self, ctx: Any) -> Any:
        """Get drive from SharePoint site URL."""
        from urllib.parse import urlparse

        parsed = urlparse(self.site_url)
        # Extract site path from URL like
        # https://tenant.sharepoint.com/sites/sitename
        site_path = parsed.path.rstrip("/")
        if site_path:
            return ctx.sites.get_by_path(site_path).drive
        return ctx.sites.root.drive

    def _get_onedrive_drive(self, ctx: Any) -> Any:
        """Get OneDrive drive based on authentication method."""
        # OAuth (delegated auth) - can use /me
        if self.access_token:
            return ctx.me.drive

        # Client credentials (app-only) - must use user email
        if self.client_secret:
            if not self.user_email:
                error_msg = (
                    "OneDrive client credentials require user email. Provide either \n"
                    "- user_email (e.g., user@company.onmicrosoft.com) \n"
                    "- OR use OAuth with access_token instead."
                )
                raise ConnectorError(
                    error_msg,
                    treat_as_user_message=True,
                )
            return ctx.users[self.user_email].drive

        error_msg = (
            "SharePoint authentication credentials missing. Provide either:\n"
            "- client_secret (for app-only access)\n"
            "- OR access_token (for delegated access)"
        )
        raise ConnectorError(
            error_msg,
            treat_as_user_message=True,
        )

    def _normalize_path(self, path: str) -> str:
        """Normalize path for SharePoint API."""
        if not path:
            return "root"
        # Remove leading/trailing slashes and normalize
        path = path.strip("/")
        if not path or path == ".":
            return "root"
        return path

    def _get_item_by_path(self, path: str) -> Any:
        """Get drive item by path."""
        path = self._normalize_path(path)
        drive = self._get_drive()

        if path == "root":
            return drive.root
        else:
            return drive.root.get_by_path(path)

    def ls(self, path: str = "", detail: bool = True, **kwargs: Any) -> list[Any]:
        """List directory contents."""
        try:
            item = self._get_item_by_path(path)
            children = (
                item.children.select(
                    [
                        "id",
                        "name",
                        "file",
                        "folder",
                        "size",
                        "lastModifiedDateTime",
                        "createdDateTime",
                    ]
                )
                .get()
                .execute_query()
            )

            results = []
            for child in children:
                info = self._item_to_info(child, path)
                if detail:
                    results.append(info)
                else:
                    results.append(info["name"])

            return results
        except Exception as e:
            logger.error(f"Error listing path {path}: {e}")
            raise

    def listdir(self, path: str = "", detail: bool = True, **kwargs: Any) -> list[Any]:
        """List directory contents (alias for ls)."""
        return self.ls(path, detail=detail, **kwargs)

    def _item_to_info(self, item: Any, parent_path: str = "") -> dict[str, Any]:
        """Convert SharePoint item to fsspec info dict."""
        name = item.name
        if parent_path and parent_path != "root":
            full_path = f"{parent_path.strip('/')}/{name}"
        else:
            full_path = name

        # Use the Office365 library's built-in is_folder property which properly
        # checks if the folder facet was populated in the API response
        is_folder = item.is_folder

        # Access size from properties dict - Office365 library stores API response data there
        size = item.properties.get("size", 0) or 0

        info = {
            "name": full_path,
            "size": size,
            "type": "directory" if is_folder else "file",
            "id": item.id,
        }

        # Add metadata fields
        if hasattr(item, "last_modified_date_time"):
            info["lastModifiedDateTime"] = item.last_modified_date_time
        if hasattr(item, "created_date_time"):
            info["createdDateTime"] = item.created_date_time
        if hasattr(item, "e_tag"):
            info["eTag"] = item.e_tag
        if hasattr(item, "c_tag"):
            info["cTag"] = item.c_tag

        # File-specific metadata
        if not is_folder and hasattr(item, "file"):
            file_info = item.file
            if hasattr(file_info, "hashes") and file_info.hashes:
                hashes = file_info.hashes
                if hasattr(hashes, "quick_xor_hash"):
                    info["quickXorHash"] = hashes.quick_xor_hash
                if hasattr(hashes, "sha256_hash"):
                    info["sha256Hash"] = hashes.sha256_hash

        return info

    def info(self, path: str, **kwargs: Any) -> dict[str, Any]:
        """Get info for a path."""
        item = self._get_item_by_path(path)
        item.get().select(
            [
                "id",
                "name",
                "file",
                "folder",
                "size",
                "lastModifiedDateTime",
                "createdDateTime",
            ]
        ).execute_query()
        parent = "/".join(path.strip("/").split("/")[:-1])
        return self._item_to_info(item, parent)

    def stat(self, path: str, **kwargs: Any) -> dict[str, Any]:
        """Get file/directory stats (alias for info)."""
        return self.info(path, **kwargs)

    def exists(self, path: str, **kwargs: Any) -> bool:
        """Check if path exists."""
        try:
            self.info(path)
            return True
        except Exception:
            return False

    def isdir(self, path: str) -> bool:
        """Check if path is a directory."""
        try:
            info = self.info(path)
            return info.get("type") == "directory"
        except Exception:
            return False

    def isfile(self, path: str) -> bool:
        """Check if path is a file."""
        try:
            info = self.info(path)
            return info.get("type") == "file"
        except Exception:
            return False

    def mkdir(self, path: str, create_parents: bool = True, **kwargs: Any) -> None:
        """Create directory."""
        path = self._normalize_path(path)
        if path == "root":
            return

        parts = path.split("/")
        if create_parents:
            current = ""
            for part in parts:
                if current:
                    current = f"{current}/{part}"
                else:
                    current = part
                if not self.exists(current):
                    self._create_folder(current)
        else:
            self._create_folder(path)

    def _create_folder(self, path: str) -> None:
        """Create a single folder."""
        parts = path.split("/")
        name = parts[-1]
        parent_path = "/".join(parts[:-1]) if len(parts) > 1 else ""

        parent = self._get_item_by_path(parent_path)

        from office365.onedrive.driveitems.driveItem import DriveItem

        folder_item = DriveItem(self._get_context())
        folder_item.set_property("name", name)
        folder_item.set_property("folder", {})
        parent.children.add(folder_item).execute_query()

    def _download_file(self, path: str) -> bytes:
        """Download file content."""
        item = self._get_item_by_path(path)
        content = item.get_content().execute_query()
        return content.value

    def _open(
        self,
        path: str,
        mode: str = "rb",
        **kwargs: Any,
    ) -> SharePointFile:
        """Open a file."""
        return SharePointFile(self, path, mode, **kwargs)

    def cat_file(self, path: str, **kwargs: Any) -> bytes:
        """Read file contents."""
        return self._download_file(path)

    def read_bytes(self, path: str) -> bytes:
        """Read file as bytes."""
        return self._download_file(path)

    def write_bytes(self, path: str, data: bytes, **kwargs: Any) -> None:
        """Write bytes to file."""
        path = self._normalize_path(path)
        parts = path.split("/")
        name = parts[-1]
        parent_path = "/".join(parts[:-1]) if len(parts) > 1 else ""

        parent = self._get_item_by_path(parent_path)
        parent.upload(name, data).execute_query()

    def rm(self, path: str, recursive: bool = False, **kwargs: Any) -> None:
        """Remove file or directory."""
        item = self._get_item_by_path(path)
        item.delete_object().execute_query()

    def delete(self, path: str, **kwargs: Any) -> None:
        """Delete file (alias for rm)."""
        self.rm(path, **kwargs)

    def walk(
        self,
        path: str = "",
        maxdepth: int | None = None,
        **kwargs: Any,
    ):
        """Walk directory tree."""
        if maxdepth is not None and maxdepth < 1:
            return

        path = self._normalize_path(path)
        try:
            items = self.ls(path, detail=True)
        except Exception:
            return

        dirs = []
        files = []

        for item in items:
            if item["type"] == "directory":
                dirs.append(item["name"].split("/")[-1])
            else:
                files.append(item["name"].split("/")[-1])

        yield path if path != "root" else "", dirs, files

        for d in dirs:
            subpath = f"{path}/{d}" if path != "root" else d
            new_depth = maxdepth - 1 if maxdepth is not None else None
            yield from self.walk(subpath, maxdepth=new_depth, **kwargs)


class SharePointFS(UnstractFileSystem):
    """SharePoint/OneDrive filesystem connector for Unstract.

    Fork-safe and thread-safe implementation that supports:
    - SharePoint Online document libraries
    - OneDrive for Business (Microsoft 365 work/school accounts)
    - OneDrive Personal (consumer Microsoft accounts)

    Authentication modes:
    - Client credentials (app-only): tenant_id, client_id, client_secret
    - OAuth 2.0 (user delegated): access_token, refresh_token
    """

    def __init__(self, settings: dict[str, Any]):
        super().__init__("SharePoint")

        # Store settings for lazy initialization (handle None case)
        self._settings = settings or {}
        self._site_url = self._settings.get("site_url", "").strip()
        self._tenant_id = self._settings.get("tenant_id", "").strip()
        self._client_id = self._settings.get("client_id", "").strip()
        self._client_secret = self._settings.get("client_secret", "")
        self._drive_id = self._settings.get("drive_id", "")

        # OAuth tokens (for user-delegated access)
        self._access_token = self._settings.get("access_token", "")
        self._refresh_token = self._settings.get("refresh_token", "")

        # User email (for OneDrive with client credentials)
        self._user_email = self._settings.get("user_email", "")

        # Account type (for OneDrive Personal)
        self._is_personal = self._settings.get("is_personal", False)

        # Validate authentication method
        has_oauth = bool(self._access_token and self._refresh_token)
        has_client_creds = bool(self._client_id and self._client_secret)

        if not has_oauth and not has_client_creds:
            base_error = "SharePoint connection requires authentication"
            details = (
                "Provide either \n"
                "- OAuth tokens (access_token, refresh_token) \n"
                "- OR Client Credentials (tenant_id, client_id, client_secret)"
            )
            error_msg = f"{base_error}\nDetails: \n```\n{details}\n```"
            raise ConnectorError(
                error_msg,
                treat_as_user_message=True,
            )

        # Lazy initialization
        self._fs: SharePointFileSystem | None = None
        self._fs_lock = threading.Lock()

    @staticmethod
    def get_id() -> str:
        return "sharepoint|c8f4a9e2-7b3d-4e5f-a1c6-9d8e7f6b5a4c"

    @staticmethod
    def get_name() -> str:
        return "SharePoint / OneDrive"

    @staticmethod
    def get_description() -> str:
        return "Access files in SharePoint Online, OneDrive for Business, or OneDrive Personal"

    @staticmethod
    def get_icon() -> str:
        return "/icons/connector-icons/SharePoint.png"

    @staticmethod
    def get_json_schema() -> str:
        schema_path = os.path.join(
            os.path.dirname(__file__),
            "static",
            "json_schema.json",
        )
        with open(schema_path) as f:
            return f.read()

    @staticmethod
    def can_write() -> bool:
        return True

    @staticmethod
    def can_read() -> bool:
        return True

    @staticmethod
    def requires_oauth() -> bool:
        return True  # Enable OAuth button - also supports client credentials via oneOf

    @staticmethod
    def python_social_auth_backend() -> str:
        return "azuread-tenant-oauth2"

    def get_fsspec_fs(self) -> SharePointFileSystem:
        """Get SharePoint filesystem with lazy initialization.

        Thread-safe and fork-safe initialization.

        Returns:
            SharePointFileSystem instance
        """
        if self._fs is None:
            with _SHAREPOINT_INIT_LOCK:
                if self._fs is None:
                    logger.info("Initializing SharePoint filesystem (lazy init)")

                    try:
                        # Determine tenant based on account type
                        # - Personal accounts use "consumers"
                        # - Business accounts use the provided tenant_id or "common"
                        if self._is_personal:
                            tenant = "consumers"
                        elif self._tenant_id:
                            tenant = self._tenant_id
                        else:
                            tenant = "common"

                        self._fs = SharePointFileSystem(
                            site_url=self._site_url,
                            tenant_id=tenant,
                            client_id=self._client_id,
                            client_secret=self._client_secret or None,
                            access_token=self._access_token or None,
                            refresh_token=self._refresh_token or None,
                            drive_id=self._drive_id or None,
                            is_personal=self._is_personal,
                            user_email=self._user_email or None,
                        )
                        logger.info("SharePoint filesystem initialized")
                    except Exception as e:
                        base_error = "Failed to initialize SharePoint connection"
                        library_error = str(e) if str(e) else None
                        error_msg = (
                            f"{base_error}\nDetails: \n```\n{library_error}\n```"
                            if library_error
                            else base_error
                        )
                        raise ConnectorError(
                            error_msg,
                            treat_as_user_message=True,
                        ) from e

        return self._fs

    def test_credentials(self) -> bool:
        """Test SharePoint/OneDrive credentials."""
        try:
            fs = self.get_fsspec_fs()
            # Try to list root to verify access
            fs.ls("")
            return True
        except Exception as e:
            base_error = "SharePoint connection test failed"
            library_error = str(e) if str(e) else None
            error_msg = (
                f"{base_error}\nDetails: \n```\n{library_error}\n```"
                if library_error
                else base_error
            )
            raise ConnectorError(
                error_msg,
                treat_as_user_message=True,
            ) from e

    def extract_metadata_file_hash(self, metadata: dict[str, Any]) -> str | None:
        """Extract unique file hash from SharePoint metadata.

        SharePoint uses quickXorHash or SHA256 for file integrity.

        Args:
            metadata: File metadata dictionary

        Returns:
            File hash string or None
        """
        # Try different hash fields in order of preference
        hash_fields = ["quickXorHash", "cTag", "eTag", "id"]

        for field in hash_fields:
            if field in metadata and metadata[field]:
                value = metadata[field]
                if isinstance(value, str):
                    # Remove quotes and version info from eTags
                    return value.split(",")[0].strip('"')
                return str(value)

        logger.warning(
            f"[SharePoint] No file hash found in metadata: {list(metadata.keys())}"
        )
        return None

    def is_dir_by_metadata(self, metadata: dict[str, Any]) -> bool:
        """Check if path is a directory from metadata.

        Args:
            metadata: File metadata dictionary

        Returns:
            True if path is a directory
        """
        return metadata.get("type") == "directory"

    def extract_modified_date(self, metadata: dict[str, Any]) -> datetime | None:
        """Extract last modified date from SharePoint metadata.

        Args:
            metadata: File metadata dictionary

        Returns:
            datetime object or None
        """
        # Try different date fields
        date_fields = ["lastModifiedDateTime", "modified", "createdDateTime"]

        for field in date_fields:
            value = metadata.get(field)
            if value:
                if isinstance(value, datetime):
                    if value.tzinfo is None:
                        return value.replace(tzinfo=UTC)
                    return value.astimezone(UTC)
                elif isinstance(value, str):
                    try:
                        # Handle ISO format with Z suffix
                        if value.endswith("Z"):
                            value = value[:-1] + "+00:00"
                        dt = datetime.fromisoformat(value)
                        if dt.tzinfo is None:
                            return dt.replace(tzinfo=UTC)
                        return dt.astimezone(UTC)
                    except ValueError:
                        logger.warning(f"[SharePoint] Invalid datetime format: {value}")
                        continue

        logger.debug(
            f"[SharePoint] No modified date in metadata: {list(metadata.keys())}"
        )
        return None

    @staticmethod
    def get_connector_root_dir(input_dir: str, **kwargs: Any) -> str:
        """Get root directory path for SharePoint.

        SharePoint paths should not have leading slashes.
        """
        input_dir = input_dir.strip("/")
        if not input_dir:
            return ""
        return f"{input_dir}/"
