"""Tests for the locally edited profile: name, language and photo."""

import os
import secrets
import struct
import tempfile
import zlib
from dataclasses import dataclass
from unittest.mock import patch

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.test import TestCase

from account_v2 import user_profile
from account_v2.dto import UserInfo
from account_v2.models import User


def png_bytes() -> bytes:
    """A valid 1x1 PNG."""

    def chunk(kind: bytes, data: bytes) -> bytes:
        body = kind + data
        return struct.pack(">I", len(data)) + body + struct.pack(">I", zlib.crc32(body))

    ihdr = struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0)
    idat = zlib.compress(b"\x00\xff\x00\x00")
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", ihdr)
        + chunk(b"IDAT", idat)
        + chunk(b"IEND", b"")
    )


JPEG = b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00" + (
    b"\x00" * 64
)
GIF = b"GIF89a\x01\x00\x01\x00\x80\x00\x00\x00\x00\x00\xff\xff\xff!\xf9\x04" + (
    b"\x00" * 32
)


def make_user(email: str = "a@example.com") -> User:
    return User.objects.create_user(
        username=email, email=email, password=secrets.token_urlsafe()
    )


class LocalStorageMixin:
    """Points the permanent storage at a temp dir for the test."""

    def setUp(self) -> None:
        super().setUp()
        self.tmp = tempfile.TemporaryDirectory()
        env = patch.dict(
            "os.environ",
            {
                "PERMANENT_REMOTE_STORAGE": '{"provider": "local"}',
                "REMOTE_USER_PROFILE_PHOTO_PATH": self.tmp.name,
            },
        )
        env.start()
        self.addCleanup(env.stop)
        self.addCleanup(self.tmp.cleanup)


class PhotoStorageTests(LocalStorageMixin, TestCase):
    def setUp(self) -> None:
        super().setUp()
        self.user = make_user()

    def test_no_photo_reads_none(self) -> None:
        self.assertIsNone(user_profile.read_photo(self.user))

    def test_png_round_trip(self) -> None:
        user_profile.save_photo(self.user, png_bytes())
        self.user.refresh_from_db()
        self.assertIsNotNone(self.user.profile_photo_updated_at)
        self.assertEqual(user_profile.read_photo(self.user), (png_bytes(), "image/png"))

    def test_jpeg_round_trip(self) -> None:
        user_profile.save_photo(self.user, JPEG)
        self.assertEqual(user_profile.read_photo(self.user), (JPEG, "image/jpeg"))

    def test_new_photo_replaces_old(self) -> None:
        user_profile.save_photo(self.user, JPEG)
        user_profile.save_photo(self.user, png_bytes())
        self.assertEqual(user_profile.read_photo(self.user)[1], "image/png")

    def test_photos_are_per_user(self) -> None:
        other = make_user("b@example.com")
        user_profile.save_photo(self.user, png_bytes())
        user_profile.save_photo(other, JPEG)
        self.assertEqual(user_profile.read_photo(self.user)[1], "image/png")
        self.assertEqual(user_profile.read_photo(other)[1], "image/jpeg")

    def test_delete_photo(self) -> None:
        user_profile.save_photo(self.user, png_bytes())
        user_profile.delete_photo(self.user)
        self.user.refresh_from_db()
        self.assertIsNone(self.user.profile_photo_updated_at)
        self.assertIsNone(user_profile.read_photo(self.user))

    def test_delete_without_photo_is_a_no_op(self) -> None:
        user_profile.delete_photo(self.user)
        self.assertIsNone(user_profile.read_photo(self.user))

    def test_missing_object_is_logged_and_not_served(self) -> None:
        user_profile.save_photo(self.user, png_bytes())
        os.remove(user_profile.photo_path(self.user))
        with self.assertLogs("account_v2.user_profile", "WARNING"):
            self.assertIsNone(user_profile.read_photo(self.user))

    def test_delete_clears_timestamp_even_when_in_memory_copy_is_stale(self) -> None:
        user_profile.save_photo(self.user, png_bytes())
        stale = User.objects.get(pk=self.user.pk)
        stale.profile_photo_updated_at = None
        user_profile.delete_photo(stale)
        self.user.refresh_from_db()
        self.assertIsNone(self.user.profile_photo_updated_at)

    def test_stored_bytes_that_are_not_an_image_are_not_served(self) -> None:
        user_profile.save_photo(self.user, png_bytes())
        path = user_profile.photo_path(self.user)
        with open(path, "wb") as f:
            f.write(GIF)
        with self.assertLogs("account_v2.user_profile", "WARNING"):
            self.assertIsNone(user_profile.read_photo(self.user))


class PhotoBasePathTests(TestCase):
    def test_explicit_env_wins(self) -> None:
        with patch.dict(
            "os.environ",
            {
                "REMOTE_USER_PROFILE_PHOTO_PATH": "bucket/photos",
                "REMOTE_PROMPT_STUDIO_FILE_PATH": "other/prompt-studio-data",
            },
        ):
            self.assertEqual(user_profile.photo_base_path(), "bucket/photos")

    def test_defaults_beside_prompt_studio_files(self) -> None:
        with patch.dict(
            "os.environ",
            {
                "REMOTE_USER_PROFILE_PHOTO_PATH": "",
                "REMOTE_PROMPT_STUDIO_FILE_PATH": "bucket-x/prompt-studio-data",
            },
        ):
            self.assertEqual(
                user_profile.photo_base_path(), "bucket-x/user-profile-photos"
            )

    def test_unset_paths_are_a_config_error(self) -> None:
        with patch.dict(
            "os.environ",
            {"REMOTE_USER_PROFILE_PHOTO_PATH": "", "REMOTE_PROMPT_STUDIO_FILE_PATH": ""},
        ):
            with self.assertRaises(ImproperlyConfigured):
                user_profile.photo_base_path()


class PhotoUrlTests(TestCase):
    def setUp(self) -> None:
        self.user = make_user()

    def test_none_without_photo(self) -> None:
        self.assertIsNone(user_profile.photo_url(self.user, "org-a"))

    def test_none_without_organization(self) -> None:
        self.user.profile_photo_updated_at = user_profile.timezone.now()
        self.assertIsNone(user_profile.photo_url(self.user, None))

    def test_org_scoped_and_versioned(self) -> None:
        self.user.profile_photo_updated_at = user_profile.timezone.now()
        version = int(self.user.profile_photo_updated_at.timestamp())
        self.assertEqual(
            user_profile.photo_url(self.user, "org-a"),
            f"/{settings.TENANT_SUBFOLDER_PREFIX}/org-a/users/profile/photo/"
            f"?v={version}",
        )


@dataclass
class PluginUserInfo(UserInfo):
    """Stand-in for an auth plugin's own UserInfo with an extra field."""

    email_verified: bool = False


class ProfileOverrideTests(TestCase):
    def setUp(self) -> None:
        self.user = make_user()
        self.info = UserInfo(
            email="a@example.com",
            user_id="auth0|1",
            name="Provider",
            display_name="Provider Name",
            picture="https://provider/pic.png",
        )

    def test_no_edits_keeps_provider_values(self) -> None:
        result = user_profile.with_profile_overrides(self.info, self.user, "org-a")
        self.assertEqual(result, self.info)

    def test_edited_name_replaces_name_and_display_name(self) -> None:
        self.user.profile_display_name = "Edited"
        result = user_profile.with_profile_overrides(self.info, self.user, "org-a")
        self.assertEqual((result.name, result.display_name), ("Edited", "Edited"))
        self.assertEqual(self.info.name, "Provider")

    def test_photo_replaces_picture(self) -> None:
        self.user.profile_photo_updated_at = user_profile.timezone.now()
        result = user_profile.with_profile_overrides(self.info, self.user, "org-a")
        self.assertEqual(result.picture, user_profile.photo_url(self.user, "org-a"))

    def test_keeps_plugin_fields(self) -> None:
        info = PluginUserInfo(
            email="a@example.com", user_id="auth0|1", email_verified=True
        )
        self.user.profile_display_name = "Edited"
        result = user_profile.with_profile_overrides(info, self.user, "org-a")
        self.assertIsInstance(result, PluginUserInfo)
        self.assertTrue(result.email_verified)


class LanguageDefaultTests(TestCase):
    def test_new_user_language_is_en_us(self) -> None:
        self.assertEqual(make_user().language, "en-US")


class ControllerOrganizationTests(TestCase):
    def test_photo_url_uses_the_organization_passed_in(self) -> None:
        from types import SimpleNamespace

        from account_v2.authentication_controller import AuthenticationController

        user = make_user()
        user.profile_photo_updated_at = user_profile.timezone.now()
        with patch(
            "account_v2.authentication_controller.AuthenticationPluginRegistry"
            ".is_plugin_available",
            return_value=False,
        ):
            info = AuthenticationController().get_user_info(
                SimpleNamespace(user=user), organization_id="org-b"
            )
        self.assertEqual(info.picture, user_profile.photo_url(user, "org-b"))
