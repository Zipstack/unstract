"""Shared access gate for the ``execution/<pk>/...`` routes (UN-2651).

Those routes are addressed by a ``WorkflowExecution`` id and nothing else, so
the id is what gets authorized. One gate keeps them from drifting apart.
"""

import logging

from rest_framework.exceptions import PermissionDenied
from utils.user_context import UserContext

from workflow_manager.workflow_v2.models.execution import WorkflowExecution

logger = logging.getLogger(__name__)


def assert_execution_accessible(user, execution_id) -> None:
    """Raise ``PermissionDenied`` unless ``user`` may read ``execution_id``.

    Unknown ids are denied like inaccessible ones so the response is not an
    existence oracle; the log line keeps the distinction.
    """
    if WorkflowExecution.objects.for_user(user).filter(pk=execution_id).exists():
        return

    logger.warning(
        "Execution access denied: user=%s execution=%s org=%s exists=%s",
        getattr(user, "id", None),
        execution_id,
        UserContext.get_organization_identifier(),
        WorkflowExecution.objects.filter(pk=execution_id).exists(),
    )
    raise PermissionDenied("You do not have access to this execution.")
