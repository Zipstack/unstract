"""PG Queue (PGMQ) transport substrate — scaffold.

Reserved home for the PostgreSQL-backed queue substrate (PGMQ +
``SKIP LOCKED``) that will run alongside Celery during the Strangler-Fig
migration. PGMQ is a *core* worker transport — the intended primary
backend — so it lives inside the queue-backend seam next to its sibling
substrates (``dispatch``, ``routing``, ``barrier``, ``redis_barrier``),
**not** under ``workers/plugins/`` (that directory is the git-ignored
overlay for cloud/enterprise plugins copied in at build time).

A subpackage (rather than a single module like the barriers) because
the real implementation spans several files — ``config.py`` (per-task
timeouts/retries), ``consumer.py`` (poll loop + graceful shutdown), and
the single-orchestrator (admit / reap / route, fair-admission query).

Empty by design in this phase. Routing decisions are made by
:func:`queue_backend.routing.select_backend`; until a consumer exists
here, PG-selected dispatches still ride Celery (see
``queue_backend.dispatch``).

Labs reference: ``Zipstack/labs:labs-ali/workflow-execution-architecture``
— ``docs/pg-queue-implementation-guide.md`` (§3 Worker Lifecycle,
§6 Orchestrator).
"""
