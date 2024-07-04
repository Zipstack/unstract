from django.urls import path
from pluggable_apps.apps.chat_history.views import ChatHistoryView
from rest_framework.urlpatterns import format_suffix_patterns

chat_history = ChatHistoryView.as_view(
    {
        "post": ChatHistoryView.create.__name__,
    }
)

chat_history_details = ChatHistoryView.as_view(
    {
        "get": ChatHistoryView.retrieve.__name__,
    }
)

urlpatterns = format_suffix_patterns(
    [
        path("", chat_history, name="chat_history"),
        path(
            "<uuid:pk>/",
            chat_history_details,
            name="chat_history_details",
        ),
    ]
)
