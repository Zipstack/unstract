from django.urls import path
from rest_framework.urlpatterns import format_suffix_patterns
from .views import SPSPromptView

sps_prompt_detail = SPSPromptView.as_view(
    {
        "get": "retrieve",
        "patch": "partial_update",
        "delete": "destroy",
    }
)

sps_prompt_list = SPSPromptView.as_view(
    {
        "get": "list",
        "post": "create",
    }
)

urlpatterns = format_suffix_patterns(
    [
        path(
            "prompts/<uuid:pk>",
            sps_prompt_detail,
            name="spsprompt-detail",
        ),
        path(
            "prompts",
            sps_prompt_list,
            name="spsprompt-list",
        ),
    ]
)
