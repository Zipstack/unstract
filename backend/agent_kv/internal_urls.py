from django.urls import path

from agent_kv.internal_views import (
    FinalizeView,
    StageReportView,
    SweepView,
    TTLCleanupView,
)

urlpatterns = [
    path(
        "jobs/<uuid:job_id>/stage/",
        StageReportView.as_view(),
        name="agent_kv_internal_stage",
    ),
    path(
        "jobs/<uuid:job_id>/finalize/",
        FinalizeView.as_view(),
        name="agent_kv_internal_finalize",
    ),
    path(
        "sweep/",
        SweepView.as_view(),
        name="agent_kv_internal_sweep",
    ),
    path(
        "ttl-cleanup/",
        TTLCleanupView.as_view(),
        name="agent_kv_internal_ttl_cleanup",
    ),
]
