"""Auto-discovering organization-scoped manager."""

import logging

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
        - No FK path to Organization: logs warning, no filtering
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
            # RuntimeError: pytest-django blocks DB access
            # OperationalError: DB not reachable (startup, migrations)
            # ProgrammingError: schema not ready (during migrations)
            return qs

        if org is None:
            # No request context (Celery, management commands, shell)
            return qs

        path = get_org_path(self.model)
        if path is None:
            logger.warning(
                "OrgAwareManager: No org path for %s.%s. "
                "Queries will not be org-scoped.",
                self.model._meta.app_label,
                self.model.__name__,
            )
            return qs

        return qs.filter(**{path: org})
