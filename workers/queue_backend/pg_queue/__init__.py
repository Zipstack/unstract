"""PG Queue (PGMQ) transport substrate — scaffold.

Reserved home for the PostgreSQL-backed queue substrate (PGMQ +
``SKIP LOCKED``) that will run alongside Celery during the Strangler-Fig
migration. PGMQ is a *core* worker transport — the intended primary
backend — so it lives inside the queue-backend seam next to its sibling
substrates (``dispatch``, ``routing``, ``barrier``, ``redis_barrier``),
**not** under ``workers/plugins/``, whose plugin *implementation
subdirectories* are the git-ignored overlay copied in at build time (the
directory itself — ``__init__.py``, ``plugin_manager.py`` — is tracked).

A subpackage (rather than a single module like the barriers) because the
real implementation will likely span several modules (config, consumer
poll loop, orchestrator) — exact layout TBD.

Empty by design in this phase. Routing decisions are made by
:func:`queue_backend.routing.select_backend`; until a consumer exists
here, PG-selected dispatches still ride Celery (see
``queue_backend.dispatch``).

Design reference: the PG Queue implementation guide in the labs repo
(``workflow-execution-architecture``). Branch and section pointers move,
so they're tracked on UN-3534 / the PR rather than baked in here.
"""
