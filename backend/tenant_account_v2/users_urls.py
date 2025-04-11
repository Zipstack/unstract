from django.urls import path

from tenant_account_v2.users_view import OrganizationUserViewSet

organization_user_role = OrganizationUserViewSet.as_view(
    {
        "post": OrganizationUserViewSet.assign_organization_role_to_user.__name__,
        "delete": OrganizationUserViewSet.remove_organization_role_from_user.__name__,
    }
)

user_profile = OrganizationUserViewSet.as_view(
    {
        "get": OrganizationUserViewSet.get_user_profile.__name__,
        "put": OrganizationUserViewSet.update_flags.__name__,
    }
)

invite_user = OrganizationUserViewSet.as_view(
    {
        "post": OrganizationUserViewSet.invite_user.__name__,
    }
)

organization_users = OrganizationUserViewSet.as_view(
    {
        "get": OrganizationUserViewSet.get_organization_members.__name__,
        "delete": OrganizationUserViewSet.remove_members_from_organization.__name__,
    }
)


urlpatterns = [
    path("", organization_users, name="organization_user"),
    path("profile/", user_profile, name="user_profile"),
    path("role/", organization_user_role, name="organization_user_role"),
    path("invite/", invite_user, name="invite_user"),
]
