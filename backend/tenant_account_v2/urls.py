from django.urls import include, path

from tenant_account_v2 import invitation_urls, users_urls
from tenant_account_v2.views import get_organization, get_roles, reset_password

urlpatterns = [
    path("roles", get_roles, name="roles"),
    path("users/", include(users_urls)),
    path("invitation/", include(invitation_urls)),
    path("organization", get_organization, name="get_organization"),
    path("reset_password", reset_password, name="reset_password"),
]
