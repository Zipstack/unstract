from django.urls import path
from pluggable_apps.apps.chat_transcript.views import ChatTranscriptView
from rest_framework.urlpatterns import format_suffix_patterns

chat_transcript = ChatTranscriptView.as_view(
    {
        "post": ChatTranscriptView.create.__name__,
    }
)

urlpatterns = format_suffix_patterns(
    [
        path(
            "",
            chat_transcript,
            name="chat_transcript",
        ),
    ]
)
