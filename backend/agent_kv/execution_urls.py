from django.urls import path

from agent_kv.execution_views import (
    JobCancelView,
    JobResultView,
    JobStatusView,
    SubmitView,
    ValidateView,
)

urlpatterns = [
    path("", SubmitView.as_view(), name="agent_kv_submit"),
    path("validate", ValidateView.as_view(), name="agent_kv_validate"),
    path("<uuid:job_id>", JobStatusView.as_view(), name="agent_kv_status"),
    path("<uuid:job_id>/result", JobResultView.as_view(), name="agent_kv_result"),
    path("<uuid:job_id>/cancel", JobCancelView.as_view(), name="agent_kv_cancel"),
]
