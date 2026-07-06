from __future__ import annotations

import re
import uuid as _uuid
from typing import TYPE_CHECKING

from account_v2.enums import UserRole
from account_v2.models import User
from django.apps import apps
from django.db import models, transaction
from tenant_account_v2.models import OrganizationMember

if TYPE_CHECKING:
    from account_v2.models import Organization

    from platform_api.models import PlatformApiKey

# Business app labels whose models may carry created_by / membership rows.
# Restricts transfer_ownership to avoid scanning Django built-in and third-party models.
_BUSINESS_APP_LABELS = {
    "adapter_processor_v2",
    "api_v2",
    "connector_v2",
    "pipeline_v2",
    "workflow_v2",
    "prompt_studio_core_v2",
    "prompt_studio_registry_v2",
    "agentic_studio_registry",
}


def _slugify_for_email(name: str) -> str:
    """Sanitize key name to RFC 5321-safe email local part."""
    slug = name.lower().replace(" ", "-")
    slug = re.sub(r"[^a-z0-9\-]", "", slug)
    return slug[:20] or "key"


def create_api_user_for_key(
    platform_api_key: PlatformApiKey, organization: Organization
) -> User:
    """Create a dedicated service account for bearer auth sessions."""
    with transaction.atomic():
        uid = str(_uuid.uuid4())
        name_slug = _slugify_for_email(platform_api_key.name)
        user = User(
            username=f"svc-{name_slug}-{uid[:8]}",
            email=f"{name_slug}-{uid[:8]}@platform.internal",
            user_id=uid,
            is_service_account=True,
        )
        user.set_unusable_password()
        user.save()

        OrganizationMember.objects.create(
            user=user,
            organization=organization,
            role=UserRole.USER.value,
        )

        platform_api_key.api_user = user
        platform_api_key.save(update_fields=["api_user"])
    return user


def _get_user_fk_fields(model: type) -> list[str]:
    """Return names of all ForeignKey fields pointing to User."""
    return [
        f.name
        for f in model._meta.get_fields()
        if isinstance(f, models.ForeignKey) and f.related_model is User
    ]


def _get_user_m2m_fields(model: type) -> list[str]:
    """Return names of ManyToMany-to-User fields safe to mutate via ``.add()``.

    Only auto-created (implicit) through tables qualify. A custom through model
    can't be mutated with ``.add()`` / ``.remove()``, so it is excluded — the
    sole such data (resource memberships, UN-2202) now lives in the polymorphic
    ``ResourceMembership`` table and is transferred by
    :func:`_transfer_membership_rows`.
    """
    return [
        f.name
        for f in model._meta.get_fields()
        if isinstance(f, models.ManyToManyField)
        and f.related_model is User
        and f.remote_field.through._meta.auto_created
    ]


def _transfer_model_ownership(model: type, from_user: User, to_user: User) -> None:
    """Transfer ownership for a single model from one user to another.

    Dynamically discovers all ForeignKey and ManyToMany fields pointing to
    User, so custom fields like workflow_owner are handled automatically.

    Uses _base_manager to bypass DefaultOrganizationManagerMixin which
    relies on UserContext (unavailable during signal/cleanup paths).
    """
    # Use _base_manager to bypass org-scoped default manager filtering.
    qs = model._base_manager.all()

    user_fk_fields = _get_user_fk_fields(model)
    user_m2m_fields = _get_user_m2m_fields(model)

    # Transfer all ForeignKey fields pointing to User
    for field_name in user_fk_fields:
        qs.filter(**{field_name: from_user}).update(**{field_name: to_user})

    # Transfer all ManyToMany fields pointing to User
    for field_name in user_m2m_fields:
        for instance in qs.filter(**{field_name: from_user}):
            getattr(instance, field_name).add(to_user)
            getattr(instance, field_name).remove(from_user)


def _transfer_membership_rows(from_user: User, to_user: User) -> None:
    """Re-point OWNER/VIEWER ``ResourceMembership`` rows across all resources.

    One polymorphic table covers every resource (UN-2202). ``unique_together
    (user, content_type, object_id)`` means a resource ``to_user`` already has
    a role on can't gain a second row — drop ``from_user``'s row there instead.
    """
    from tenant_account_v2.models import ResourceMembership

    held = set(
        ResourceMembership.objects.filter(user=to_user).values_list(
            "content_type_id", "object_id"
        )
    )
    for row in ResourceMembership.objects.filter(user=from_user):
        if (row.content_type_id, row.object_id) in held:
            row.delete()  # to_user already has a role on this resource
        else:
            row.user = to_user
            row.save(update_fields=["user"])


def transfer_ownership(from_user: User, to_user: User | None) -> None:
    """Transfer all resource ownership from one user to another.

    Replaces from_user with to_user across business models:
    - created_by / modified_by ForeignKey fields
    - auto-through ManyToMany fields to User
    - OWNER/VIEWER membership rows (custom-through, UN-2202) — re-pointed with
      ``unique_together`` dedup so a resource to_user already holds isn't
      duplicated.
    """
    if not to_user:
        return

    with transaction.atomic():
        for model in apps.get_models():
            if model._meta.app_label not in _BUSINESS_APP_LABELS:
                continue
            _transfer_model_ownership(model, from_user, to_user)
        # Memberships live in one polymorphic table — transfer once, not per model.
        _transfer_membership_rows(from_user, to_user)


def delete_api_user_for_key(platform_api_key: PlatformApiKey) -> None:
    """Transfer ownership to key creator, then delete the service account."""
    api_user = platform_api_key.api_user
    if not api_user:
        return

    with transaction.atomic():
        transfer_ownership(from_user=api_user, to_user=platform_api_key.created_by)
        api_user.delete()
