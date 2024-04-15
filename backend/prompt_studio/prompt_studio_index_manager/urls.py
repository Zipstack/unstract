from django.urls import path
from rest_framework.urlpatterns import format_suffix_patterns

from .views import IndexManagerView

prompt_studio_index_list = IndexManagerView.as_view({"get": "list", "post": "create"})

prompt_studio_index_detail = IndexManagerView.as_view(
    {
        "get": "retrieve",
    }
)

urlpatterns = format_suffix_patterns(
    [
        path(
            "document-index/",
            prompt_studio_index_list,
            name="prompt-studio-documents-list",
        ),
    ]
)
