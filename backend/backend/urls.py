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

from backend.constants import UrlPathConstants
from django.conf.urls import *  # noqa: F401, F403
from django.urls import include, path

urlpatterns = [
    path("", include("tenant_account.urls")),
    path("", include("prompt.urls")),
    path("", include("project.urls")),
    path("", include("connector.urls")),
    path("", include("connector_processor.urls")),
    path("", include("adapter_processor.urls")),
    path("", include("file_management.urls")),
    path("", include("tool_instance.urls")),
    path("", include("cron_expression_generator.urls")),
    path("", include("pipeline.urls")),
    path("workflow/", include("workflow_manager.urls")),
    path("platform/", include("platform_settings.urls")),
    path("api/", include("api.urls")),
    path(
        UrlPathConstants.PROMPT_STUDIO,
        include("prompt_studio.prompt_profile_manager.urls"),
    ),
    path(
        UrlPathConstants.PROMPT_STUDIO,
        include("prompt_studio.prompt_studio.urls"),
    ),
    path("", include("prompt_studio.prompt_studio_core.urls")),
    path(
        UrlPathConstants.PROMPT_STUDIO,
        include("prompt_studio.prompt_studio_registry.urls"),
    ),
    path(
        UrlPathConstants.PROMPT_STUDIO,
        include("prompt_studio.prompt_studio_output_manager.urls"),
    ),
    path("", include("apps.canned_question.urls")),
    path("", include("apps.app_deployment.urls")),
    path("", include("apps.chat_history.urls")),
    path("", include("apps.chat_transcript.urls")),
    path("", include("apps.document_management.urls")),
]
