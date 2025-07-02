from django.db import transaction
from django.urls import path
from django.utils.decorators import method_decorator
from rest_framework.urlpatterns import format_suffix_patterns

from .views import PromptStudioCoreView

prompt_studio_list = PromptStudioCoreView.as_view({"get": "list", "post": "create"})
prompt_studio_detail = PromptStudioCoreView.as_view(
    {
        "get": "retrieve",
        "put": "update",
        "patch": "partial_update",
        "delete": "destroy",
    }
)
prompt_studio_choices = PromptStudioCoreView.as_view({"get": "get_select_choices"})
prompt_studio_profiles = PromptStudioCoreView.as_view(
    {"get": "list_profiles", "patch": "make_profile_default"}
)

prompt_studio_prompts = PromptStudioCoreView.as_view({"post": "create_prompt"})

prompt_studio_profilemanager = PromptStudioCoreView.as_view(
    {"post": "create_profile_manager"}
)

prompt_studio_prompt_index = PromptStudioCoreView.as_view({"post": "index_document"})
prompt_studio_prompt_response = PromptStudioCoreView.as_view({"post": "fetch_response"})
prompt_studio_adapter_choices = PromptStudioCoreView.as_view(
    {"get": "get_adapter_choices"}
)
prompt_studio_single_pass_extraction = PromptStudioCoreView.as_view(
    {"post": "single_pass_extraction"}
)
prompt_studio_users = PromptStudioCoreView.as_view({"get": "list_of_shared_users"})


prompt_studio_file = PromptStudioCoreView.as_view(
    {
        "post": "upload_for_ide",
        "get": "fetch_contents_ide",
        "delete": "delete_for_ide",
    }
)

prompt_studio_export = PromptStudioCoreView.as_view(
    {"post": "export_tool", "get": "export_tool_info"}
)

prompt_studio_export_project = PromptStudioCoreView.as_view({"get": "export_project"})
prompt_studio_import_project = PromptStudioCoreView.as_view({"post": "import_project"})


urlpatterns = format_suffix_patterns(
    [
        path("prompt-studio/", prompt_studio_list, name="prompt-studio-list"),
        path(
            "prompt-studio/<uuid:pk>/",
            prompt_studio_detail,
            name="tool-studio-detail",
        ),
        path(
            "prompt-studio/select_choices/",
            prompt_studio_choices,
            name="prompt-studio-choices",
        ),
        path(
            "prompt-studio/prompt-studio-profile/<uuid:pk>/",
            prompt_studio_profiles,
            name="prompt-studio-profiles",
        ),
        path(
            "prompt-studio/prompt-studio-prompt/<uuid:pk>/",
            prompt_studio_prompts,
            name="prompt-studio-prompts",
        ),
        path(
            "prompt-studio/profilemanager/<uuid:pk>",
            prompt_studio_profilemanager,
            name="prompt-studio-profilemanager",
        ),
        path(
            "prompt-studio/index-document/<uuid:pk>",
            method_decorator(transaction.non_atomic_requests)(prompt_studio_prompt_index),
            name="prompt-studio-prompt-index",
        ),
        path(
            "prompt-studio/fetch_response/<uuid:pk>",
            prompt_studio_prompt_response,
            name="prompt-studio-prompt-response",
        ),
        path(
            "prompt-studio/adapter-choices/",
            prompt_studio_adapter_choices,
            name="prompt-studio-adapter-choices",
        ),
        path(
            "prompt-studio/single-pass-extraction/<uuid:pk>",
            prompt_studio_single_pass_extraction,
            name="prompt-studio-single-pass-extraction",
        ),
        path(
            "prompt-studio/users/<uuid:pk>",
            prompt_studio_users,
            name="prompt-studio-users",
        ),
        path(
            "prompt-studio/file/<uuid:pk>",
            prompt_studio_file,
            name="prompt_studio_file",
        ),
        path(
            "prompt-studio/export/<uuid:pk>",
            prompt_studio_export,
            name="prompt_studio_export",
        ),
        path(
            "prompt-studio/export-project/<uuid:pk>",
            prompt_studio_export_project,
            name="prompt_studio_export_project",
        ),
        path(
            "prompt-studio/import-project/",
            prompt_studio_import_project,
            name="prompt_studio_import_project",
        ),
    ]
)
