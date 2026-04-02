import logging

from django.db.models import Q
from rest_framework.filters import BaseFilterBackend

from utils.models.org_path_discovery import get_org_path
from utils.user_context import UserContext

logger = logging.getLogger(__name__)

# ViewSet attributes read by OrganizationFilterBackend.
# Use these constants when setting attributes on ViewSets to avoid typos.
SKIP_ORG_FILTER = "skip_org_filter"
ORG_FILTER_PATHS = "org_filter_paths"


class OrganizationFilterBackend(BaseFilterBackend):
    """Global filter backend that enforces organization scoping.

    Added to DEFAULT_FILTER_BACKENDS in settings.py. Runs on ALL DRF
    operations (list, retrieve, update, delete) via filter_queryset().

    Always applies org filtering via BFS-discovered FK path — never trusts
    model managers to have already filtered. Double-filtering with
    OrgAwareManager or DefaultOrganizationManagerMixin is idempotent
    and harmless.

    Viewsets MUST NOT override filter_backends — use DEFAULT_FILTER_BACKENDS.
    If a viewset needs additional filter backends, append to the default
    rather than replacing it.

    Opt-out: set skip_org_filter = True on the viewset.

    For models with multiple nullable FK paths to Organization, set
    org_filter_paths on the viewset to use OR filtering across all
    paths (skips BFS):

        class NotificationViewSet(viewsets.ModelViewSet):
            org_filter_paths = [
                "pipeline__workflow__organization",
                "api__workflow__organization",
            ]
    """

    def filter_queryset(self, request, queryset, view):
        if getattr(view, SKIP_ORG_FILTER, False):
            return queryset

        model = queryset.model

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

        # Use explicit paths if set on the viewset (for models with
        # multiple nullable FK paths to Organization).
        explicit_paths = getattr(view, ORG_FILTER_PATHS, None)
        if explicit_paths:
            q = Q()
            for path in explicit_paths:
                q |= Q(**{path: org})
            return queryset.filter(q)

        path = get_org_path(model)
        if path:
            return queryset.filter(**{path: org})

        # No path found — fail-closed
        logger.warning(
            "OrganizationFilterBackend: No org path for %s.%s "
            "in %s. Returning empty queryset (fail-closed).",
            model._meta.app_label,
            model.__name__,
            view.__class__.__name__,
        )
        return queryset.none()
