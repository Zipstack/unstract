from extractor_registry import api_routes

#: The `kv` extractor's name. Kept as a constant, but NOT routable on this
#: deployment -- see `EXTRACTOR_ROUTES` below, which carries `table` only.
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

#: Which executor and operation each extractor dispatches to. DERIVED from the
#: shared catalogue in `extractor_registry` -- this is the blind API's view of
#: it. The Studio gets its own view of the same rows once cloud #1894 merges;
#: see `extractor_registry/__init__.py` for the current cross-repo state.
#:
#: **`kv` is deliberately absent**, because nothing drains
#: `celery_executor_agentic_kv` on this deployment. `SUPPORTED_EXTRACTORS` is
#: derived from these keys, so the omission turns a `kv` submit into a 400 at
#: the serializer instead of a 202 onto a queue with no consumer. The absence
#: is expressed as `available=False` on the catalogue's `multi_stage` row.
#:
#: Re-enabling is NOT a one-line change, and this comment deliberately does not
#: enumerate the rest -- every attempt to state the blast radius as a count or
#: a file list has been wrong. Flip `available=True` on that row, run the
#: BACKEND unit tier, and read the failures. Several pin the ABSENCE; retire
#: those rather than editing them green, but check first that a failing test
#: pins the absence rather than merely using it as a fixture.
#:
#: Two guards do NOT fail in that tier, so the procedure above will not find
#: them. `workers/tests/test_queue_consumer_wiring.py` pins queue names as
#: literals and cannot import this module, so it reds only once the queue is
#: also wired into the fleet; and the cloud chart's `agent_kv_wiring_test.yaml`
#: fails the chart build if `celery_executor_agentic_kv` appears anywhere.
#: Flipping the flag is also not sufficient on its own -- the Studio's door
#: needs a parameter builder in the cloud tree (see `extractor_registry.spec`),
#: and the queue needs worker-tier wiring.
EXTRACTOR_ROUTES = api_routes()

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
