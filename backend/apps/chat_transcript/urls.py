# urls.py
from apps.chat_transcript.views import ChatTranscriptView
from django.urls import path
from rest_framework.urlpatterns import format_suffix_patterns

chat_transcript = ChatTranscriptView.as_view(
    {
        "get": ChatTranscriptView.list.__name__,
        "post": ChatTranscriptView.create.__name__,
    }
)

urlpatterns = format_suffix_patterns(
    [
        path(
            "chats/<uuid:chat_history_id>/",
            chat_transcript,
            name="chat_list_create",
        ),
    ]
)
