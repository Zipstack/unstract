"""Auto-discovering organization-scoped manager."""

import logging

from django.core.exceptions import ImproperlyConfigured
from django.db.utils import OperationalError, ProgrammingError
from utils.models.base_model import BaseModelManager
from utils.models.org_path_discovery import get_org_path
from utils.user_context import UserContext

logger = logging.getLogger(__name__)


class OrgAwareManager(BaseModelManager):
    """Manager that auto-discovers FK path to Organization and applies
    org filtering to all queries in request context.

    Unlike DefaultOrganizationManagerMixin (which requires a direct
    organization FK on the model), this manager uses BFS to auto-discover
    the FK chain. Works with any model that has a path to Organization
    through foreign keys.

    Usage:
        1. Models WITHOUT a custom manager — add directly::

            class ExecutionLog(BaseModel):
                wf_execution = models.ForeignKey(WorkflowExecution, ...)
                ...
                objects = OrgAwareManager()

        2. Models WITH a custom manager — use as base class
           (replaces models.Manager in the class definition)::

            class WorkflowExecutionManager(OrgAwareManager):
                def for_user(self, user) -> QuerySet:
                    # Custom methods work as before. self.filter() and
                    # self.all() automatically include org scoping from
                    # OrgAwareManager.get_queryset().
                    ...


            class WorkflowExecution(BaseModel):
                objects = WorkflowExecutionManager()

    Behavior:
        - In request context (middleware sets org): filters by org
        - Outside request context (Celery, commands): no filtering
        - No FK path to Organization: raises ImproperlyConfigured
        - During migrations/startup: gracefully skips filtering

    All queries on the model become org-scoped during requests — not just
    viewset querysets, but also serializer method fields, signals, and
    utility functions.
    """

    def get_queryset(self):
        qs = super().get_queryset()

        try:
            org = UserContext.get_organization()
        except (RuntimeError, OperationalError, ProgrammingError) as exc:
            # OperationalError: DB not reachable (startup, migrations)
            # ProgrammingError: schema not ready (during migrations)
            # RuntimeError: pytest-django blocks DB access outside
            #   @pytest.mark.django_db.
            #
            # Deliberately fail open: these are all "the request context does
            # not exist yet", not "this caller may not see these rows".
            # OrganizationFilterBackend is the primary boundary and fails
            # closed independently at the view layer.
            #
            # The RuntimeError arm is broader than its stated cause:
            # StateStore compares an env string against a ConcurrencyMode
            # member, which never matches, so it raises whenever
            # CONCURRENCY_MODE is set at all — including to the documented
            # "thread". Hence the log line. This path is rare (startup,
            # migrations, tests), so it is signal rather than noise, and it is
            # the only way an unexpected fail-open becomes visible.
            logger.warning(
                "OrgAwareManager: no organization context for %s (%s: %s); "
                "returning an unfiltered queryset.",
                self.model._meta.label,
                type(exc).__name__,
                exc,
            )
            return qs

        if org is None:
            if UserContext.get_organization_identifier():
                # An identifier is set but did not resolve to a row —
                # Organization.DoesNotExist or ProgrammingError inside
                # get_organization(), both of which it flattens to None. That
                # happens *inside* a request, so returning everything here
                # would cross tenants. Only the no-identifier case below is
                # the "no request context" one.
                logger.warning(
                    "OrgAwareManager: organization identifier is set but did "
                    "not resolve for %s; returning an empty queryset.",
                    self.model._meta.label,
                )
                return qs.none()
            # No request context at all: Celery, management commands, shell.
            # Not logged — this is the normal state for every query those
            # make, and a line per queryset would drown the cases above.
            return qs

        path = get_org_path(self.model)
        if path is None:
            raise ImproperlyConfigured(
                f"OrgAwareManager on {self.model._meta.app_label}."
                f"{self.model.__name__} but no FK path to Organization. "
                f"Either add a FK chain to Organization or "
                f"remove OrgAwareManager from this model."
            )

        return qs.filter(**{path: org})
