from django.urls import include, path

from backend.constants import FeatureFlag
from unstract.flags.feature_flag import check_feature_flag_status

if check_feature_flag_status(FeatureFlag.MULTI_TENANCY_V2):
    from workflow_manager.endpoint_v2 import urls as endpoint_urls
    from workflow_manager.workflow_v2 import urls as workflow_urls
else:
    from workflow_manager.endpoint import urls as endpoint_urls
    from workflow_manager.workflow import urls as workflow_urls

urlpatterns = [
    path("endpoint/", include(endpoint_urls)),
    path(
        "<uuid:pk>/endpoint/",
        include(
            [
                path(
                    "",
                    endpoint_urls.workflow_endpoint_list,
                    name="workflow-endpoint",
                )
            ]
        ),
    ),
    path("", include(workflow_urls)),
]
