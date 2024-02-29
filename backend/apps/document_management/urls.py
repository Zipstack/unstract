from apps.document_management.views import DocumentView
from django.urls import path
from rest_framework.urlpatterns import format_suffix_patterns

list_files = DocumentView.as_view({"get": "list_files"})
get_file = DocumentView.as_view({"get": "get_file"})


urlpatterns = format_suffix_patterns(
    [
        path("list_files/", list_files, name="list_files"),
        path("get_file/", get_file, name="get_file"),
    ]
)
