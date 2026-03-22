import logging

from rest_framework.filters import BaseFilterBackend

from utils.models.org_aware_manager import OrgAwareManager
from utils.models.org_path_discovery import get_org_path
from utils.models.organization_mixin import DefaultOrganizationManagerMixin
from utils.user_context import UserContext

logger = logging.getLogger(__name__)


class OrganizationFilterBackend(BaseFilterBackend):
    """Global filter backend that enforces organization scoping.

    Added to DEFAULT_FILTER_BACKENDS in settings.py. Runs on ALL DRF
    operations (list, retrieve, update, delete) via filter_queryset().

    Viewsets MUST NOT override filter_backends — use DEFAULT_FILTER_BACKENDS.
    If a viewset needs additional filter backends, append to the default
    rather than replacing it.

    Three modes:
    1. Model uses org-aware manager → already safe, skip
    2. Auto-discover FK path to Organization via BFS → filter
    3. No path found or no org context → return empty queryset (fail-closed)

    Opt-out: set skip_org_filter = True on the viewset.
    """

    def filter_queryset(self, request, queryset, view):
        if getattr(view, "skip_org_filter", False):
            return queryset

        model = queryset.model

        # Mode 1: model's manager already filters by org
        if isinstance(
            model._default_manager,
            (DefaultOrganizationManagerMixin, OrgAwareManager),
        ):
            return queryset

        org = UserContext.get_organization()
        if org is None:
            logger.warning(
                "OrganizationFilterBackend: No org context for %s.%s "
                "in %s. Returning empty queryset (fail-closed).",
                model._meta.app_label,
                model.__name__,
                view.__class__.__name__,
            )
            return queryset.none()

        # Mode 2: auto-discover or use cached path
        path = get_org_path(model)
        if path:
            return queryset.filter(**{path: org})

        # Mode 3: no path found — fail-closed to prevent data leaks
        logger.warning(
            "OrganizationFilterBackend: No org path for %s.%s "
            "in %s. Returning empty queryset (fail-closed).",
            model._meta.app_label,
            model.__name__,
            view.__class__.__name__,
        )
        return queryset.none()
