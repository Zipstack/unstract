from account_v2.session_views import (
    list_sessions,
    revoke_all_sessions,
    revoke_session,
)
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
        "patch": OrganizationUserViewSet.update_profile.__name__,
    }
)

user_profile_photo = OrganizationUserViewSet.as_view(
    {
        "get": OrganizationUserViewSet.get_profile_photo.__name__,
        "post": OrganizationUserViewSet.upload_profile_photo.__name__,
        "delete": OrganizationUserViewSet.delete_profile_photo.__name__,
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
    path("profile/photo/", user_profile_photo, name="user_profile_photo"),
    path("role/", organization_user_role, name="organization_user_role"),
    path("invite/", invite_user, name="invite_user"),
    path("sessions/", list_sessions, name="user_sessions"),
    path("sessions/revoke-all/", revoke_all_sessions, name="user_sessions_revoke_all"),
    path("sessions/<str:session_id>/", revoke_session, name="user_session"),
]
