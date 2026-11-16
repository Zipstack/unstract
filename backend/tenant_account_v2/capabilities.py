"""Organisation capability permissions (UN-4399).

An org admin decides, per capability, whether any member or only admins may
use it. Each setting is a ``restrict_<...>`` boolean on ``Organization``
(True = admins only); the two legacy controlled-mode flags are the storage for
the first two capabilities, so ``organization/settings`` and
``organization/capabilities/`` stay in step by construction.

Service accounts (platform API keys) are never subject to a capability
setting. For the three creation capabilities and resource deletion, the
setting only narrows: each endpoint's own rules (ownership, key permission levels)
still apply on top. The three formerly admin-only areas (members, API keys,
platform defaults) are the exception: ``opened_to_members`` admits members to
them, with the limits each endpoint sets; see CAPABILITIES.md.
"""

from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from account_v2.models import Organization
from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import BasePermission
from utils.user_context import UserContext

from tenant_account_v2.organization_member_service import OrganizationMemberService


class Capability(StrEnum):
    """In the design's order."""

    CREATE_LLM_ADAPTERS = "create_llm_adapters"
    CREATE_CONNECTORS = "create_connectors"
    CREATE_OTHER_ADAPTERS = "create_other_adapters"
    MANAGE_API_KEYS = "manage_api_keys"
    MANAGE_MEMBERS = "manage_members"
    CHANGE_PLATFORM_DEFAULTS = "change_platform_defaults"
    DELETE_WORKFLOWS_AND_DEPLOYMENTS = "delete_workflows_and_deployments"


class CapabilitySetting(StrEnum):
    ADMINS_ONLY = "admins_only"
    ANY_MEMBER = "any_member"


# The serializers' choices, and the targets of the schema's enum-name overrides
# (drf-spectacular matches overrides on the choice set, not on the Enum).
CAPABILITY_KEY_VALUES = [capability.value for capability in Capability]
CAPABILITY_SETTING_VALUES = [setting.value for setting in CapabilitySetting]


@dataclass(frozen=True)
class CapabilitySpec:
    key: Capability
    label: str
    description: str
    field: str  # the Organization BooleanField; True means admins only
    # False while the endpoints that the capability governs do not enforce
    # it yet; such a capability can only be "admins_only" (today's behaviour).
    enforced: bool
    # A refusal's message. Legacy capabilities keep their existing wording so
    # existing responses do not change.
    denied_message: str = ""

    def message(self) -> str:
        return self.denied_message or (
            f"{self.label} is restricted to organisation admins."
        )


SPECS: tuple[CapabilitySpec, ...] = (
    CapabilitySpec(
        Capability.CREATE_LLM_ADAPTERS,
        "Create LLM adapters",
        "Add new LLM provider connections.",
        "restrict_llm_adapter_creation",
        enforced=True,
        denied_message=(
            "LLM adapter creation is restricted to organization admins. "
            "Please contact your organization admin."
        ),
    ),
    CapabilitySpec(
        Capability.CREATE_CONNECTORS,
        "Create connectors",
        "Add new source and destination connectors.",
        "restrict_connector_creation",
        enforced=True,
        denied_message=(
            "Connector creation is restricted to organization admins. "
            "Please contact your organization admin."
        ),
    ),
    CapabilitySpec(
        Capability.CREATE_OTHER_ADAPTERS,
        "Create other adapters",
        "Add embedding, vector database, text extractor and OCR adapters.",
        "restrict_other_adapter_creation",
        enforced=True,
    ),
    CapabilitySpec(
        Capability.MANAGE_API_KEYS,
        "Manage API keys",
        "Create global deployment keys for deployments they own, and "
        "view or rotate the keys they created. Platform API keys stay "
        "admin-only.",
        "restrict_api_key_management",
        enforced=True,
    ),
    CapabilitySpec(
        Capability.MANAGE_MEMBERS,
        "Manage members",
        "Invite members with the user role.",
        "restrict_member_management",
        enforced=True,
    ),
    CapabilitySpec(
        Capability.CHANGE_PLATFORM_DEFAULTS,
        "Change platform defaults",
        "Change the organisation's notification settings.",
        "restrict_platform_defaults",
        enforced=True,
    ),
    CapabilitySpec(
        Capability.DELETE_WORKFLOWS_AND_DEPLOYMENTS,
        "Delete workflows and deployments",
        "Delete workflows, API deployments and pipelines the member owns.",
        "restrict_resource_deletion",
        enforced=True,
    ),
)

SPECS_BY_KEY: dict[str, CapabilitySpec] = {spec.key.value: spec for spec in SPECS}


def setting_of(organization: Organization, spec: CapabilitySpec) -> CapabilitySetting:
    if getattr(organization, spec.field):
        return CapabilitySetting.ADMINS_ONLY
    return CapabilitySetting.ANY_MEMBER


def is_allowed(user: Any, organization: Organization | None, key: Capability) -> bool:
    """Whether the setting lets ``user`` use the capability.

    It says only that the setting does not block them: the endpoint's own
    rules (for example, deleting needs ownership) still apply on top.
    """
    spec = SPECS_BY_KEY[key]
    if getattr(user, "is_service_account", False) or organization is None:
        return True
    if setting_of(organization, spec) == CapabilitySetting.ANY_MEMBER:
        return True
    return OrganizationMemberService.is_user_organization_admin(user)


def opened_to_members(
    user: Any, organization: Organization | None, key: Capability
) -> bool:
    """Whether ``key`` admits ``user`` though they are not an admin.

    For the capabilities whose endpoints were admin-only (API keys, members,
    platform defaults): the caller's admin check stays, and this is the only
    way past it. Service accounts never qualify; those endpoints refused them
    before and still do.
    """
    if getattr(user, "is_service_account", False) or organization is None:
        return False
    return setting_of(organization, SPECS_BY_KEY[key]) == CapabilitySetting.ANY_MEMBER


def enforce_capability(request: Any, key: Capability) -> None:
    """Raise ``PermissionDenied`` when the org restricts ``key`` to admins and
    the caller is not one.
    """
    if not is_allowed(request.user, UserContext.get_organization(), key):
        raise PermissionDenied(SPECS_BY_KEY[key].message())


class RequiresCapability(BasePermission):
    """A DRF permission that applies ``enforce_capability`` for one key.

    Use it beside an endpoint's existing permission classes; it narrows, never
    widens, what they allow.
    """

    def __init__(self, key: Capability) -> None:
        self.key = key

    def has_permission(self, request: Any, view: Any) -> bool:
        enforce_capability(request, self.key)
        return True
