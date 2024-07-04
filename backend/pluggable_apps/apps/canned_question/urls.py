# urls.py
from django.urls import path
from pluggable_apps.apps.canned_question.views import CannedQuestionView
from rest_framework.urlpatterns import format_suffix_patterns

deployment = CannedQuestionView.as_view(
    {
        "post": CannedQuestionView.create.__name__,
    }
)
deployment_details = CannedQuestionView.as_view(
    {
        "get": CannedQuestionView.retrieve.__name__,
        "patch": CannedQuestionView.partial_update.__name__,
        "delete": CannedQuestionView.destroy.__name__,
    }
)

urlpatterns = format_suffix_patterns(
    [
        path("", deployment, name="canned_question_list_create"),
        path(
            "<uuid:pk>/",
            deployment_details,
            name="canned_question_details",
        ),
    ]
)
