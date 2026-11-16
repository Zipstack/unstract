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

from django.db import transaction
from django.urls import path

from agent_kv.execution_views import (
    JobCancelView,
    JobResultView,
    JobStatusView,
    SubmitView,
)

urlpatterns = [
    # `non_atomic_requests`, and only on submit. A sync-wait submit
    # (`timeout` > 0) polls for the job to terminalize while still inside the
    # request. Under `DJANGO_ATOMIC_REQUESTS=True` the whole view runs in one
    # transaction, so neither the job row nor the queue insert is COMMITTED
    # while that poll runs -- no worker can see work that is not yet visible,
    # so the job cannot start, and every positive `timeout` burns its full
    # duration and then returns 202. The caller is not told; they just never
    # get the inline result the flag was supposed to give them.
    #
    # The flag defaults to False and ships False (`charts/unstract-platform/
    # values.yaml`), so nothing hits this today -- this keeps the view correct
    # if an operator ever turns it on, rather than leaving a silent
    # degradation behind a config switch. The same precondition is already
    # documented for the RPC path in `pg_queue/executor_rpc.py`
    # (`wait_for_result`): dispatch must not be called inside an open
    # transaction. This view needs nothing from an implicit transaction --
    # the job insert is one statement and every terminal write is its own
    # guarded UPDATE.
    path(
        "",
        transaction.non_atomic_requests(SubmitView.as_view()),
        name="agent_kv_submit",
    ),
    path("<uuid:job_id>", JobStatusView.as_view(), name="agent_kv_status"),
    path("<uuid:job_id>/result", JobResultView.as_view(), name="agent_kv_result"),
    path("<uuid:job_id>/cancel", JobCancelView.as_view(), name="agent_kv_cancel"),
]
