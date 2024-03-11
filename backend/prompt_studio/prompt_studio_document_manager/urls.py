from django.urls import path
from rest_framework.urlpatterns import format_suffix_patterns

from .views import PromptStudioDocumentManagerView

prompt_studio_documents_list = PromptStudioDocumentManagerView.as_view(
    {"get": "list", "post": "create"}
)

prompt_studio_documents_detail = PromptStudioDocumentManagerView.as_view(
    {
        "get": "retrieve",
        "put": "update",
        "patch": "partial_update",
        "delete": "destroy",
    }
)

urlpatterns = format_suffix_patterns(
    [
        path(
            "prompt-document/",
            prompt_studio_documents_list,
            name="prompt-studio-documents-list",
        ),
        path(
            "prompt-document/<uuid:pk>/",
            prompt_studio_documents_detail,
            name="tool-studio-documents-detail",
        ),
    ]
)
