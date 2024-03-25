from django.urls import path
from rest_framework.urlpatterns import format_suffix_patterns

from .views import PromptStudioOutputView

prompt_doc_list = PromptStudioOutputView.as_view({"get": "list"})

urlpatterns = format_suffix_patterns(
    [
        path("prompt-output/", prompt_doc_list, name="prompt-doc-list"),
    ]
)
