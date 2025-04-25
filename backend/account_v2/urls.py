from django.urls import path

from account_v2.views import (
    callback,
    create_organization,
    get_organizations,
    get_session_data,
    login,
    logout,
    set_organization,
    signup,
)

urlpatterns = [
    path("login", login, name="login"),
    path("signup", signup, name="signup"),
    path("logout", logout, name="logout"),
    path("callback", callback, name="callback"),
    path("session", get_session_data, name="session"),
    path("organization", get_organizations, name="get_organizations"),
    path("organization/<str:id>/set", set_organization, name="set_organization"),
    path("organization/create", create_organization, name="create_organization"),
]
