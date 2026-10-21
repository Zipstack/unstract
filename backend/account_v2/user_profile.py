"""The profile a user edits locally: name, language and photo.

The edited name and language live on the User row and the photo in the
permanent file storage. Neither is written to the identity provider; both
are shown in place of the provider's values.
"""

import dataclasses
import logging
import os
from pathlib import PurePosixPath
from typing import TypeVar

import magic
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
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

logger = logging.getLogger(__name__)


def photo_base_path() -> str:
    """Where photos are kept: the env if set, else beside Prompt Studio files.

    The default lands in the same bucket as Prompt Studio data.
    """
    explicit = os.environ.get(PHOTO_PATH_ENV, "").strip()
    if explicit:
        return explicit
    prompt_studio = os.environ.get(
        FileStorageConstants.REMOTE_PROMPT_STUDIO_FILE_PATH, ""
    )
    if not prompt_studio.strip():
        raise ImproperlyConfigured(
            f"Set {PHOTO_PATH_ENV} or "
            f"{FileStorageConstants.REMOTE_PROMPT_STUDIO_FILE_PATH} to store "
            "profile photos."
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
    path = photo_path(user)
    try:
        data = _storage().read(path=path, mode="rb")
    except FileNotFoundError:
        logger.warning("Profile photo of user %s is missing at %s", user.pk, path)
        return None
    content_type = magic.from_buffer(data, mime=True)
    if content_type not in PHOTO_TYPES:
        logger.warning(
            "Profile photo of user %s is %s, not served", user.pk, content_type
        )
        return None
    return data, content_type


def delete_photo(user: User) -> None:
    """Remove the object, then the record, so a failed removal can be retried."""
    recorded = User.objects.filter(
        pk=user.pk, profile_photo_updated_at__isnull=False
    ).exists()
    if recorded:  # Without a recorded photo there is no storage to touch.
        try:
            _storage().rm(photo_path(user), recursive=False)
        except FileNotFoundError:
            logger.warning("Profile photo of user %s was already gone", user.pk)
        User.objects.filter(pk=user.pk).update(profile_photo_updated_at=None)
    user.profile_photo_updated_at = None


def photo_url(user: User, organization_id: str | None) -> str | None:
    """Org-scoped URL of the photo endpoint, versioned by upload time in seconds."""
    if not (user.profile_photo_updated_at and organization_id):
        return None
    version = int(user.profile_photo_updated_at.timestamp())
    return (
        f"/{settings.TENANT_SUBFOLDER_PREFIX}/{organization_id}"
        f"/users/profile/photo/?v={version}"
    )


def with_profile_overrides(info: T, user: User, organization_id: str | None) -> T:
    """A copy of the provider's user info with the locally edited values on top."""
    changes: dict[str, str | None] = {}
    if user.profile_display_name:
        # The edited name is the whole name; the provider's surname would
        # otherwise be appended to it where clients join the two.
        changes["name"] = user.profile_display_name
        changes["display_name"] = user.profile_display_name
        changes["family_name"] = None
    url = photo_url(user, organization_id)
    if url:
        changes["picture"] = url
    return dataclasses.replace(info, **changes) if changes else info
