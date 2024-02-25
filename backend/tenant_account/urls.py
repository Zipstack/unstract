from django.urls import include, path
from tenant_account import invitation_urls, users_urls
from tenant_account.views import get_organization, get_roles, reset_password

urlpatterns = [
    path("roles", get_roles, name="roles"),
    path("users/", include(users_urls)),
    path("invitation/", include(invitation_urls)),
    path("organization", get_organization, name="get_organization"),
    path("reset_password", reset_password, name="reset_password"),
]
