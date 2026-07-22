"""Guard: a global API deployment key never authenticates another org's API.

``KeyHelper.validate_global_api_deployment_key`` looks a key up by ``key`` +
``is_active`` with **no organization filter**, so the org comparison inside
``GlobalApiDeploymentKey.has_access_to_deployment`` is the only thing standing
between a valid Org A key and an Org B deployment. These tests pin that guard,
the rest of the authorization matrix, and the deployment-key -> global-key
fallback ordering in ``DeploymentHelper.validate_api``.

No test database: every case runs on unsaved model instances with the M2M
descriptor and ``objects`` manager patched, mirroring the mock-collaborator
style of ``api_v2/tests/test_deployment_helper.py``.
"""

from __future__ import annotations

import os
from unittest import mock

import django
from django.apps import apps

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "backend.settings.test")
if not apps.ready:
    django.setup()

import pytest  # noqa: E402
from django.core.exceptions import ValidationError  # noqa: E402
from rest_framework.serializers import (  # noqa: E402
    ValidationError as DRFValidationError,
)

import api_v2.deployment_helper as dh  # noqa: E402
from api_v2.exceptions import APINotFound, InactiveAPI, UnauthorizedKey  # noqa: E402
from api_v2.key_helper import KeyHelper  # noqa: E402
from api_v2.models import APIDeployment  # noqa: E402
from api_v2.serializers import ExecutionRequestSerializer  # noqa: E402
from prompt_studio.prompt_profile_manager_v2.models import (  # noqa: E402
    ProfileManager,
)
from utils.user_context import UserContext  # noqa: E402
from global_api_deployment_key.models import GlobalApiDeploymentKey  # noqa: E402
from global_api_deployment_key.serializers import (  # noqa: E402
    GlobalApiDeploymentKeyUpdateSerializer,
)

ORG_A = 1
ORG_B = 2
# A syntactically valid UUID — the bearer value under test, not a real key.
WELL_FORMED_UUID = "3f1d9c4e-6b2a-4c8d-9e77-1a2b3c4d5e6f"


def _deployment(organization_id: int = ORG_A) -> APIDeployment:
    """An unsaved deployment; the auth path only reads id/org/is_active."""
    deployment = APIDeployment(api_name="my-api", is_active=True)
    deployment.id = "8c1f0b6a-0000-4000-8000-000000000001"
    deployment.organization_id = organization_id
    return deployment


def _key(
    *,
    organization_id: int = ORG_A,
    is_active: bool = True,
    allow_all: bool = False,
) -> GlobalApiDeploymentKey:
    key = GlobalApiDeploymentKey(
        name="prod-key",
        description="prod",
        is_active=is_active,
        allow_all_deployments=allow_all,
    )
    key.organization_id = organization_id
    return key


@pytest.fixture
def m2m():
    """Patch the ``api_deployments`` relation so no database is needed.

    ``ManyToManyDescriptor`` is a data descriptor, so it can only be shadowed on
    the class — hence ``PropertyMock`` rather than an instance attribute.
    """
    with mock.patch.object(
        GlobalApiDeploymentKey, "api_deployments", new_callable=mock.PropertyMock
    ) as prop:
        yield prop


@pytest.fixture
def no_org():
    """No organization in context.

    Org resolution is a DB read, and it runs inside the org-scoped model
    manager as well as the serializer, so it is patched on the class both share.
    """
    with mock.patch.object(UserContext, "get_organization", return_value=None):
        yield


def _scope(m2m, *, contains: bool) -> None:
    """Make the key's deployment list report whether it holds the deployment."""
    manager = mock.MagicMock()
    manager.filter.return_value.exists.return_value = contains
    m2m.return_value = manager


class TestHasAccessToDeployment:
    """The authorization matrix on the model."""

    def test_cross_org_key_is_rejected_even_when_allow_all(self, m2m) -> None:
        """The load-bearing tenant guard: Org A key, Org B deployment."""
        key = _key(organization_id=ORG_A, allow_all=True)
        assert key.has_access_to_deployment(_deployment(ORG_B)) is False

    def test_cross_org_key_is_rejected_when_scoped(self, m2m) -> None:
        """Org mismatch wins even if the M2M somehow lists the deployment."""
        _scope(m2m, contains=True)
        key = _key(organization_id=ORG_A, allow_all=False)
        assert key.has_access_to_deployment(_deployment(ORG_B)) is False

    def test_same_org_allow_all_authorizes(self, m2m) -> None:
        key = _key(organization_id=ORG_A, allow_all=True)
        assert key.has_access_to_deployment(_deployment(ORG_A)) is True

    def test_inactive_key_is_rejected(self, m2m) -> None:
        key = _key(organization_id=ORG_A, allow_all=True, is_active=False)
        assert key.has_access_to_deployment(_deployment(ORG_A)) is False

    def test_scoped_key_authorizes_listed_deployment(self, m2m) -> None:
        _scope(m2m, contains=True)
        key = _key(organization_id=ORG_A, allow_all=False)
        assert key.has_access_to_deployment(_deployment(ORG_A)) is True

    def test_scoped_key_rejects_unlisted_deployment(self, m2m) -> None:
        _scope(m2m, contains=False)
        key = _key(organization_id=ORG_A, allow_all=False)
        assert key.has_access_to_deployment(_deployment(ORG_A)) is False


class TestValidateGlobalApiDeploymentKey:
    """The lookup wrapper: what reaches the caller for each failure mode."""

    def test_unknown_key_raises_unauthorized(self) -> None:
        with mock.patch.object(GlobalApiDeploymentKey, "objects") as objects:
            objects.get.side_effect = GlobalApiDeploymentKey.DoesNotExist
            with pytest.raises(UnauthorizedKey):
                KeyHelper.validate_global_api_deployment_key(
                    api_key=WELL_FORMED_UUID, api_deployment=_deployment()
                )

    def test_malformed_key_raises_unauthorized_not_server_error(self) -> None:
        """A non-UUID bearer token must 401, not 500 — UUIDField coercion."""
        with mock.patch.object(GlobalApiDeploymentKey, "objects") as objects:
            objects.get.side_effect = ValidationError("badly formed UUID")
            with pytest.raises(UnauthorizedKey):
                KeyHelper.validate_global_api_deployment_key(
                    api_key="not-a-uuid", api_deployment=_deployment()
                )

    def test_out_of_scope_key_raises_unauthorized(self) -> None:
        key = mock.MagicMock()
        key.has_access_to_deployment.return_value = False
        with mock.patch.object(GlobalApiDeploymentKey, "objects") as objects:
            objects.get.return_value = key
            with pytest.raises(UnauthorizedKey):
                KeyHelper.validate_global_api_deployment_key(
                    api_key=WELL_FORMED_UUID, api_deployment=_deployment()
                )

    def test_authorized_key_is_returned_for_audit(self) -> None:
        key = mock.MagicMock()
        key.has_access_to_deployment.return_value = True
        with mock.patch.object(GlobalApiDeploymentKey, "objects") as objects:
            objects.get.return_value = key
            returned = KeyHelper.validate_global_api_deployment_key(
                api_key=WELL_FORMED_UUID, api_deployment=_deployment()
            )
        assert returned is key
        # Inactive keys are excluded by the lookup itself, not a later check.
        objects.get.assert_called_once_with(key=WELL_FORMED_UUID, is_active=True)


class TestValidateApiFallbackOrdering:
    """Deployment-specific key first; the global key is strictly a fallback."""

    def test_missing_deployment_raises_api_not_found(self) -> None:
        with pytest.raises(APINotFound):
            dh.DeploymentHelper.validate_api(api_deployment=None, api_key=WELL_FORMED_UUID)

    def test_inactive_deployment_raises_inactive_api(self) -> None:
        deployment = _deployment()
        deployment.is_active = False
        with pytest.raises(InactiveAPI):
            dh.DeploymentHelper.validate_api(
                api_deployment=deployment, api_key=WELL_FORMED_UUID
            )

    def test_valid_deployment_key_never_hits_global_lookup(self) -> None:
        with mock.patch.object(dh, "KeyHelper") as key_helper:
            key_helper.validate_api_key.return_value = None
            result = dh.DeploymentHelper.validate_api(
                api_deployment=_deployment(), api_key=WELL_FORMED_UUID
            )
            key_helper.validate_global_api_deployment_key.assert_not_called()
        assert result is None

    def test_falls_back_to_global_key_and_returns_it(self) -> None:
        global_key = mock.MagicMock()
        with mock.patch.object(dh, "KeyHelper") as key_helper:
            key_helper.validate_api_key.side_effect = UnauthorizedKey
            key_helper.validate_global_api_deployment_key.return_value = global_key
            result = dh.DeploymentHelper.validate_api(
                api_deployment=_deployment(), api_key=WELL_FORMED_UUID
            )
        assert result is global_key

    def test_both_paths_failing_propagates_unauthorized(self) -> None:
        with mock.patch.object(dh, "KeyHelper") as key_helper:
            key_helper.validate_api_key.side_effect = UnauthorizedKey
            key_helper.validate_global_api_deployment_key.side_effect = UnauthorizedKey
            with pytest.raises(UnauthorizedKey):
                dh.DeploymentHelper.validate_api(
                    api_deployment=_deployment(), api_key=WELL_FORMED_UUID
                )


class TestGlobalKeyLlmProfileScoping:
    """``llm_profile_id`` must stay org-scoped when a global key is used.

    The per-user ownership check that guards deployment-specific keys cannot
    apply to an org-level key, so the organization comparison in
    ``ExecutionRequestSerializer.validate_llm_profile_id`` is what stops a
    caller referencing another org's profile by UUID.
    """

    PROFILE_ID = "b7c2f1de-0000-4000-8000-000000000002"

    def _serializer(self, organization_id: int = ORG_A):
        return ExecutionRequestSerializer(
            context={
                "api": _deployment(organization_id),
                "api_key": WELL_FORMED_UUID,
                "is_global_key": True,
            }
        )

    def _profile(self, organization_id: int | None) -> mock.MagicMock:
        profile = mock.MagicMock()
        profile.prompt_studio_tool_id = (
            None if organization_id is None else "tool-id"
        )
        profile.prompt_studio_tool.organization_id = organization_id
        return profile

    def test_same_org_profile_is_accepted(self) -> None:
        with mock.patch.object(ProfileManager, "objects") as objects:
            objects.get.return_value = self._profile(ORG_A)
            assert (
                self._serializer().validate_llm_profile_id(self.PROFILE_ID)
                == self.PROFILE_ID
            )

    def test_cross_org_profile_is_rejected(self) -> None:
        with mock.patch.object(ProfileManager, "objects") as objects:
            objects.get.return_value = self._profile(ORG_B)
            with pytest.raises(DRFValidationError, match="Profile not found"):
                self._serializer().validate_llm_profile_id(self.PROFILE_ID)

    def test_profile_without_a_tool_fails_closed(self) -> None:
        """No prompt studio tool means no derivable org — reject, don't guess."""
        with mock.patch.object(ProfileManager, "objects") as objects:
            objects.get.return_value = self._profile(None)
            with pytest.raises(DRFValidationError, match="Profile not found"):
                self._serializer().validate_llm_profile_id(self.PROFILE_ID)

    def test_unknown_profile_is_rejected(self) -> None:
        with mock.patch.object(ProfileManager, "objects") as objects:
            objects.get.side_effect = ProfileManager.DoesNotExist
            with pytest.raises(DRFValidationError, match="Profile not found"):
                self._serializer().validate_llm_profile_id(self.PROFILE_ID)


class TestUpdateSerializerScopeValidation:
    """PATCH must not trap callers into an unrepresentable scope.

    Updates are partial, so the effective scope is a mix of payload and stored
    state. These pin the two cases where validating the stored list would
    reject a legitimate request.
    """

    def _serializer(self, instance, data):
        return GlobalApiDeploymentKeyUpdateSerializer(instance, data=data, partial=True)

    def test_flipping_a_scoped_key_to_allow_all_clears_the_list(
        self, m2m, no_org
    ) -> None:
        """PATCH {"allow_all_deployments": true} alone must succeed."""
        _scope(m2m, contains=True)
        instance = _key(allow_all=False)
        serializer = self._serializer(instance, {"allow_all_deployments": True})
        assert serializer.is_valid(), serializer.errors
        # Cleared, so the stored list can't misrepresent what the key reaches.
        assert serializer.validated_data["api_deployments"] == []

    def test_key_stranded_by_a_deleted_deployment_stays_deactivatable(
        self, m2m, no_org
    ) -> None:
        """Its only deployment was deleted; deactivating it must still work."""
        m2m.return_value.exists.return_value = False
        instance = _key(allow_all=False)
        serializer = self._serializer(instance, {"is_active": False})
        assert serializer.is_valid(), serializer.errors

    def test_turning_allow_all_off_without_deployments_is_rejected(
        self, m2m, no_org
    ) -> None:
        m2m.return_value.exists.return_value = False
        instance = _key(allow_all=True)
        serializer = self._serializer(instance, {"allow_all_deployments": False})
        assert not serializer.is_valid()
        assert "api_deployments" in serializer.errors
