"""Regression guard for migration 0014's deploy-safety in-flight backfill.

The one line ``UPDATE pg_queue_message SET state='claimed' WHERE vt > now()`` is
what stops a rolling deploy over a non-empty queue from re-marking every in-flight
(claimed-but-unacked, future-``vt``) row as ``ready`` → instant re-claim →
fleet-wide one-time double processing (UN-3445 PR review, HIGH). Its correctness
rests on an ordering invariant nothing else locks down: ``AddField`` first backfills
ALL rows to ``ready``, and only this later ``RunSQL`` re-classifies the genuinely
in-flight ones. A refactor that drops/reorders the step, or inverts the ``vt > now()``
predicate, would silently reintroduce the exact bug this PR prevents — and every
state-machine test would still pass (they don't exercise the migration step).

This structurally pins the operation (present, correct predicate, ordered after the
``AddField``). The *behavioural* half — that ``vt > now()`` actually selects the
in-flight rows against real Postgres — is
``test_pg_queue_client.py::test_inflight_backfill_sql_classifies_by_vt`` (the backend
has no pytest-django / migration-executor harness, so a full-migration run isn't
cheap here; these two together catch removal, reordering, and predicate inversion).
"""

from importlib import import_module

from django.db import migrations

_MIGRATION = import_module(
    "pg_queue.migrations."
    "0014_remove_pgqueuemessage_pg_queue_message_dequeue_idx_and_more"
)


def _first_index(ops, predicate):
    return next((i for i, op in enumerate(ops) if predicate(op)), -1)


def test_inflight_backfill_present_correct_and_ordered_after_addfield():
    ops = _MIGRATION.Migration.operations

    add_state = _first_index(
        ops,
        lambda o: isinstance(o, migrations.AddField) and o.name == "state",
    )
    backfill = _first_index(
        ops,
        lambda o: isinstance(o, migrations.RunSQL)
        and "state = 'claimed'" in str(o.sql)
        and "vt > now()" in str(o.sql),
    )

    # Present: the backfill exists with the exact re-classification predicate.
    assert add_state >= 0, "0014 must add the `state` field"
    assert backfill >= 0, (
        "0014 must backfill in-flight rows with "
        "`UPDATE ... SET state='claimed' WHERE vt > now()` — removing/inverting it "
        "reintroduces fleet-wide double-delivery on a rolling deploy"
    )
    # Ordered: AddField sets every row 'ready' first; the backfill must run AFTER
    # it to re-classify the genuinely in-flight rows (reorder = no-op backfill).
    assert backfill > add_state, "the in-flight backfill must run after AddField(state)"
