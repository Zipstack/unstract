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
