"""The one constant that drifts silently across the two repos.

``TABLE_STAGE_NAMES[0]`` here is the stage name ``_status_document`` will
*show*. ``STAGE_TABLE_EXTRACTION`` in the cloud repo's
``workers/plugins/agentic_table/src/api_binding.py`` is the name the executor
actually *sends*. They must be equal, and nothing enforces it:
``StageReportView`` persists whatever name arrives, and ``_status_document``
then filters a job's recorded stages through the list below.

So on drift the job completes normally, bills normally, and every status
response reports an empty ``stages`` array. No test on either side can catch
that alone -- each repo is internally consistent -- and from a client's seat it
reads as "the API is broken". This file is one half of the lock; the cloud half
is ``workers/plugins/agentic_table/tests/test_cross_repo_stage_name.py``.

A literal, not an import: the two repos are separate checkouts and only meet in
the merged tree, so an import would make this test pass vacuously wherever the
other side is absent -- exactly the environments where drift is introduced.
"""

from agent_kv.constants import TABLE_EXTRACTOR_NAME, TABLE_STAGE_NAMES

#: Must equal ``STAGE_TABLE_EXTRACTION`` in the cloud repo's
#: ``workers/plugins/agentic_table/src/api_binding.py``. Change one, change
#: both, in the same PR.
CLOUD_STAGE_TABLE_EXTRACTION = "table_extraction"


def test_the_status_filter_matches_the_name_the_executor_sends():
    assert TABLE_STAGE_NAMES[0] == CLOUD_STAGE_TABLE_EXTRACTION, (
        "TABLE_STAGE_NAMES[0] no longer equals STAGE_TABLE_EXTRACTION in the "
        "cloud repo's workers/plugins/agentic_table/src/api_binding.py. Every "
        "table job will complete normally while reporting an empty `stages` "
        "array. Update both sides, and the cloud twin of this test, together."
    )


def test_the_table_extractor_reports_exactly_one_stage():
    """The table engine exposes no node-level progress hooks, so a second name
    here would describe progress the executor cannot substantiate -- it would
    be recorded as missing rather than pending, for every job."""
    assert TABLE_STAGE_NAMES == [CLOUD_STAGE_TABLE_EXTRACTION]
    assert TABLE_EXTRACTOR_NAME == "table"


# ---------------------------------------------------------------------------
# Second cross-repo lock in this pair: the stage-STATUS allowlist.
#
# Same shape as the stage-name lock above and the same class of silent drift,
# but one layer along. `StageReportView` rejects a status outside
# `_VALID_STAGE_STATUSES` with a 400 -- and the cloud reporter
# (`extraction_seams.progress.StageReporter.report`) SWALLOWS 400s by design,
# because its contract is that a failed progress report must never fail a
# paid run. So if the two sets drift, every affected job completes and bills
# normally while its reported stage stays frozen at the last value that
# happened to be accepted.
#
# The cloud side already carried a `!! CROSS-REPO CONSTANT !!` banner on its
# copy with nothing asserting against this one. The cloud twin of this test is
# `workers/plugins/extraction_seams/tests/test_progress.py`.
# ---------------------------------------------------------------------------

#: Must equal ``VALID_STAGE_STATUSES`` in the cloud repo's
#: ``workers/plugins/extraction_seams/src/progress.py``. Change one, change
#: both, in the same PR.
#:
#: A literal, not an import: the two repos are separate checkouts and only meet
#: in the merged tree, so an import would make this pass vacuously wherever the
#: other side is absent -- exactly the environments where drift is introduced.
CLOUD_VALID_STAGE_STATUSES = frozenset({"running", "done"})


def test_the_accepted_stage_statuses_match_what_the_executor_sends():
    from agent_kv.internal_views import _VALID_STAGE_STATUSES

    assert _VALID_STAGE_STATUSES == CLOUD_VALID_STAGE_STATUSES, (
        "_VALID_STAGE_STATUSES no longer equals VALID_STAGE_STATUSES in the "
        "cloud repo's workers/plugins/extraction_seams/src/progress.py. Stage "
        "reports will be rejected with a 400 that the cloud reporter swallows, "
        "so jobs will complete and bill while their reported stage freezes. "
        "Update both sides, and both twins of this test, together."
    )


def test_a_terminal_outcome_is_not_an_accepted_stage_status():
    """Why the set is only two values, asserted rather than described.

    Terminal outcomes travel on finalize. `"failed"` as a stage status is the
    case that actually shipped once, and accepting it here would let a job
    report a terminal stage while its row stayed non-terminal.
    """
    from agent_kv.internal_views import _VALID_STAGE_STATUSES

    for terminal in ("failed", "completed", "cancelled", "timed_out"):
        assert terminal not in _VALID_STAGE_STATUSES, terminal
