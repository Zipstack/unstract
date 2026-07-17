from django.urls import path
from rest_framework.urlpatterns import format_suffix_patterns

from pipeline_v2.constants import PipelineURL
from pipeline_v2.execution_view import PipelineExecutionViewSet
from pipeline_v2.views import PipelineViewSet

pipeline_list = PipelineViewSet.as_view(
    {
        "get": "list",
        "post": "create",
    }
)
execution_list = PipelineExecutionViewSet.as_view(
    {
        "get": "list",
    }
)
pipeline_detail = PipelineViewSet.as_view(
    {
        "get": "retrieve",
        "put": "update",
        "patch": "partial_update",
        "delete": "destroy",
    }
)

download_postman_collection = PipelineViewSet.as_view(
    {
        "get": PipelineViewSet.download_postman_collection.__name__,
    }
)

list_shared_users = PipelineViewSet.as_view(
    {
        "get": PipelineViewSet.list_of_shared_users.__name__,
    }
)

pipeline_execute = PipelineViewSet.as_view({"post": "execute"})
pipeline_share = PipelineViewSet.as_view({"post": "share"})
pipeline_effective_members = PipelineViewSet.as_view({"get": "effective_members"})
pipeline_add_owner = PipelineViewSet.as_view({"post": "add_co_owner"})
pipeline_remove_owner = PipelineViewSet.as_view({"delete": "remove_co_owner"})


urlpatterns = format_suffix_patterns(
    [
        path("pipeline/", pipeline_list, name=PipelineURL.LIST),
        path("pipeline/<uuid:pk>/", pipeline_detail, name=PipelineURL.DETAIL),
        path(
            "pipeline/<uuid:pk>/executions/",
            execution_list,
            name=PipelineURL.EXECUTIONS,
        ),
        path("pipeline/execute/", pipeline_execute, name=PipelineURL.EXECUTE),
        path(
            "pipeline/<uuid:pk>/users/",
            list_shared_users,
            name="pipeline-shared-users",
        ),
        path(
            "pipeline/<uuid:pk>/share/",
            pipeline_share,
            name="pipeline-share",
        ),
        path(
            "pipeline/<uuid:pk>/effective-members/",
            pipeline_effective_members,
            name="pipeline-effective-members",
        ),
        path(
            "pipeline/<uuid:pk>/owners/",
            pipeline_add_owner,
            name="pipeline-add-owner",
        ),
        path(
            "pipeline/<uuid:pk>/owners/<int:user_id>/",
            pipeline_remove_owner,
            name="pipeline-remove-owner",
        ),
        path(
            "pipeline/api/postman_collection/<uuid:pk>/",
            download_postman_collection,
            name="download_pipeline_postman_collection",
        ),
    ]
)
