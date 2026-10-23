"""Profile update endpoints, through the org-scoped URL and the auth middleware."""

from unittest.mock import MagicMock, patch

from account_v2.models import Organization
from account_v2.test_user_profile import GIF, LocalStorageMixin, make_user, png_bytes
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import RequestFactory, TestCase
from utils.user_context import UserContext

from tenant_account_v2.models import OrganizationMember

BASE = "/api/v1/unstract/org-a/users/profile/"
PHOTO = f"{BASE}photo/"


def upload(content: bytes, name: str = "me.png") -> dict:
    return {"photo": SimpleUploadedFile(name, content)}


class ProfileEndpointTests(LocalStorageMixin, TestCase):
    def setUp(self) -> None:
        super().setUp()
        org = Organization.objects.create(
            name="org-a", display_name="Org A", organization_id="org-a"
        )
        self.user = make_user("me@example.com")
        OrganizationMember.objects.create(organization=org, user=self.user, role="admin")
        # OSS auth throughout.
        for target in (
            "account_v2.custom_auth_middleware.AuthenticationPluginRegistry"
            ".is_plugin_available",
            "account_v2.authentication_controller.AuthenticationPluginRegistry"
            ".is_plugin_available",
        ):
            patcher = patch(target, MagicMock(return_value=False))
            patcher.start()
            self.addCleanup(patcher.stop)
        self.addCleanup(UserContext.set_organization_identifier, None)
        self.client.force_login(self.user)
        session = self.client.session
        session["organization"] = "org-a"
        session.save()

    def profile(self) -> dict:
        response = self.client.get(BASE)
        self.assertEqual(response.status_code, 200, response.content)
        return response.json()["user"]

    def patch_profile(self, body: dict):
        return self.client.patch(BASE, body, content_type="application/json")

    def error_attrs(self, response) -> list[str]:
        self.assertEqual(response.status_code, 400, response.content)
        return [e["attr"] for e in response.json()["errors"]]

    # GET

    def test_get_adds_photo_url_and_language(self) -> None:
        user = self.profile()
        self.assertIsNone(user["photo_url"])
        self.assertEqual(user["language"], "en-US")
        self.assertEqual(user["name"], "me@example.com")
        self.assertTrue(user["is_admin"])

    # PATCH

    def test_patch_name_is_trimmed_and_shown(self) -> None:
        response = self.patch_profile({"display_name": "  Me Edited  "})
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.json()["user"]["display_name"], "Me Edited")
        user = self.profile()
        self.assertEqual((user["name"], user["display_name"]), ("Me Edited",) * 2)
        self.user.refresh_from_db()
        self.assertEqual(self.user.profile_display_name, "Me Edited")

    def test_patch_language(self) -> None:
        type(self.user).objects.filter(pk=self.user.pk).update(language="xx-XX")
        self.assertEqual(self.profile()["language"], "xx-XX")
        response = self.patch_profile({"language": "en-US"})
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(self.profile()["language"], "en-US")

    def test_empty_patch_changes_nothing(self) -> None:
        self.patch_profile({"display_name": "Me Edited"})
        response = self.patch_profile({})
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.json()["user"]["display_name"], "Me Edited")
        self.user.refresh_from_db()
        self.assertEqual(self.user.profile_display_name, "Me Edited")

    def test_patch_refuses_empty_and_blank_names(self) -> None:
        for name in ("", "   "):
            with self.subTest(name=name):
                self.assertEqual(
                    self.error_attrs(self.patch_profile({"display_name": name})),
                    ["display_name"],
                )

    def test_patch_language_alone_keeps_the_name(self) -> None:
        self.patch_profile({"display_name": "Me Edited"})
        response = self.patch_profile({"language": "en-US"})
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.json()["user"]["display_name"], "Me Edited")

    def test_patch_refuses_name_over_64(self) -> None:
        self.assertEqual(
            self.error_attrs(self.patch_profile({"display_name": "x" * 65})),
            ["display_name"],
        )
        self.assertEqual(self.patch_profile({"display_name": "x" * 64}).status_code, 200)

    def test_patch_ignores_fields_it_does_not_own(self) -> None:
        before = type(self.user).objects.get(pk=self.user.pk)
        response = self.patch_profile(
            {
                "display_name": "Me Edited",
                "is_staff": True,
                "email": "evil@example.com",
                "profile_photo_updated_at": "2026-01-01T00:00:00Z",
            }
        )
        self.assertEqual(response.status_code, 200, response.content)
        self.user.refresh_from_db()
        self.assertEqual(self.user.profile_display_name, "Me Edited")
        self.assertEqual(
            (self.user.is_staff, self.user.email, self.user.profile_photo_updated_at),
            (before.is_staff, before.email, None),
        )

    def test_patch_refuses_unknown_language(self) -> None:
        self.assertEqual(
            self.error_attrs(
                self.patch_profile({"display_name": "Me", "language": "fr-FR"})
            ),
            ["language"],
        )

    # Photo

    def test_upload_then_profile_and_photo(self) -> None:
        response = self.client.post(PHOTO, upload(png_bytes()))
        self.assertEqual(response.status_code, 200, response.content)
        url = response.json()["photo_url"]
        self.assertTrue(url.startswith(PHOTO + "?v="), url)
        user = self.profile()
        self.assertEqual((user["photo_url"], user["picture"]), (url, url))

        photo = self.client.get(url)
        self.assertEqual(photo.status_code, 200)
        self.assertEqual(photo.content, png_bytes())
        self.assertEqual(photo["Content-Type"], "image/png")
        self.assertEqual(photo["X-Content-Type-Options"], "nosniff")

    def test_photo_is_served_to_a_client_that_accepts_only_images(self) -> None:
        self.client.post(PHOTO, upload(png_bytes()))
        for accept in ("image/png", "image/*"):
            with self.subTest(accept=accept):
                photo = self.client.get(PHOTO, HTTP_ACCEPT=accept)
                self.assertEqual(photo.status_code, 200)
                self.assertEqual(photo.content, png_bytes())
                self.assertEqual(photo["Content-Type"], "image/png")

    def test_no_photo_is_a_json_404_when_only_images_are_accepted(self) -> None:
        response = self.client.get(PHOTO, HTTP_ACCEPT="image/png")
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response["Content-Type"], "application/json")
        self.assertEqual(response.json()["type"], "client_error")

    def test_type_comes_from_the_bytes_not_the_name(self) -> None:
        response = self.client.post(PHOTO, upload(png_bytes(), "me.jpg"))
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(self.client.get(PHOTO)["Content-Type"], "image/png")

    def test_upload_refuses_gif(self) -> None:
        response = self.client.post(PHOTO, upload(GIF, "me.gif"))
        self.assertEqual(self.error_attrs(response), ["photo"])

    def test_upload_refuses_over_2_mb_before_reading_it(self) -> None:
        big = png_bytes() + b"\x00" * (2 * 1024 * 1024 + 1 - len(png_bytes()))
        with patch("utils.FileValidator.magic.from_buffer") as sniff:
            response = self.client.post(PHOTO, upload(big))
        self.assertEqual(self.error_attrs(response), ["photo"])
        sniff.assert_not_called()

    def test_set_organization_returns_photo_for_the_new_organization(self) -> None:
        from account_v2.authentication_controller import AuthenticationController

        Organization.objects.create(
            name="org-b", display_name="Org B", organization_id="org-b"
        )
        self.client.post(PHOTO, upload(png_bytes()))
        self.user.refresh_from_db()
        request = RequestFactory().post("/x/")
        request.user = self.user
        request.session = self.client.session  # still on org-a
        for target, value in (
            (
                "account_v2.authentication_controller.CacheService"
                ".get_user_organizations",
                MagicMock(return_value={"org-a", "org-b"}),
            ),
            (
                "account_v2.authentication_controller.OrganizationMemberService"
                ".remove_user_membership_in_organization_cache",
                MagicMock(),
            ),
            (
                "account_v2.authentication_controller.OrganizationMemberService"
                ".set_user_membership_in_organization_cache",
                MagicMock(),
            ),
            (
                "account_v2.authentication_controller.AuthenticationService"
                ".setup_default_adapters_for_user",
                MagicMock(),
            ),
        ):
            patcher = patch(target, value)
            patcher.start()
            self.addCleanup(patcher.stop)
        response = AuthenticationController().set_user_organization(request, "org-b")
        self.assertEqual(response.status_code, 200)
        self.assertIn("/org-b/users/profile/photo/", response.data["user"]["picture"])

    def test_upload_accepts_exactly_2_mb(self) -> None:
        exact = png_bytes() + b"\x00" * (2 * 1024 * 1024 - len(png_bytes()))
        self.assertEqual(self.client.post(PHOTO, upload(exact)).status_code, 200)

    def test_upload_refuses_missing_file(self) -> None:
        self.assertEqual(self.error_attrs(self.client.post(PHOTO, {})), ["photo"])

    def test_no_photo_is_404(self) -> None:
        self.assertEqual(self.client.get(PHOTO).status_code, 404)

    def test_delete_photo(self) -> None:
        self.client.post(PHOTO, upload(png_bytes()))
        self.assertEqual(self.client.delete(PHOTO).status_code, 204)
        self.assertEqual(self.client.get(PHOTO).status_code, 404)
        self.assertIsNone(self.profile()["photo_url"])

    def test_delete_without_photo_is_204(self) -> None:
        self.assertEqual(self.client.delete(PHOTO).status_code, 204)

    # Auth

    def test_anonymous_caller_is_refused(self) -> None:
        self.client.logout()
        for method in ("get", "post", "delete"):
            with self.subTest(method=method):
                response = getattr(self.client, method)(PHOTO)
                self.assertEqual(response.status_code, 401)
        self.assertEqual(self.patch_profile({"display_name": "x"}).status_code, 401)

    def test_service_account_cannot_change_the_profile(self) -> None:
        type(self.user).objects.filter(pk=self.user.pk).update(is_service_account=True)
        calls = (
            ("patch", lambda: self.patch_profile({"display_name": "Bot"})),
            ("post", lambda: self.client.post(PHOTO, upload(png_bytes()))),
            ("delete", lambda: self.client.delete(PHOTO)),
        )
        for method, call in calls:
            with self.subTest(method=method):
                self.assertEqual(call().status_code, 403)
        self.user.refresh_from_db()
        self.assertEqual(self.user.profile_display_name, "")
        self.assertIsNone(self.user.profile_photo_updated_at)


class ProfileSchemaTests(TestCase):
    def test_schema_documents_the_contract(self) -> None:
        from drf_spectacular.generators import SchemaGenerator

        from tenant_account_v2 import users_urls

        schema = SchemaGenerator(patterns=users_urls.urlpatterns).get_schema(
            request=None, public=True
        )
        ops = {
            op["operationId"]: op
            for path in schema["paths"].values()
            for op in path.values()
        }
        self.assertTrue(
            {
                "user_profile",
                "user_profile_update",
                "user_profile_photo",
                "user_profile_photo_upload",
                "user_profile_photo_delete",
            }
            <= set(ops)
        )
        user = schema["components"]["schemas"]["UserProfile"]
        self.assertTrue({"photo_url", "language"} <= set(user["required"]))
        self.assertTrue(user["properties"]["photo_url"]["nullable"])
        update = schema["components"]["schemas"]["PatchedProfileUpdate"]
        self.assertNotIn("required", update)
        self.assertEqual(update["properties"]["display_name"]["maxLength"], 64)
        self.assertEqual(
            set(ops["user_profile_update"]["responses"]),
            {"200", "400", "403", "404", "500"},
        )
        photo = ops["user_profile_photo"]["responses"]["200"]["content"]
        self.assertEqual(set(photo), {"image/png", "image/jpeg"})
        upload = ops["user_profile_photo_upload"]["requestBody"]["content"]
        self.assertEqual(set(upload), {"multipart/form-data"})


def test_photo_upload_is_documented_as_binary() -> None:
    """A bare FileField documents as `format: uri`, which generators turn into a
    string parameter instead of a multipart upload.
    """
    from drf_spectacular.openapi import AutoSchema

    from tenant_account_v2.serializer import ProfilePhotoSerializer

    field = ProfilePhotoSerializer().fields["photo"]
    mapped = AutoSchema()._map_serializer_field(field, direction="request")

    assert mapped == {"type": "string", "format": "binary"}
