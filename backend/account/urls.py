from account.views import (
    callback,
    create_organization,
    get_organizations,
    get_session_data,
    login,
    logout,
    set_organization,
    signup,
)
from django.urls import path
from django.utils.decorators import method_decorator
from django.db import transaction

urlpatterns = [
    path("login", login, name="login"),
    path("signup", signup, name="signup"),
    path("logout", logout, name="logout"),
    path("callback", callback, name="callback"),
    path("session", get_session_data, name="session"),
    path("organization", get_organizations, name="get_organizations"),
    path("organization/<str:id>/set",
        method_decorator(transaction.non_atomic_requests)
            (
                set_organization
            ), 
        name="set_organization"
        ),
    path("organization/create", create_organization, name="create_organization"),
]
