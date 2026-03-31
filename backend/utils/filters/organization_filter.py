import logging

from rest_framework.filters import BaseFilterBackend

from utils.models.org_path_discovery import get_org_path
from utils.user_context import UserContext

logger = logging.getLogger(__name__)


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
    """

    def filter_queryset(self, request, queryset, view):
        if getattr(view, "skip_org_filter", False):
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
