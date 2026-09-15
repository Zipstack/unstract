"""The converge command routes by PG_SCHEDULER_ENABLED — in BOTH directions.

Thin glue, but the branch is load-bearing: it is what makes a rollback a values
change rather than a procedure someone has to remember under pressure. Getting the
direction wrong would either adopt on a rollback (the opposite of intent) or leave
the reverse a no-op — the exact failure that stranded a pipeline on integration and
made Beat and the PG scheduler both fire it.

The sub-commands are stubbed: their own behaviour is covered by
test_reconcile_pg_schedules_command / test_mirror_pg_periodic_tasks. What is pinned
here is *which* is called, with *which* flags.
"""

from unittest.mock import patch

import pytest
from django.core.management import call_command

_CMD = "pg_queue.management.commands.converge_pg_scheduler"


def _run(monkeypatch, *, gate: bool, periodics: bool = False, dry_run: bool = False):
    """Run the command with the gate set, returning the sub-command calls made."""
    monkeypatch.setenv("PG_SCHEDULER_ENABLED", "true" if gate else "false")
    with patch(f"{_CMD}.call_command") as sub:
        args = ["converge_pg_scheduler"]
        if periodics:
            args.append("--periodics")
        if dry_run:
            args.append("--dry-run")
        call_command(*args)
    # {command_name: kwargs} — no sub-command is invoked twice in either direction.
    return {c.args[0]: c.kwargs for c in sub.call_args_list}


class TestDirection:
    def test_gate_on_adopts_pipelines(self, monkeypatch):
        calls = _run(monkeypatch, gate=True)
        assert "reconcile_pg_schedules" in calls
        # NOT mirror-only: that is the inert mode, which would adopt nothing.
        assert not calls["reconcile_pg_schedules"].get("mirror_only")
        assert not calls["reconcile_pg_schedules"].get("release_stale")

    def test_gate_off_releases_pipelines_back_to_beat(self, monkeypatch):
        calls = _run(monkeypatch, gate=False)
        kwargs = calls["reconcile_pg_schedules"]
        # Both halves: mirror stays inert-safe, release_stale is the actual rollback.
        assert kwargs["mirror_only"] is True
        assert kwargs["release_stale"] is True

    def test_an_unset_gate_converges_to_pg(self, monkeypatch):
        """Absent must mean PG, not "do nothing" — the default has to be the
        direction the deployment actually runs, and PG_SCHEDULER_ENABLED now
        defaults on (UN-4046).
        """
        monkeypatch.delenv("PG_SCHEDULER_ENABLED", raising=False)
        with patch(f"{_CMD}.call_command") as sub:
            call_command("converge_pg_scheduler")
        kwargs = {c.args[0]: c.kwargs for c in sub.call_args_list}
        # Hand-over direction: adopt, not release.
        assert "release_stale" not in kwargs["reconcile_pg_schedules"]


class TestPeriodicsAreOptIn:
    def test_periodics_are_untouched_by_default(self, monkeypatch):
        """Deferring metrics must be real.

        Adopting them requires workerPgMetrics to be deployed; doing it implicitly
        would fire dashboard_metrics.* into a queue with no consumer.
        """
        assert "mirror_pg_periodic_tasks" not in _run(monkeypatch, gate=True)
        assert "mirror_pg_periodic_tasks" not in _run(monkeypatch, gate=False)

    def test_gate_on_with_periodics_adopts_every_mirrored_row(self, monkeypatch):
        calls = _run(monkeypatch, gate=True, periodics=True)
        # Empty list = "all rows" (nargs="*"); None would mean the flag was absent.
        assert calls["mirror_pg_periodic_tasks"]["adopt"] == []

    def test_gate_off_with_periodics_releases_them(self, monkeypatch):
        calls = _run(monkeypatch, gate=False, periodics=True)
        assert calls["mirror_pg_periodic_tasks"]["release"] == []
        assert "adopt" not in calls["mirror_pg_periodic_tasks"]


class TestDryRunReaches_Everything:
    """A dry run that silently writes through one sub-command is worse than none."""

    @pytest.mark.parametrize("gate", [True, False])
    def test_dry_run_propagates_to_every_sub_command(self, monkeypatch, gate):
        calls = _run(monkeypatch, gate=gate, periodics=True, dry_run=True)
        assert calls, "no sub-commands were invoked"
        for name, kwargs in calls.items():
            assert kwargs.get("dry_run") is True, name
