# urls.py
from apps.chat_history.views import ChatHistoryView
from django.urls import path
from rest_framework.urlpatterns import format_suffix_patterns

chat_history = ChatHistoryView.as_view(
    {
        "get": ChatHistoryView.list.__name__,
        "post": ChatHistoryView.create.__name__,
    }
)

urlpatterns = format_suffix_patterns(
    [
        path("chats/", chat_history, name="chat_session_list_create"),
    ]
)
