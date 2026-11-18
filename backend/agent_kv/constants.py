<<<<<<< HEAD
#: The `kv` extractor's name. Kept as a constant, but NOT routable on this
#: deployment -- see `EXTRACTOR_ROUTES` below, which carries `table` only.
=======
from extractor_registry import api_routes

#: The `kv` extractor's name -- the key-value/agentic-KV engine, routable
#: alongside `table` (see `EXTRACTOR_ROUTES` below).
>>>>>>> 56bd4641 (UN-4214 [MISC] One shared Extractor Agent registry, two front doors (#2379))
#:
#: An earlier version of this comment said "v1 accepts exactly one extractor
#: (`kv`), so the job row does not carry which one it ran". Both halves are now
#: wrong, on line 1 of the file that defines the routing table: `kv` is the one
#: extractor this deployment does NOT accept, and `AgentKVJob.extractor` has
#: carried the name since migration 0002.
V1_EXTRACTOR_NAME = "kv"

STAGE_NAMES = [
    "document_processing",
    "extraction",
    "qa",
    "challenge",
    "normalize",
    "constraints",
    "codegen",
    "code_execution",
]
EXECUTOR_NAME = "agentic_kv"
OPERATION_KV_EXTRACT = "kv_extract"
EXECUTION_SOURCE = "agent_kv_api"

#: The table extractor, served by the cloud `agentic_table` plugin's blind-API
#: operation. It reuses the IDE table path's executor, and therefore its
#: already-wired `celery_executor_agentic_table` queue, with a second
#: operation; a new executor name would derive a queue nothing drains.
TABLE_EXTRACTOR_NAME = "table"

#: Read by `test_queue_wiring_is_derived.py`'s ALL_KNOWN_EXECUTORS. The
#: blind-API operation is not duplicated in THIS module -- it is still stated
#: independently in `workers/executor/tasks.py`, which cannot import the
#: catalogue -- and the route test pins the wire value directly.
#:
#: `EXECUTOR_NAME` and `OPERATION_KV_EXTRACT` above are the same shape of
#: restatement for the `kv` row and are kept, because `ALL_KNOWN_EXECUTORS`
#: needs a literal the worker-side suite can read. They are cross-checked
#: against the catalogue by `test_the_kv_route_constants_match_the_catalogue`;
#: before that they were asserted against their own values.
TABLE_EXECUTOR_NAME = "agentic_table"

<<<<<<< HEAD
#: Which executor and operation each extractor dispatches to. `dispatch_job`
#: reads this rather than hardcoding one pair, so adding an extractor is one
#: entry here plus its options serializer and stage list.
=======
#: Which executor and operation each extractor dispatches to. DERIVED from the
#: shared catalogue in `extractor_registry` -- this is the blind API's view of
#: it, one entry per catalogue row with an API door. The Studio gets its own
#: view of the same rows once cloud #1894 merges; see
#: `extractor_registry/__init__.py` for the current cross-repo state.
#:
#: The catalogue's `available` flag is NOT consulted here. It says whether the
#: Studio may offer an agent, and `multi_stage` is still `available=False`
#: there while `kv` is routed here: the two doors gate on different things,
#: and this door's gate is `enabled_extractors()` in `execution_serializers.py`.
#:
#: `dispatch_job` reads this rather than hardcoding one pair, so adding an
#: extractor is one catalogue row with an API door plus its options
#: serializer, stage list and -- where the executor requires adapters -- its
#: adapters serializer, AND its entry in the
#: acceptance gate (`_EXTRACTOR_ENABLE_FLAGS` in `execution_serializers.py` --
#: a setting name to gate it, or `_UNGATED` to accept it everywhere, with
#: `test_every_routed_extractor_has_a_gate_entry` deriving the requirement from
#: this table so the step cannot be skipped). An earlier revision named this
#: step while the gate was a single `if` on one hard-coded name, so there was
#: nowhere to put the entry and a new extractor inherited the
#: 202-into-a-dead-queue shape this very comment warns about. `SUPPORTED_EXTRACTORS` is derived from
#: these keys (`execution_serializers.py`), so this table decides what is
#: ROUTED -- NOT what `extractors[].name` accepts, which is
#: `enabled_extractors()`'s. An earlier wording claimed "this table alone
#: decides what accepts", contradicting the paragraph two below it.
>>>>>>> 56bd4641 (UN-4214 [MISC] One shared Extractor Agent registry, two front doors (#2379))
#:
#: **`kv` is deliberately absent.** This deployment ships the `agentic_table`
#: plugin and not `agentic_kv`, so nothing drains `celery_executor_agentic_kv`.
#: `SUPPORTED_EXTRACTORS` is derived from this table's keys
#: (`execution_serializers.py`), so the omission turns a `kv` submit into a 400
#: at the serializer. Restoring the entry below is all it takes to re-enable
#: the extractor once the plugin ships -- and restoring it WITHOUT the plugin
#: is the failure this guards: the submit would be accepted with a 202,
#: dispatched to a queue with no consumer, and sit in DISPATCHED forever with
#: no error at the producer and nothing in any log to find.
#:
<<<<<<< HEAD
#: `V1_EXTRACTOR_NAME`, `STAGE_NAMES` and the KV options serializer stay in the
#: tree, dormant and still under test, so re-enabling is one line rather than a
#: content merge against the branch that carries the engine.
EXTRACTOR_ROUTES = {
    TABLE_EXTRACTOR_NAME: (TABLE_EXECUTOR_NAME, OPERATION_TABLE_EXTRACT_API),
}
=======
#: Routing `kv` is therefore NOT what enables it. Acceptance is gated separately,
#: on `AGENT_KV_KV_EXTRACTOR_ENABLED` (`enabled_extractors()` in
#: `execution_serializers.py`), which the chart sets in the same values file
#: that adds `celery_executor_agentic_kv` to the executor fleet's queue list.
#: The flag defaults false, which is what makes the merge order safe: this repo
#: merges first -- the cloud half imports `unstract-agent-kv-schema` from it --
#: and until the chart lands a `kv` submit is refused at validation instead of
#: being accepted into a queue nothing serves.
#:
#: An earlier revision of this comment listed three facts "checked against a
#: running deployment", the third citing `agent_kv_wiring_test.yaml::AKV-Q5b`
#: as pinning that the fleet subscribes. That citation was a FORWARD reference
#: and is worth recording as one: on the cloud repo's `main` that test asserts
#: the subscription is ABSENT ("the executor ConfigMap does not subscribe to
#: the agentic_kv queue"), and it is inverted only by the paired cloud PR. The
#: dev environment those facts were checked against was running both halves, so
#: the check was real but described no deployable image built from `main`. The
#: flag above replaces the convention that the two PRs would land together with
#: something a deployment states about itself.
#:
#: `EXECUTOR_NAME`/`OPERATION_KV_EXTRACT` matching what `AgenticKVExecutor`
#: dispatches on is still pinned by `test_the_kv_route_targets_the_shipped_executor`.
EXTRACTOR_ROUTES = api_routes()
>>>>>>> 56bd4641 (UN-4214 [MISC] One shared Extractor Agent registry, two front doors (#2379))

#: The table engine reports one coarse stage: it has no node-level progress
#: hooks (the IDE path gets `stream_log` only), so inventing finer stages here
#: would describe progress the executor cannot actually report.
TABLE_STAGE_NAMES = ["table_extraction"]

#: Stage names ARE wire format -- they are returned to clients -- and they are
#: extractor-specific (`qa`/`challenge`/`codegen` mean nothing to the table
#: extractor). `_status_document` filters a job's recorded stages through the
#: list for the extractor that ran: `StageReportView` persists whatever name
#: the executor sends, so without a per-extractor list a table job's stages
#: would be stored and then silently filtered out of every status response.
STAGE_NAMES_BY_EXTRACTOR = {
    V1_EXTRACTOR_NAME: STAGE_NAMES,
    TABLE_EXTRACTOR_NAME: TABLE_STAGE_NAMES,
}
