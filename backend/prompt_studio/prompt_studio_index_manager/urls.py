from django.urls import path
from rest_framework.urlpatterns import format_suffix_patterns

from .views import IndexManagerView

prompt_studio_index_list = IndexManagerView.as_view({"get": "list", "post": "create"})

prompt_studio_index_detail = IndexManagerView.as_view(
    {
        "get": "retrieve",
    }
)
prompt_studio_index_data = IndexManagerView.as_view({"get": "get_indexed_data_for_profile"})

urlpatterns = format_suffix_patterns(
    [
        path(
            "document-index/",
            prompt_studio_index_list,
            name="prompt-studio-documents-list",
        ),
        path(
            "indexed-result/",
            prompt_studio_index_data,
            name="prompt-studio-indexed-list",
        ),
    ]
)
