from django.urls import path

from agent_kv.execution_views import SubmitView

urlpatterns = [
    path("", SubmitView.as_view(), name="agent_kv_submit"),
]
