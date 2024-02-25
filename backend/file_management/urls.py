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
        path(
            "prompt-studio/file/upload",
            prompt_studio_file_upload,
            name="prompt_studio_upload",
        ),
        path(
            "prompt-studio/file/fetch_contents",
            prompt_studio_fetch_content,
            name="tool_studio_fetch",
        ),
        path(
            "prompt-studio/file",
            prompt_studio_file_list,
            name="prompt_studio_list",
        ),
    ]
)
