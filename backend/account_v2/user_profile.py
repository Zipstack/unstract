"""The profile a user edits locally: name, language and photo.

The edited name and photo are stored here, never written to the identity
provider, and shown in place of the provider's values.
"""

import dataclasses
import os
from pathlib import PurePosixPath
from typing import TypeVar

import magic
from django.conf import settings
from django.utils import timezone
from utils.file_storage.constants import FileStorageConstants, FileStorageKeys

from account_v2.dto import UserInfo
from account_v2.models import User
from unstract.sdk1.file_storage.constants import StorageType
from unstract.sdk1.file_storage.env_helper import EnvHelper

PHOTO_TYPES = ("image/png", "image/jpeg")
MAX_PHOTO_BYTES = 2 * 1024 * 1024
LANGUAGES = ("en-US",)
PHOTO_PATH_ENV = "REMOTE_USER_PROFILE_PHOTO_PATH"

T = TypeVar("T", bound=UserInfo)


def photo_base_path() -> str:
    """Where photos are kept: the env if set, else beside Prompt Studio files.

    The default lands in the same bucket as Prompt Studio data, which every
    deployment already configures.
    """
    explicit = os.environ.get(PHOTO_PATH_ENV, "").strip()
    if explicit:
        return explicit
    prompt_studio = os.environ.get(
        FileStorageConstants.REMOTE_PROMPT_STUDIO_FILE_PATH, ""
    )
    return str(PurePosixPath(prompt_studio).parent / "user-profile-photos")


def photo_path(user: User) -> str:
    return str(PurePosixPath(photo_base_path()) / str(user.pk) / "photo")


def _storage():
    return EnvHelper.get_storage(
        storage_type=StorageType.PERMANENT,
        env_name=FileStorageKeys.PERMANENT_REMOTE_STORAGE,
    )


def save_photo(user: User, data: bytes) -> None:
    """Store an already validated PNG or JPEG as the user's photo."""
    fs = _storage()
    path = photo_path(user)
    fs.mkdir(str(PurePosixPath(path).parent), create_parents=True)
    fs.write(path=path, mode="wb", data=data)
    user.profile_photo_updated_at = timezone.now()
    user.save(update_fields=["profile_photo_updated_at"])


def read_photo(user: User) -> tuple[bytes, str] | None:
    """The photo bytes and content type, or None when there is no servable photo."""
    if not user.profile_photo_updated_at:
        return None
    fs = _storage()
    path = photo_path(user)
    if not fs.exists(path):
        return None
    data = fs.read(path=path, mode="rb")
    content_type = magic.from_buffer(data, mime=True)
    if content_type not in PHOTO_TYPES:
        return None
    return data, content_type


def delete_photo(user: User) -> None:
    fs = _storage()
    path = photo_path(user)
    if fs.exists(path):
        fs.rm(path, recursive=False)
    if user.profile_photo_updated_at:
        user.profile_photo_updated_at = None
        user.save(update_fields=["profile_photo_updated_at"])


def photo_url(user: User, organization_id: str | None) -> str | None:
    """Org-scoped URL of the photo endpoint, versioned so a new photo busts caches."""
    if not (user.profile_photo_updated_at and organization_id):
        return None
    version = int(user.profile_photo_updated_at.timestamp())
    return (
        f"/{settings.TENANT_SUBFOLDER_PREFIX}/{organization_id}"
        f"/users/profile/photo/?v={version}"
    )


def with_profile_overrides(info: T, user: User, organization_id: str | None) -> T:
    """A copy of the provider's user info with the locally edited values on top."""
    changes: dict[str, str] = {}
    if user.profile_display_name:
        changes["name"] = user.profile_display_name
        changes["display_name"] = user.profile_display_name
    url = photo_url(user, organization_id)
    if url:
        changes["picture"] = url
    return dataclasses.replace(info, **changes) if changes else info
