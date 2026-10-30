from django.urls import path

from inbox.internal_views import PurgeInboxAPIView

urlpatterns = [path("purge/", PurgeInboxAPIView.as_view(), name="inbox_purge")]
