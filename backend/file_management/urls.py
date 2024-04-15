from django.urls import path
from rest_framework.urlpatterns import format_suffix_patterns

from .views import FileManagementViewSet

file_list = FileManagementViewSet.as_view(
    {
        "get": "list",
    }
)
file_downlaod = FileManagementViewSet.as_view(
    {
        "get": "download",
    }
)

file_upload = FileManagementViewSet.as_view(
    {
        "post": "upload",
    }
)
prompt_studio_file_upload = FileManagementViewSet.as_view(
    {
        "post": "upload_for_ide",
    }
)
prompt_studio_fetch_content = FileManagementViewSet.as_view(
    {
        "get": "fetch_contents_ide",
    }
)
prompt_studio_file_list = FileManagementViewSet.as_view(
    {
        "get": "list_ide",
    }
)
file_delete = FileManagementViewSet.as_view(
    {
        "get": "delete",
    }
)
urlpatterns = format_suffix_patterns(
    [
        path("file", file_list, name="file-list"),
        path("file/download", file_downlaod, name="download"),
        path("file/upload", file_upload, name="upload"),
        path("file/delete", file_delete, name="delete"),
    ]
)
