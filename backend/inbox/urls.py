from django.urls import path

from inbox.views import InboxViewSet

urlpatterns = [
    path("", InboxViewSet.as_view({"get": "list"}), name="inbox"),
    path("read-all/", InboxViewSet.as_view({"post": "read_all"}), name="inbox_read_all"),
    path("<uuid:pk>/read/", InboxViewSet.as_view({"post": "read"}), name="inbox_read"),
]
