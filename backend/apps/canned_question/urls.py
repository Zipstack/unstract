# urls.py
from apps.canned_question.views import CannedQuestionView
from django.urls import path
from rest_framework.urlpatterns import format_suffix_patterns

deployment = CannedQuestionView.as_view(
    {
        "get": CannedQuestionView.list.__name__,
        "post": CannedQuestionView.create.__name__,
    }
)
deployment_details = CannedQuestionView.as_view(
    {
        "get": CannedQuestionView.retrieve.__name__,
        "put": CannedQuestionView.update.__name__,
        "patch": CannedQuestionView.partial_update.__name__,
        "delete": CannedQuestionView.destroy.__name__,
    }
)

urlpatterns = format_suffix_patterns(
    [
        path("canned_question/", deployment, name="canned_question_list_create"),
        path(
            "canned_question/<uuid:pk>/",
            deployment_details,
            name="canned_question_details",
        ),
    ]
)
