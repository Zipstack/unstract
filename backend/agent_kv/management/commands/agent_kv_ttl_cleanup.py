"""CronJob entrypoint for the Agent-KV TTL cleanup of expired staged files.

Thin wrapper around :func:`agent_kv.maintenance.run_ttl_cleanup` -- see that
function's docstring for the cleanup logic itself (spec §5.4). This command
is the cloud mechanism for driving it: a Kubernetes CronJob runs
``python manage.py agent_kv_ttl_cleanup`` on a schedule. The internal
``TTLCleanupView``/``POST /internal/v1/agent-kv/ttl-cleanup/`` endpoint
(``agent_kv/internal_views.py``) delegates to the same function and remains
the OSS/self-hosted mechanism, driven by the PG-scheduler periodic task
(``workers/scheduler/agent_kv_tasks.py``).
"""

import json

from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Delete staged files for expired Agent-KV jobs (CronJob entrypoint)"

    def handle(self, *args, **options):
        from agent_kv.maintenance import run_ttl_cleanup

        self.stdout.write(json.dumps(run_ttl_cleanup()))
