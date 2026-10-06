"""Public Agent-KV execution routes.

``ValidateView`` is **deliberately not routed here.** It compiles a `kv` keys
schema through ``unstract.agent_kv_schema.compile_schema`` and does nothing
else; the `table` extractor's ``keys`` is ``{"target_table": ...}``, validated
by ``TableKeysSerializer`` at submit. Publishing an endpoint that validates
schemas for an extractor this deployment refuses with a 400 would be an
incoherent public contract.

The view class and the schema package both stay in the tree. Deleting them
would force a content merge in the files the branch carrying the KV engine
rewrites most; leaving them makes restoring this endpoint one line.
"""

from django.urls import path

from agent_kv.execution_views import (
    JobCancelView,
    JobResultView,
    JobStatusView,
    SubmitView,
)

urlpatterns = [
    path("", SubmitView.as_view(), name="agent_kv_submit"),
    path("<uuid:job_id>", JobStatusView.as_view(), name="agent_kv_status"),
    path("<uuid:job_id>/result", JobResultView.as_view(), name="agent_kv_result"),
    path("<uuid:job_id>/cancel", JobCancelView.as_view(), name="agent_kv_cancel"),
]
