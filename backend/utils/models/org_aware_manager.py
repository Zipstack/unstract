"""Auto-discovering organization-scoped manager."""

import logging

from django.core.exceptions import ImproperlyConfigured
from django.db import models
from django.db.utils import OperationalError, ProgrammingError
from utils.models.org_path_discovery import get_org_path
from utils.user_context import UserContext

logger = logging.getLogger(__name__)


class OrgAwareManager(models.Manager):
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
        except (RuntimeError, OperationalError, ProgrammingError):
            # OperationalError: DB not reachable (startup, migrations)
            # ProgrammingError: schema not ready (during migrations)
            # RuntimeError: pytest-django blocks DB access outside
            #   @pytest.mark.django_db. Note: this is a broad catch — any
            #   RuntimeError (e.g. from StateStore/middleware) returns an
            #   unfiltered queryset (fail-open). This is acceptable because
            #   OrgAwareManager is defense-in-depth; OrganizationFilterBackend
            #   at the view layer is the primary security boundary and
            #   fails-closed independently.
            return qs

        if org is None:
            # No request context (Celery, management commands, shell)
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
