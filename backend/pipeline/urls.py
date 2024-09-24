from django.urls import path
from pipeline.constants import PipelineURL
from pipeline.execution_view import PipelineExecutionViewSet
from pipeline.views import PipelineViewSet
from rest_framework.urlpatterns import format_suffix_patterns

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

pipeline_execute = PipelineViewSet.as_view({"post": "execute"})


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
            "pipeline/api/postman_collection/<uuid:pk>/",
            download_postman_collection,
            name="download_pipeline_postman_collection",
        ),
    ]
)
