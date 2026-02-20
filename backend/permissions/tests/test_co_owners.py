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


class TestIsOwnerPermission(TestCase):
    """Test the IsOwner permission class recognizes co-owners."""

    def setUp(self) -> None:
        self.factory = RequestFactory()
        self.permission = IsOwner()

        self.creator = Mock()
        self.creator.pk = uuid4()

        self.co_owner = Mock()
        self.co_owner.pk = uuid4()

        self.other_user = Mock()
        self.other_user.pk = uuid4()

        # Build a mock resource with co_owners
        self.resource = Mock()
        self.resource.created_by = self.creator
        co_owners_qs = MagicMock()
        co_owners_qs.filter.return_value.exists.return_value = False
        self.resource.co_owners = co_owners_qs

    def _make_request(self, user: Mock) -> Mock:
        request = self.factory.get("/fake/")
        request.user = user
        return request

    def test_creator_has_permission(self) -> None:
        request = self._make_request(self.creator)
        self.assertTrue(
            self.permission.has_object_permission(request, None, self.resource)
        )

    def test_co_owner_has_permission(self) -> None:
        # Make co_owners.filter(...).exists() return True for co_owner
        def filter_side_effect(**kwargs: object) -> Mock:
            mock_qs = Mock()
            mock_qs.exists.return_value = kwargs.get("pk") == self.co_owner.pk
            return mock_qs

        self.resource.co_owners.filter.side_effect = filter_side_effect

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


class TestIsOwnerOrSharedUserPermission(TestCase):
    """Test IsOwnerOrSharedUser recognizes co-owners."""

    def setUp(self) -> None:
        self.factory = RequestFactory()
        self.permission = IsOwnerOrSharedUser()

        self.creator = Mock()
        self.creator.pk = uuid4()

        self.co_owner = Mock()
        self.co_owner.pk = uuid4()

        self.shared_user = Mock()
        self.shared_user.pk = uuid4()

        self.other_user = Mock()
        self.other_user.pk = uuid4()

        self.resource = Mock()
        self.resource.created_by = self.creator

        # Default: no matches
        co_owners_qs = MagicMock()
        co_owners_qs.filter.return_value.exists.return_value = False
        self.resource.co_owners = co_owners_qs

        shared_users_qs = MagicMock()
        shared_users_qs.filter.return_value.exists.return_value = False
        self.resource.shared_users = shared_users_qs

    def _make_request(self, user: Mock) -> Mock:
        request = self.factory.get("/fake/")
        request.user = user
        return request

    def test_co_owner_has_permission(self) -> None:
        def filter_side_effect(**kwargs: object) -> Mock:
            mock_qs = Mock()
            mock_qs.exists.return_value = kwargs.get("pk") == self.co_owner.pk
            return mock_qs

        self.resource.co_owners.filter.side_effect = filter_side_effect

        request = self._make_request(self.co_owner)
        self.assertTrue(
            self.permission.has_object_permission(request, None, self.resource)
        )

    def test_shared_user_has_permission(self) -> None:
        def filter_side_effect(**kwargs: object) -> Mock:
            mock_qs = Mock()
            mock_qs.exists.return_value = kwargs.get("pk") == self.shared_user.pk
            return mock_qs

        self.resource.shared_users.filter.side_effect = filter_side_effect

        request = self._make_request(self.shared_user)
        self.assertTrue(
            self.permission.has_object_permission(request, None, self.resource)
        )

    def test_other_user_denied(self) -> None:
        request = self._make_request(self.other_user)
        self.assertFalse(
            self.permission.has_object_permission(request, None, self.resource)
        )


class TestIsOwnerOrSharedUserOrSharedToOrgPermission(TestCase):
    """Test IsOwnerOrSharedUserOrSharedToOrg recognizes co-owners."""

    def setUp(self) -> None:
        self.factory = RequestFactory()
        self.permission = IsOwnerOrSharedUserOrSharedToOrg()

        self.creator = Mock()
        self.creator.pk = uuid4()

        self.co_owner = Mock()
        self.co_owner.pk = uuid4()

        self.other_user = Mock()
        self.other_user.pk = uuid4()

        self.resource = Mock()
        self.resource.created_by = self.creator
        self.resource.shared_to_org = False

        co_owners_qs = MagicMock()
        co_owners_qs.filter.return_value.exists.return_value = False
        self.resource.co_owners = co_owners_qs

        shared_users_qs = MagicMock()
        shared_users_qs.filter.return_value.exists.return_value = False
        self.resource.shared_users = shared_users_qs

    def _make_request(self, user: Mock) -> Mock:
        request = self.factory.get("/fake/")
        request.user = user
        return request

    def test_co_owner_has_permission(self) -> None:
        def filter_side_effect(**kwargs: object) -> Mock:
            mock_qs = Mock()
            mock_qs.exists.return_value = kwargs.get("pk") == self.co_owner.pk
            return mock_qs

        self.resource.co_owners.filter.side_effect = filter_side_effect

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

    def _make_resource(self, creator: Mock) -> Mock:
        resource = Mock()
        resource.created_by = creator
        co_owners_qs = MagicMock()
        co_owners_qs.filter.return_value.exists.return_value = False
        resource.co_owners = co_owners_qs
        return resource

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

        resource = self._make_resource(creator)

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

        resource = self._make_resource(creator)

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

        resource = self._make_resource(creator)
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

        resource = self._make_resource(creator)
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

        resource = self._make_resource(creator)

        serializer = AddCoOwnerSerializer(
            data={"user_id": 77},
            context={"resource": resource},
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()

        resource.co_owners.add.assert_called_once_with(new_user)


class TestRemoveCoOwnerSerializer(TestCase):
    """Test RemoveCoOwnerSerializer validation and save logic."""

    def _make_resource(self, creator: Mock, co_owner_count: int = 1) -> Mock:
        resource = Mock()
        resource.created_by = creator

        co_owners_qs = MagicMock()
        co_owners_qs.count.return_value = co_owner_count
        co_owners_qs.filter.return_value.exists.return_value = False
        resource.co_owners = co_owners_qs

        return resource

    def test_cannot_remove_last_owner(self) -> None:
        creator = Mock()
        # Creator is the only co-owner (count=1)
        resource = self._make_resource(creator, co_owner_count=1)
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

        # Both creator and co_owner are in co_owners (count=2)
        resource = self._make_resource(creator, co_owner_count=2)
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

        resource = self._make_resource(creator, co_owner_count=1)
        # random_user is not in co_owners

        serializer = RemoveCoOwnerSerializer(
            data={},
            context={"resource": resource, "user_to_remove": random_user},
        )
        self.assertFalse(serializer.is_valid())

    def test_save_removes_co_owner(self) -> None:
        creator = Mock()
        co_owner = Mock()
        co_owner.id = uuid4()

        # Both creator and co_owner in co_owners (count=2)
        resource = self._make_resource(creator, co_owner_count=2)
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

        # Both creator and co_owner in co_owners (count=2)
        resource = self._make_resource(creator, co_owner_count=2)
        resource.co_owners.filter.return_value.exists.return_value = True

        serializer = RemoveCoOwnerSerializer(
            data={},
            context={"resource": resource, "user_to_remove": creator},
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()

        # Should just remove from co_owners, no creator promotion
        resource.co_owners.remove.assert_called_once_with(creator)
        resource.save.assert_not_called()
