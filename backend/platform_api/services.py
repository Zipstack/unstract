from account_v2.enums import UserRole
from account_v2.models import User
from tenant_account_v2.models import OrganizationMember


def create_api_user_for_key(platform_api_key, organization):
    """Create a dedicated dummy user for bearer auth sessions."""
    key_id = str(platform_api_key.id)
    user = User(
        username=f"api-key-{key_id}",
        email=f"api-key-{key_id}@platform.internal",
        user_id=f"api-key-{key_id}",
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


def delete_api_user_for_key(platform_api_key):
    """Delete the dummy user when a key is deleted."""
    if platform_api_key.api_user:
        platform_api_key.api_user.delete()  # Cascades OrganizationMember
