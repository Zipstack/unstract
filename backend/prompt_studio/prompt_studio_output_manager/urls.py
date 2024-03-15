from django.urls import path
from rest_framework.urlpatterns import format_suffix_patterns

from .views import PromptStudioOutputView

prompt_doc_list = PromptStudioOutputView.as_view(
    {"get": "list", "post": "create"}
)
prompt_doc_detail = PromptStudioOutputView.as_view(
    {
        "get": "retrieve",
        "put": "update",
        "patch": "partial_update",
        "delete": "destroy",
    }
)

urlpatterns = format_suffix_patterns(
    [
        path("prompt-output/", prompt_doc_list, name="prompt-doc-list"),
        path(
            "prompt-output/<uuid:pk>/",
            prompt_doc_detail,
            name="prompt-doc-detail",
        ),
    ]
)
