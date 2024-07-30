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
    path("", include("tenant_account.urls")),
    path("", include("prompt.urls")),
    path("", include("project.urls")),
    path("", include("connector.urls")),
    path("", include("connector_processor.urls")),
    path("", include("adapter_processor.urls")),
    path("", include("file_management.urls")),
    path("", include("tool_instance.urls")),
    path("", include("pipeline.urls")),
    path("", include("feature_flag.urls")),
    path("workflow/", include("workflow_manager.urls")),
    path("platform/", include("platform_settings.urls")),
    path("api/", include("api.urls")),
    path("usage/", include("usage.urls")),
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
    path(
        UrlPathConstants.PROMPT_STUDIO,
        include("prompt_studio.prompt_studio_document_manager.urls"),
    ),
    path(
        UrlPathConstants.PROMPT_STUDIO,
        include("prompt_studio.prompt_studio_index_manager.urls"),
    ),
]


# APP deployment urls
try:
    import pluggable_apps.apps.app_deployment.urls  # noqa # pylint: disable=unused-import
    import pluggable_apps.apps.canned_question.urls  # noqa # pylint: disable=unused-import
    import pluggable_apps.apps.chat_history.urls  # noqa # pylint: disable=unused-import
    import pluggable_apps.apps.chat_transcript.urls  # noqa # pylint: disable=unused-import

    urlpatterns += [
        path(
            "canned_question/",
            include("pluggable_apps.apps.canned_question.urls"),
        ),
        path("app/", include("pluggable_apps.apps.app_deployment.urls")),
        path("chat_history/", include("pluggable_apps.apps.chat_history.urls")),
        path("chat/", include("pluggable_apps.apps.chat_transcript.urls")),
    ]
except ImportError:
    pass

# Subscription urls
try:

    import pluggable_apps.subscription.urls  # noqa  # pylint: disable=unused-import

    urlpatterns += [
        path("", include("pluggable_apps.subscription.urls")),
    ]
except ImportError:
    pass

try:
    import pluggable_apps.manual_review.api_urls  # noqa # pylint: disable=unused-import
    import pluggable_apps.manual_review.urls  # noqa # pylint: disable=unused-import

    urlpatterns += [
        path("manual_review/", include("pluggable_apps.manual_review.urls")),
        path("manual_review/", include("pluggable_apps.manual_review.api_urls")),
    ]
except ImportError:
    pass

# Public share urls
try:

    import pluggable_apps.public_shares.share_manager.urls  # noqa # pylint: disable=unused-import

    urlpatterns += [
        path("", include("pluggable_apps.public_shares.share_manager.urls")),
    ]
except ImportError:
    pass

# Clone urls
try:

    import pluggable_apps.clone.urls  # noqa # pylint: disable=unused-import

    urlpatterns += [
        path("", include("pluggable_apps.clone.urls")),
    ]
except ImportError:
    pass
