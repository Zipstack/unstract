from apps import views
from django.urls import path
from rest_framework.urlpatterns import format_suffix_patterns

urlpatterns = format_suffix_patterns(
    [
        path("app/", views.get_app_list, name="app-list"),
    ]
)
