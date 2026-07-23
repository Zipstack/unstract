"""Tests for the reconcile_pg_schedules management command.

DB-free: the ORM, mirror upsert, and ownership reconcile are mocked. These pin
the operator-facing contract — backfill skip, the malformed-args guard, the
dry-run preview, the counters, and the non-zero exit on failure.
"""

from unittest.mock import MagicMock, patch

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError

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
            PT.objects.filter.return_value = [pt_new, pt_exists]
            # pid-exists already mirrored; pid-new not (one prefetch query).
            Sched.objects.values_list.return_value = ["pid-exists"]
            Sched.objects.all.return_value = [_row("pid-new"), _row("pid-exists")]
            call_command("reconcile_pg_schedules")

        upsert.assert_called_once()  # only the unmirrored one backfilled
        assert upsert.call_args.kwargs["pipeline_id"] == "pid-new"
        assert reconcile.call_count == 2  # both rows reconciled

    def test_malformed_args_skipped_not_fatal(self):
        bad = _pt("pid-bad", args="{ this is not json")
        good = _pt("pid-good", args='["wf", "org", "", "", "pid-good", false, "n"]')
        with (
            patch(f"{_CMD}.PeriodicTask") as PT,
            patch(f"{_CMD}.PgPeriodicSchedule") as Sched,
            patch(f"{_CMD}.mirror_periodic_schedule_upsert") as upsert,
            patch(f"{_CMD}.reconcile_ownership_for", return_value=False),
        ):
            PT.objects.filter.return_value = [bad, good]
            Sched.objects.values_list.return_value = []
            Sched.objects.all.return_value = []
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
            PT.objects.filter.return_value = [weird]
            Sched.objects.values_list.return_value = []
            Sched.objects.all.return_value = []
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
            PT.objects.filter.return_value = [
                _pt("pid-1", args='["wf", "org", "", "", "pid-1", false, "n"]')
            ]
            Sched.objects.values_list.return_value = []
            Sched.objects.all.return_value = [_row("pid-1")]
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
            PT.objects.filter.return_value = []
            Sched.objects.values_list.return_value = []
            Sched.objects.all.return_value = [_row("pid-1")]
            with pytest.raises(CommandError):
                call_command("reconcile_pg_schedules")
