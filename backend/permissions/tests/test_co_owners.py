"""Tests for co-owner management: permissions, serializers, and views."""

from unittest.mock import MagicMock, Mock, patch
from uuid import uuid4

from django.test import RequestFactory, TestCase
from permissions.co_owner_serializers import AddCoOwnerSerializer, RemoveCoOwnerSerializer
from permissions.permission import (
    IsOwner,
    IsOwnerOrSharedUser,
    IsOwnerOrSharedUserOrSharedToOrg,
)


def make_filter_side_effect(target_pk: object):
    """Return a filter side_effect that returns True only for the given pk."""

    def filter_side_effect(**kwargs: object) -> Mock:
        mock_qs = Mock()
        mock_qs.exists.return_value = kwargs.get("pk") == target_pk
        return mock_qs

    return filter_side_effect


def make_resource_mock(creator: Mock, co_owner_count: int = 1) -> Mock:
    """Create a mock resource with a co_owners queryset."""
    resource = Mock()
    resource.created_by = creator
    co_owners_qs = MagicMock()
    co_owners_qs.count.return_value = co_owner_count
    co_owners_qs.filter.return_value.exists.return_value = False
    resource.co_owners = co_owners_qs
    return resource


class CoOwnerPermissionTestBase(TestCase):
    """Base class for co-owner permission tests."""

    def setUp(self) -> None:
        self.factory = RequestFactory()

        self.creator = Mock()
        self.creator.pk = uuid4()

        self.co_owner = Mock()
        self.co_owner.pk = uuid4()

        self.other_user = Mock()
        self.other_user.pk = uuid4()

        self.resource = Mock()
        self.resource.created_by = self.creator
        co_owners_qs = MagicMock()
        co_owners_qs.filter.return_value.exists.return_value = False
        self.resource.co_owners = co_owners_qs

    def _make_request(self, user: Mock) -> Mock:
        request = self.factory.get("/fake/")
        request.user = user
        return request


class TestIsOwnerPermission(CoOwnerPermissionTestBase):
    """Test the IsOwner permission class recognizes co-owners."""

    def setUp(self) -> None:
        super().setUp()
        self.permission = IsOwner()

    def test_creator_has_permission(self) -> None:
        request = self._make_request(self.creator)
        self.assertTrue(
            self.permission.has_object_permission(request, None, self.resource)
        )

    def test_co_owner_has_permission(self) -> None:
        self.resource.co_owners.filter.side_effect = make_filter_side_effect(
            self.co_owner.pk
        )
        request = self._make_request(self.co_owner)
        self.assertTrue(
            self.permission.has_object_permission(request, None, self.resource)
        )

    def test_other_user_denied(self) -> None:
        request = self._make_request(self.other_user)
        self.assertFalse(
            self.permission.has_object_permission(request, None, self.resource)
        )

    def test_object_without_co_owners_field(self) -> None:
        """Permission works for objects that don't have co_owners."""
        resource = Mock(spec=["created_by"])
        resource.created_by = self.creator

        request = self._make_request(self.other_user)
        self.assertFalse(
            self.permission.has_object_permission(request, None, resource)
        )


class TestIsOwnerOrSharedUserPermission(CoOwnerPermissionTestBase):
    """Test IsOwnerOrSharedUser recognizes co-owners."""

    def setUp(self) -> None:
        super().setUp()
        self.permission = IsOwnerOrSharedUser()

        self.shared_user = Mock()
        self.shared_user.pk = uuid4()

        shared_users_qs = MagicMock()
        shared_users_qs.filter.return_value.exists.return_value = False
        self.resource.shared_users = shared_users_qs

    def test_co_owner_has_permission(self) -> None:
        self.resource.co_owners.filter.side_effect = make_filter_side_effect(
            self.co_owner.pk
        )
        request = self._make_request(self.co_owner)
        self.assertTrue(
            self.permission.has_object_permission(request, None, self.resource)
        )

    def test_shared_user_has_permission(self) -> None:
        self.resource.shared_users.filter.side_effect = make_filter_side_effect(
            self.shared_user.pk
        )
        request = self._make_request(self.shared_user)
        self.assertTrue(
            self.permission.has_object_permission(request, None, self.resource)
        )

    def test_other_user_denied(self) -> None:
        request = self._make_request(self.other_user)
        self.assertFalse(
            self.permission.has_object_permission(request, None, self.resource)
        )


class TestIsOwnerOrSharedUserOrSharedToOrgPermission(CoOwnerPermissionTestBase):
    """Test IsOwnerOrSharedUserOrSharedToOrg recognizes co-owners."""

    def setUp(self) -> None:
        super().setUp()
        self.permission = IsOwnerOrSharedUserOrSharedToOrg()
        self.resource.shared_to_org = False

        shared_users_qs = MagicMock()
        shared_users_qs.filter.return_value.exists.return_value = False
        self.resource.shared_users = shared_users_qs

    def test_co_owner_has_permission(self) -> None:
        self.resource.co_owners.filter.side_effect = make_filter_side_effect(
            self.co_owner.pk
        )
        request = self._make_request(self.co_owner)
        self.assertTrue(
            self.permission.has_object_permission(request, None, self.resource)
        )

    def test_shared_to_org_grants_access(self) -> None:
        self.resource.shared_to_org = True
        request = self._make_request(self.other_user)
        self.assertTrue(
            self.permission.has_object_permission(request, None, self.resource)
        )


class TestAddCoOwnerSerializer(TestCase):
    """Test AddCoOwnerSerializer validation logic."""

    @patch("permissions.co_owner_serializers.User.objects")
    @patch("permissions.co_owner_serializers.OrganizationMember.objects")
    @patch("permissions.co_owner_serializers.UserContext.get_organization")
    def test_valid_add_co_owner(
        self, mock_get_org: Mock, mock_org_member: Mock, mock_user_objects: Mock
    ) -> None:
        creator = Mock()
        new_co_owner = Mock()
        new_co_owner.id = 42

        mock_get_org.return_value = Mock()
        mock_org_member.filter.return_value.exists.return_value = True
        mock_user_objects.get.return_value = new_co_owner

        resource = make_resource_mock(creator)

        serializer = AddCoOwnerSerializer(
            data={"user_id": 42},
            context={"resource": resource},
        )
        self.assertTrue(serializer.is_valid())

    @patch("permissions.co_owner_serializers.OrganizationMember.objects")
    @patch("permissions.co_owner_serializers.UserContext.get_organization")
    def test_user_not_in_organization(
        self, mock_get_org: Mock, mock_org_member: Mock
    ) -> None:
        creator = Mock()
        mock_get_org.return_value = Mock()
        mock_org_member.filter.return_value.exists.return_value = False

        resource = make_resource_mock(creator)

        serializer = AddCoOwnerSerializer(
            data={"user_id": 999},
            context={"resource": resource},
        )
        self.assertFalse(serializer.is_valid())
        self.assertIn("user_id", serializer.errors)

    @patch("permissions.co_owner_serializers.User.objects")
    @patch("permissions.co_owner_serializers.OrganizationMember.objects")
    @patch("permissions.co_owner_serializers.UserContext.get_organization")
    def test_cannot_add_creator_as_co_owner(
        self, mock_get_org: Mock, mock_org_member: Mock, mock_user_objects: Mock
    ) -> None:
        creator = Mock()
        creator.id = 1

        mock_get_org.return_value = Mock()
        mock_org_member.filter.return_value.exists.return_value = True
        mock_user_objects.get.return_value = creator

        resource = make_resource_mock(creator)
        # Creator is already in co_owners
        resource.co_owners.filter.return_value.exists.return_value = True

        serializer = AddCoOwnerSerializer(
            data={"user_id": 1},
            context={"resource": resource},
        )
        self.assertFalse(serializer.is_valid())
        self.assertIn("user_id", serializer.errors)

    @patch("permissions.co_owner_serializers.User.objects")
    @patch("permissions.co_owner_serializers.OrganizationMember.objects")
    @patch("permissions.co_owner_serializers.UserContext.get_organization")
    def test_cannot_add_existing_co_owner(
        self, mock_get_org: Mock, mock_org_member: Mock, mock_user_objects: Mock
    ) -> None:
        creator = Mock()
        existing_co_owner = Mock()
        existing_co_owner.id = 99

        mock_get_org.return_value = Mock()
        mock_org_member.filter.return_value.exists.return_value = True
        mock_user_objects.get.return_value = existing_co_owner

        resource = make_resource_mock(creator)
        # Already a co-owner
        resource.co_owners.filter.return_value.exists.return_value = True

        serializer = AddCoOwnerSerializer(
            data={"user_id": 99},
            context={"resource": resource},
        )
        self.assertFalse(serializer.is_valid())
        self.assertIn("user_id", serializer.errors)

    @patch("permissions.co_owner_serializers.User.objects")
    @patch("permissions.co_owner_serializers.OrganizationMember.objects")
    @patch("permissions.co_owner_serializers.UserContext.get_organization")
    def test_save_adds_co_owner(
        self, mock_get_org: Mock, mock_org_member: Mock, mock_user_objects: Mock
    ) -> None:
        creator = Mock()
        new_user = Mock()
        new_user.id = 77

        mock_get_org.return_value = Mock()
        mock_org_member.filter.return_value.exists.return_value = True
        mock_user_objects.get.return_value = new_user

        resource = make_resource_mock(creator)

        serializer = AddCoOwnerSerializer(
            data={"user_id": 77},
            context={"resource": resource},
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()

        resource.co_owners.add.assert_called_once_with(new_user)


class TestRemoveCoOwnerSerializer(TestCase):
    """Test RemoveCoOwnerSerializer validation and save logic."""

    def test_cannot_remove_last_owner(self) -> None:
        creator = Mock()
        resource = make_resource_mock(creator, co_owner_count=1)
        resource.co_owners.filter.return_value.exists.return_value = True

        serializer = RemoveCoOwnerSerializer(
            data={},
            context={"resource": resource, "user_to_remove": creator},
        )
        self.assertFalse(serializer.is_valid())

    def test_can_remove_co_owner_when_multiple_owners(self) -> None:
        creator = Mock()
        co_owner = Mock()
        co_owner.id = uuid4()

        resource = make_resource_mock(creator, co_owner_count=2)
        resource.co_owners.filter.return_value.exists.return_value = True

        serializer = RemoveCoOwnerSerializer(
            data={},
            context={"resource": resource, "user_to_remove": co_owner},
        )
        self.assertTrue(serializer.is_valid())

    def test_user_not_an_owner(self) -> None:
        creator = Mock()
        random_user = Mock()
        random_user.id = uuid4()

        resource = make_resource_mock(creator, co_owner_count=1)

        serializer = RemoveCoOwnerSerializer(
            data={},
            context={"resource": resource, "user_to_remove": random_user},
        )
        self.assertFalse(serializer.is_valid())

    def test_save_removes_co_owner(self) -> None:
        creator = Mock()
        co_owner = Mock()
        co_owner.id = uuid4()

        resource = make_resource_mock(creator, co_owner_count=2)
        resource.co_owners.filter.return_value.exists.return_value = True

        serializer = RemoveCoOwnerSerializer(
            data={},
            context={"resource": resource, "user_to_remove": co_owner},
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()

        resource.co_owners.remove.assert_called_once_with(co_owner)

    def test_save_removes_creator_without_promotion(self) -> None:
        """Removing creator just removes from co_owners, created_by is audit-only."""
        creator = Mock()
        co_owner = Mock()
        co_owner.id = uuid4()

        resource = make_resource_mock(creator, co_owner_count=2)
        resource.co_owners.filter.return_value.exists.return_value = True

        serializer = RemoveCoOwnerSerializer(
            data={},
            context={"resource": resource, "user_to_remove": creator},
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()

        resource.co_owners.remove.assert_called_once_with(creator)
        resource.save.assert_not_called()
