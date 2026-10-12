"""Tests for the reconcile_pg_schedules management command.

DB-free: the ORM, mirror upsert, and ownership reconcile are mocked. These pin
the operator-facing contract — backfill skip, the malformed-args guard, the
dry-run preview, the counters, and the non-zero exit on failure.
"""

from unittest.mock import MagicMock, patch

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError

from pg_queue.management.commands.reconcile_pg_schedules import (
    DEFAULT_BATCH_SIZE,
)

_CMD = "pg_queue.management.commands.reconcile_pg_schedules"


def _pt(name, args="[]", enabled=True):
    m = MagicMock()
    m.name = name
    m.args = args
    m.enabled = enabled
    m.crontab.minute = "0"
    m.crontab.hour = "9"
    m.crontab.day_of_month = "*"
    m.crontab.month_of_year = "*"
    m.crontab.day_of_week = "*"
    return m


def _row(pid, org="org", enabled=True):
    m = MagicMock()
    m.pipeline_id = pid
    m.organization_id = org
    m.enabled = enabled
    return m


def _periodic_tasks(rows):
    """Mock the PeriodicTask queryset chain the command now uses.

    The command reads `.filter(...).select_related(...).order_by(...).iterator(...)`
    so the scan is chunked; these tests pin behaviour, not the chain, so the helper
    absorbs the plumbing.
    """
    qs = MagicMock()
    qs.select_related.return_value.order_by.return_value.iterator.return_value = rows
    return qs


def _sched_ids(ids):
    """Mock `.values_list("pipeline_id", flat=True).iterator(...)`."""
    vl = MagicMock()
    vl.iterator.return_value = ids
    return vl


def _sched_rows(rows):
    """Mock `.order_by("pk").iterator(...)`."""
    qs = MagicMock()
    qs.iterator.return_value = rows
    return qs


class TestReconcileCommand:
    def test_backfills_only_unmirrored_and_reconciles(self):
        pt_new = _pt("pid-new", args='["wf", "org", "", "", "pid-new", false, "n"]')
        pt_exists = _pt("pid-exists")
        with (
            patch(f"{_CMD}.PeriodicTask") as PT,
            patch(f"{_CMD}.PgPeriodicSchedule") as Sched,
            patch(f"{_CMD}.mirror_periodic_schedule_upsert") as upsert,
            patch(f"{_CMD}.reconcile_ownership_for", return_value=False) as reconcile,
        ):
            PT.objects.filter.return_value = _periodic_tasks([pt_new, pt_exists])
            # pid-exists already mirrored; pid-new not (one prefetch query).
            Sched.objects.values_list.return_value = _sched_ids(["pid-exists"])
            Sched.objects.order_by.return_value = _sched_rows([_row("pid-new"), _row("pid-exists")])
            call_command("reconcile_pg_schedules")

        upsert.assert_called_once()  # only the unmirrored one backfilled
        assert upsert.call_args.kwargs["pipeline_id"] == "pid-new"
        assert reconcile.call_count == 2  # both rows reconciled

    def test_mirror_only_backfills_but_never_reconciles(self):
        """--mirror-only is what deploy automation runs, so it must be safe at ANY
        flag state. The reconcile it skips is the step that disables Beat rows once
        the rollout is on — an unattended job must never make that change."""
        pt_new = _pt("pid-new", args='["wf", "org", "", "", "pid-new", false, "n"]')
        with (
            patch(f"{_CMD}.PeriodicTask") as PT,
            patch(f"{_CMD}.PgPeriodicSchedule") as Sched,
            patch(f"{_CMD}.mirror_periodic_schedule_upsert") as upsert,
            patch(f"{_CMD}.reconcile_ownership_for") as reconcile,
        ):
            PT.objects.filter.return_value = _periodic_tasks([pt_new])
            Sched.objects.values_list.return_value = _sched_ids([])
            Sched.objects.order_by.return_value = _sched_rows([_row("pid-new")])
            call_command("reconcile_pg_schedules", "--mirror-only")

        upsert.assert_called_once()  # the backfill still happens
        reconcile.assert_not_called()  # the ownership flip does not

    def test_malformed_args_skipped_not_fatal(self):
        bad = _pt("pid-bad", args="{ this is not json")
        good = _pt("pid-good", args='["wf", "org", "", "", "pid-good", false, "n"]')
        with (
            patch(f"{_CMD}.PeriodicTask") as PT,
            patch(f"{_CMD}.PgPeriodicSchedule") as Sched,
            patch(f"{_CMD}.mirror_periodic_schedule_upsert") as upsert,
            patch(f"{_CMD}.reconcile_ownership_for", return_value=False),
        ):
            PT.objects.filter.return_value = _periodic_tasks([bad, good])
            Sched.objects.values_list.return_value = _sched_ids([])
            Sched.objects.order_by.return_value = _sched_rows([])
            # Must not raise despite the bad row.
            call_command("reconcile_pg_schedules")

        # Only the good row backfilled; the bad one skipped, not fatal.
        assert upsert.call_count == 1
        assert upsert.call_args.kwargs["pipeline_id"] == "pid-good"

    def test_non_list_args_skipped(self):
        weird = _pt("pid-weird", args="null")  # valid JSON, not a list
        with (
            patch(f"{_CMD}.PeriodicTask") as PT,
            patch(f"{_CMD}.PgPeriodicSchedule") as Sched,
            patch(f"{_CMD}.mirror_periodic_schedule_upsert") as upsert,
            patch(f"{_CMD}.reconcile_ownership_for", return_value=False),
        ):
            PT.objects.filter.return_value = _periodic_tasks([weird])
            Sched.objects.values_list.return_value = _sched_ids([])
            Sched.objects.order_by.return_value = _sched_rows([])
            call_command("reconcile_pg_schedules")

        upsert.assert_not_called()

    def test_dry_run_writes_nothing_but_previews_owner(self):
        with (
            patch(f"{_CMD}.PeriodicTask") as PT,
            patch(f"{_CMD}.PgPeriodicSchedule") as Sched,
            patch(f"{_CMD}.mirror_periodic_schedule_upsert") as upsert,
            patch(f"{_CMD}.reconcile_ownership_for") as reconcile,
            patch(f"{_CMD}.resolve_schedule_owner", return_value=True) as resolve,
        ):
            PT.objects.filter.return_value = _periodic_tasks(
                [_pt("pid-1", args='["wf", "org", "", "", "pid-1", false, "n"]')]
            )
            Sched.objects.values_list.return_value = _sched_ids([])
            Sched.objects.order_by.return_value = _sched_rows([_row("pid-1")])
            call_command("reconcile_pg_schedules", "--dry-run")

        upsert.assert_not_called()  # no backfill write
        reconcile.assert_not_called()  # no ownership write
        resolve.assert_called_once()  # but the would-be owner is previewed

    def test_failure_raises_command_error(self):
        with (
            patch(f"{_CMD}.PeriodicTask") as PT,
            patch(f"{_CMD}.PgPeriodicSchedule") as Sched,
            patch(f"{_CMD}.mirror_periodic_schedule_upsert"),
            patch(f"{_CMD}.reconcile_ownership_for", return_value=None),  # failed
        ):
            PT.objects.filter.return_value = _periodic_tasks([])
            Sched.objects.values_list.return_value = _sched_ids([])
            Sched.objects.order_by.return_value = _sched_rows([_row("pid-1")])
            with pytest.raises(CommandError):
                call_command("reconcile_pg_schedules")


class TestChunking:
    """Both loops must stay bounded — there is one row per scheduled pipeline, so an
    unbounded scan holds the whole pipeline population in memory (twice, before this).
    Pinned so a later refactor can't quietly drop `.iterator()`.
    """

    def _run(self, extra_args=()):
        with (
            patch(f"{_CMD}.PeriodicTask") as PT,
            patch(f"{_CMD}.PgPeriodicSchedule") as Sched,
            patch(f"{_CMD}.mirror_periodic_schedule_upsert"),
            patch(f"{_CMD}.reconcile_ownership_for", return_value=False),
        ):
            PT.objects.filter.return_value = _periodic_tasks([])
            Sched.objects.values_list.return_value = _sched_ids([])
            Sched.objects.order_by.return_value = _sched_rows([])
            call_command("reconcile_pg_schedules", *extra_args)
            return PT, Sched

    def test_both_scans_are_chunked_with_the_default_batch_size(self):
        PT, Sched = self._run()
        pt_chain = PT.objects.filter.return_value.select_related.return_value
        pt_chain.order_by.return_value.iterator.assert_called_once_with(
            chunk_size=DEFAULT_BATCH_SIZE
        )
        Sched.objects.order_by.return_value.iterator.assert_called_once_with(
            chunk_size=DEFAULT_BATCH_SIZE
        )

    def test_mirrored_id_prefetch_streams_rather_than_materialising(self):
        # This one used to build a set from the full table with no bound.
        _, Sched = self._run()
        Sched.objects.values_list.assert_called_once_with("pipeline_id", flat=True)
        Sched.objects.values_list.return_value.iterator.assert_called_once_with(
            chunk_size=DEFAULT_BATCH_SIZE
        )

    def test_batch_size_flag_is_honoured(self):
        PT, Sched = self._run(("--batch-size", "7"))
        pt_chain = PT.objects.filter.return_value.select_related.return_value
        pt_chain.order_by.return_value.iterator.assert_called_once_with(chunk_size=7)
        Sched.objects.order_by.return_value.iterator.assert_called_once_with(chunk_size=7)

    def test_scans_are_ordered_so_a_chunked_walk_is_deterministic(self):
        # Without an ORDER BY, a chunked scan has no guaranteed row order between
        # batches, so rows can be visited twice or not at all.
        PT, Sched = self._run()
        pt_chain = PT.objects.filter.return_value.select_related.return_value
        assert pt_chain.order_by.call_args[0] == ("pk",)
        assert Sched.objects.order_by.call_args[0] == ("pk",)

    @pytest.mark.parametrize("bad", ["0", "-1"])
    def test_non_positive_batch_size_is_rejected(self, bad):
        with pytest.raises(CommandError, match="--batch-size"):
            call_command("reconcile_pg_schedules", "--batch-size", bad)
