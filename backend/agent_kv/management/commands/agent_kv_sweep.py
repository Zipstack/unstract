"""CronJob entrypoint for the Agent-KV never-dispatched/stuck-job sweep.

Thin wrapper around :func:`agent_kv.maintenance.run_sweep` -- see that
function's docstring for the two-phase sweep logic itself (spec §5.4). This
command is the cloud mechanism for driving it: a Kubernetes CronJob runs
``python manage.py agent_kv_sweep`` on a schedule. The internal
``SweepView``/``POST /internal/v1/agent-kv/sweep/`` endpoint
(``agent_kv/internal_views.py``) delegates to the same function and remains
the OSS/self-hosted mechanism, driven by the PG-scheduler periodic task
(``workers/scheduler/agent_kv_tasks.py``).
"""

import json

from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Terminalize never-dispatched and stuck Agent-KV jobs (CronJob entrypoint)"

    def handle(self, *args, **options):
        from agent_kv.maintenance import run_sweep

        self.stdout.write(json.dumps(run_sweep()))
