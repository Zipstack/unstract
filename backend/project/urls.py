from django.urls import path
from rest_framework.urlpatterns import format_suffix_patterns

from .views import ProjectViewSet

project_list = ProjectViewSet.as_view({"get": "list", "post": "create"})
project_detail = ProjectViewSet.as_view(
    {"get": "retrieve", "put": "update", "patch": "partial_update", "delete": "destroy"}
)

project_settings = ProjectViewSet.as_view(
    {"get": "project_settings", "put": "project_settings"}
)
project_settings_schema = ProjectViewSet.as_view({"get": "project_settings_schema"})

urlpatterns = format_suffix_patterns(
    [
        path("projects/", project_list, name="projects-list"),
        path("projects/<uuid:pk>/", project_detail, name="projects-detail"),
        path("projects/<uuid:pk>/settings/", project_settings, name="project-settings"),
        path(
            "projects/settings/",
            project_settings_schema,
            name="project-settings-schema",
        ),
    ]
)
