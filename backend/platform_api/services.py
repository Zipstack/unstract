from account_v2.enums import UserRole
from account_v2.models import User
from django.apps import apps
from tenant_account_v2.models import OrganizationMember


def create_api_user_for_key(platform_api_key, organization):
    """Create a dedicated service account for bearer auth sessions."""
    import uuid as _uuid

    uid = str(_uuid.uuid4())
    name_slug = platform_api_key.name.lower().replace(" ", "-")[:20]
    short_uid = uid[-4:]
    user = User(
        username=f"svc-{name_slug}-{short_uid}",
        email=f"{name_slug}-{short_uid}@platform.internal",
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


def transfer_ownership(from_user, to_user):
    """Transfer all resource ownership from one user to another.

    Replaces from_user with to_user across:
    - created_by / modified_by ForeignKey fields
    - shared_users ManyToMany fields

    Also cleans up redundancy: if to_user becomes created_by (owner),
    they are removed from shared_users on that record since ownership
    already grants full access.
    """
    if not to_user:
        return

    for model in apps.get_models():
        has_created_by = hasattr(model, "created_by")
        has_shared_users = hasattr(model, "shared_users")

        if has_created_by:
            owned_pks = list(
                model.objects.filter(created_by=from_user).values_list("pk", flat=True)
            )
            model.objects.filter(pk__in=owned_pks).update(created_by=to_user)

            # Remove to_user from shared_users on records they now own
            if has_shared_users and owned_pks:
                for instance in model.objects.filter(
                    pk__in=owned_pks, shared_users=to_user
                ):
                    instance.shared_users.remove(to_user)

        if hasattr(model, "modified_by"):
            model.objects.filter(modified_by=from_user).update(modified_by=to_user)

        if has_shared_users:
            for instance in model.objects.filter(shared_users=from_user):
                instance.shared_users.add(to_user)
                instance.shared_users.remove(from_user)


def delete_api_user_for_key(platform_api_key):
    """Transfer ownership to key creator, then delete the service account."""
    api_user = platform_api_key.api_user
    if not api_user:
        return

    transfer_ownership(from_user=api_user, to_user=platform_api_key.created_by)
    api_user.delete()
