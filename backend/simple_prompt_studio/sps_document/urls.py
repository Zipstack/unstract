from django.urls import path
from rest_framework.urlpatterns import format_suffix_patterns

from .views import SPSDocumentView

sps_document_detail = SPSDocumentView.as_view(
    {
        "get": "retrieve",
        "patch": "partial_update",
        "delete": "destroy",
    }
)

sps_document_list = SPSDocumentView.as_view(
    {
        "get": "list",
        "post": "create",
    }
)

sps_document_upload = SPSDocumentView.as_view(
    {
        "post": "upload_documents",
        "get": "fetch_contents_ide",
    }
)

urlpatterns = format_suffix_patterns(
    [
        path(
            "documents/<uuid:pk>",
            sps_document_detail,
            name="spsdocument-detail",
        ),
        path(
            "documents",
            sps_document_list,
            name="spsdocument-list",
        ),
        path("documents/file", sps_document_upload, name="spsdocument-upload"),
    ]
)
