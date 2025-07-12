"""URL configuration for backend project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/4.2/topics/http/urls/

Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""

from django.conf.urls import *  # noqa: F401, F403
from django.urls import include, path

from backend.constants import UrlPathConstants

urlpatterns = [
    path("", include("tenant_account_v2.urls")),
    path("", include("connector_v2.urls")),
    path("", include("connector_processor.urls")),
    path("", include("adapter_processor_v2.urls")),
    path("", include("file_management.urls")),
    path("", include("tool_instance_v2.urls")),
    path("", include("pipeline_v2.urls")),
    path("", include("feature_flag.urls")),
    path("workflow/", include("workflow_manager.urls")),
    path("platform/", include("platform_settings_v2.urls")),
    path("api/", include("api_v2.urls")),
    path("usage/", include("usage_v2.urls")),
    path("notifications/", include("notification_v2.urls")),
    path("logs/", include("logs_helper.urls")),
    path(
        UrlPathConstants.PROMPT_STUDIO,
        include("prompt_studio.prompt_profile_manager_v2.urls"),
    ),
    path(
        UrlPathConstants.PROMPT_STUDIO,
        include("prompt_studio.prompt_studio_v2.urls"),
    ),
    path("", include("prompt_studio.prompt_studio_core_v2.urls")),
    path(
        UrlPathConstants.PROMPT_STUDIO,
        include("prompt_studio.prompt_studio_registry_v2.urls"),
    ),
    path(
        UrlPathConstants.PROMPT_STUDIO,
        include("prompt_studio.prompt_studio_output_manager_v2.urls"),
    ),
    path(
        UrlPathConstants.PROMPT_STUDIO,
        include("prompt_studio.prompt_studio_document_manager_v2.urls"),
    ),
    path(
        UrlPathConstants.PROMPT_STUDIO,
        include("prompt_studio.prompt_studio_index_manager_v2.urls"),
    ),
    path("tags/", include("tags.urls")),
    path("execution/", include("workflow_manager.execution.urls")),
    path("execution/", include("workflow_manager.file_execution.urls")),
]
