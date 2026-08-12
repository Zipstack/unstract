"""Shared access gate for the ``execution/<pk>/...`` routes (UN-2651).

Every route under that prefix is addressed by a ``WorkflowExecution`` id and
nothing else, so the id is what has to be authorized. The logs endpoint and the
file-execution endpoint back the same screen for the same id — keeping one gate
is what stops them drifting apart again.
"""

import logging

from rest_framework.exceptions import PermissionDenied
from utils.user_context import UserContext

from workflow_manager.workflow_v2.models.execution import WorkflowExecution

logger = logging.getLogger(__name__)


def assert_execution_accessible(user, execution_id) -> None:
    """Raise ``PermissionDenied`` unless ``user`` may read ``execution_id``.

    Unknown ids are denied exactly like inaccessible ones, so the response is
    not an existence oracle. The two are still told apart in the log line —
    the server is now the only place that can, and the distinction is what
    separates a stale bookmark from someone walking the id space.
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
