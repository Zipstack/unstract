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

sps_index_document = SPSProjectView.as_view(
    {
        "post": "index_document_sps",
    }
)

sps_fetch_response = SPSProjectView.as_view(
    {
        "post": "fetch_response_sps",
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
        path("index", sps_index_document, name="spsdocument-index"),
        path("fetch", sps_fetch_response, name="spsfetch-response"),
    ]
)
