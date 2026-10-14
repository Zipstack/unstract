"""The platform audit action vocabulary.

Every event carries an action key from this registry. The read API serves it
(``GET platform/audit/actions/``) so the Audit log tab can label rows and build
its "Any action" filter without hard-coding the list, and the recorder refuses
a key that is not registered, so a typo is logged rather than stored.

OSS registers every action the Frontend v1 spec names, including the ones other
tasks emit (``capability.changed``, ``key.expiry_set``, ``execution.aborted``).
Cloud code registers its own from ``AppConfig.ready``::

    from platform_audit.actions import register_action

    register_action("review_key.created", "Review key created", "keys")
"""

from dataclasses import dataclass
from enum import StrEnum


@dataclass(frozen=True)
class AuditAction:
    key: str
    label: str
    category: str


class ActionCategory(StrEnum):
    MEMBERS = "members"
    GROUPS = "groups"
    KEYS = "keys"
    DEFAULTS = "defaults"
    SETTINGS = "settings"
    CAPABILITIES = "capabilities"
    EXECUTIONS = "executions"


class TargetType(StrEnum):
    """Known ``target_type`` values. Emitters may add their own."""

    MEMBER = "member"
    INVITATION = "invitation"
    GROUP = "group"
    PLATFORM_API_KEY = "platform_api_key"
    GLOBAL_API_DEPLOYMENT_KEY = "global_api_deployment_key"
    PLATFORM_KEY = "platform_key"
    DEFAULT_PROFILE = "default_profile"
    PLATFORM_SETTING = "platform_setting"
    CAPABILITY = "capability"
    EXECUTION = "execution"


class Action(StrEnum):
    """Keys OSS registers. Emit these rather than string literals."""

    MEMBER_ROLE_CHANGED = "member.role_changed"
    MEMBER_INVITED = "member.invited"
    INVITATION_REVOKED = "invitation.revoked"
    MEMBER_REMOVED = "member.removed"
    GROUP_CREATED = "group.created"
    GROUP_CHANGED = "group.changed"
    GROUP_DELETED = "group.deleted"
    GROUP_MEMBER_ADDED = "group.member_added"
    GROUP_MEMBER_REMOVED = "group.member_removed"
    KEY_CREATED = "key.created"
    KEY_ROTATED = "key.rotated"
    KEY_REVOKED = "key.revoked"
    KEY_ENABLED = "key.enabled"
    KEY_DISABLED = "key.disabled"
    KEY_CHANGED = "key.changed"
    KEY_EXPIRY_SET = "key.expiry_set"
    DEFAULT_PROFILE_CHANGED = "default_profile.changed"
    PLATFORM_SETTING_CHANGED = "platform_setting.changed"
    CAPABILITY_CHANGED = "capability.changed"
    EXECUTION_ABORTED = "execution.aborted"


# The width of PlatformAuditEvent.action; a longer key could never be stored.
ACTION_KEY_MAX_LENGTH = 64

_REGISTRY: dict[str, AuditAction] = {}


def register_action(key: str, label: str, category: str) -> AuditAction:
    """Add an action to the vocabulary.

    Registering the same key twice with the same label and category is a
    no-op, so an ``AppConfig.ready`` that runs twice is harmless. Registering
    it with a different label or category raises, because two emitters would
    then disagree about what the key means.
    """
    action = AuditAction(key=str(key), label=label, category=str(category))
    if not action.key or len(action.key) > ACTION_KEY_MAX_LENGTH:
        raise ValueError(
            f"Audit action key must be 1-{ACTION_KEY_MAX_LENGTH} characters: "
            f"{action.key!r}"
        )
    existing = _REGISTRY.get(action.key)
    if existing is not None and existing != action:
        raise ValueError(
            f"Audit action {action.key!r} is already registered as {existing}."
        )
    _REGISTRY[action.key] = action
    return action


def get_action(key: str) -> AuditAction | None:
    return _REGISTRY.get(key)


def all_actions() -> list[AuditAction]:
    return sorted(_REGISTRY.values(), key=lambda a: (a.category, a.key))


for _key, _label, _category in (
    (Action.MEMBER_ROLE_CHANGED, "Role changed", ActionCategory.MEMBERS),
    (Action.MEMBER_INVITED, "Member invited", ActionCategory.MEMBERS),
    (Action.INVITATION_REVOKED, "Invitation revoked", ActionCategory.MEMBERS),
    (Action.MEMBER_REMOVED, "Member removed", ActionCategory.MEMBERS),
    (Action.GROUP_CREATED, "Group created", ActionCategory.GROUPS),
    (Action.GROUP_CHANGED, "Group changed", ActionCategory.GROUPS),
    (Action.GROUP_DELETED, "Group deleted", ActionCategory.GROUPS),
    (Action.GROUP_MEMBER_ADDED, "Added to group", ActionCategory.GROUPS),
    (Action.GROUP_MEMBER_REMOVED, "Removed from group", ActionCategory.GROUPS),
    (Action.KEY_CREATED, "Key created", ActionCategory.KEYS),
    (Action.KEY_ROTATED, "Key rotated", ActionCategory.KEYS),
    (Action.KEY_REVOKED, "Key revoked", ActionCategory.KEYS),
    (Action.KEY_ENABLED, "Key enabled", ActionCategory.KEYS),
    (Action.KEY_DISABLED, "Key disabled", ActionCategory.KEYS),
    (Action.KEY_CHANGED, "Key changed", ActionCategory.KEYS),
    (Action.KEY_EXPIRY_SET, "Key expiry set", ActionCategory.KEYS),
    (Action.DEFAULT_PROFILE_CHANGED, "Default changed", ActionCategory.DEFAULTS),
    (Action.PLATFORM_SETTING_CHANGED, "Setting changed", ActionCategory.SETTINGS),
    (Action.CAPABILITY_CHANGED, "Capability changed", ActionCategory.CAPABILITIES),
    (Action.EXECUTION_ABORTED, "Execution aborted", ActionCategory.EXECUTIONS),
):
    register_action(_key, _label, _category)
