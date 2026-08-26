"""Record dispatch as a POSITIVE fact instead of inferring it from absent handles.

The undispatched sweep (``workflow_v2/undispatched_sweep.py``) decides that an
execution "never dispatched" from ``task_id IS NULL AND queue_message_id IS NULL``.
That is an inference, and it is unsound: three paths in ``workflow_helper`` reach
exactly that state AFTER the message is already on its transport —

* ``_record_dispatch_handle`` raising and the caller swallowing it, under the comment
  "continuing — the orchestrator is already running";
* the handle coming back empty and the recorder returning without writing;
* a PG handle that will not parse as a bigint, same early return.

So the sweep could claim a RUNNING execution, mark it ERROR and tell the user "You can
safely run it again". On the Celery transport that self-corrected — the orchestrator ran
regardless and its terminal write superseded the ERROR. On PG it does NOT: both worker
entry points stop on a terminal execution (``general/tasks.py`` returns
``skipped_terminal_execution``; ``file_processing/tasks.py`` raises
``_TerminalExecutionSkip``), so the message is acked and the work is silently DROPPED.

``dispatched_at`` removes the inference. It is stamped by the dispatcher the moment
dispatch succeeds, BEFORE any handle bookkeeping can fail, so all three paths above are
covered by one write.

Nullable and additive
---------------------
No backfill, and none is needed. Every pre-existing row has ``dispatched_at IS NULL``
whatever its true state, so the sweep predicate KEEPS the two handle checks alongside the
new one::

    WHERE status = 'PENDING' AND created_at < now() - grace
      AND dispatched_at IS NULL
      AND task_id IS NULL AND queue_message_id IS NULL

That is what makes this a ONE-PHASE deploy. During a rolling upgrade an old backend pod
dispatches without stamping; the row then matches ``dispatched_at IS NULL`` but is
excluded by ``task_id IS NOT NULL``. Drop the handle checks and you would need to stamp
everywhere first and switch the predicate in a later release, or sweep live work
mid-deploy.

The index over that predicate is swapped separately in 0028, which needs
``atomic = False`` for ``CREATE INDEX CONCURRENTLY``; keeping the column addition here
means this migration stays a fast, transactional, single-purpose change.
"""

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("workflow_v2", "0026_workflowexecution_undispatched_idx"),
    ]

    operations = [
        migrations.AddField(
            model_name="workflowexecution",
            name="dispatched_at",
            field=models.DateTimeField(
                null=True,
                blank=True,
                db_comment=(
                    "Set when the orchestrator task was handed to its transport. NULL means "
                    "never dispatched. The POSITIVE fact the undispatched sweep needs: absent "
                    "task_id/queue_message_id also occurs for executions that ARE running, "
                    "because three paths in workflow_helper return without recording a handle "
                    "after the message is already enqueued."
                ),
            ),
        ),
    ]
