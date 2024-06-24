from django.urls import path
from rest_framework.urlpatterns import format_suffix_patterns

from .views import SPSProjectView

sps_project_detail = SPSProjectView.as_view(
    {
        "get": "retrieve",
        "patch": "partial_update",
        "delete": "destroy",
    }
)

sps_project_list = SPSProjectView.as_view(
    {
        "get": "list",
        "post": "create",
    }
)

urlpatterns = format_suffix_patterns(
    [
        path(
            "<uuid:pk>",
            sps_project_detail,
            name="spsproject-detail",
        ),
        path(
            "",
            sps_project_list,
            name="spsproject-list",
        ),
    ]
)
