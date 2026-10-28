"""The envelope key that drifts silently across the two repos.

``EXTRACTOR_AGENTS[TABLE].output_key`` here is the key the Studio unwraps the
table rows from. ``ExtractionOutput.to_dict()`` in the cloud repo's
``workers/plugins/agentic_table_engine/src/interface/runner.py`` is what
actually emits it. They must be equal. The consumer
(``agentic_studio_v1.services.schema_placeholder.unwrap_agent_output``) falls
back to returning the WHOLE envelope on a key miss, and ``apply_agent_output``
then counts that as placed -- so the "not placed" warning never fires.

On drift the job completes normally, bills normally, and the user's schema
field holds ``{"tables": [...], "page_count": 7, ...}`` where their rows were
supposed to go. No exception is raised; the cloud-side fallback does log a
WARNING naming the missing key, and that is the only runtime signal there is.

THIS FILE IS ONLY THE CONSUMER HALF. On its own it fires when someone edits
the two adjacent lines below -- the side a reader is already looking at -- and
NOT on the drift that actually happens, a rename in ``to_dict()``. The producer
half is
``workers/plugins/agentic_table_engine/tests/test_cross_repo_output_key.py``
in the cloud repo, added by cloud PR #1894. **That PR merges after this one**,
so between the two merges the lock is one-sided in the direction that matters;
there is no window in which it is one-sided the other way. Both halves are
mutation-verified against a rename of the key they pin.

A literal, not an import: the two repos are separate checkouts and the
producer is not tracked here at all (``workers/plugins/``'s plugin
subdirectories are gitignored in OSS; the directory itself is tracked for its
infrastructure files), so an import would pass vacuously in the environment
where drift is introduced.
"""

from django.test import SimpleTestCase

from extractor_registry import EXTRACTOR_AGENTS, ExtractorAgentKey

#: Must equal the rows key in ``ExtractionOutput.to_dict()`` in the cloud
#: repo's ``workers/plugins/agentic_table_engine/src/interface/runner.py``.
#: Change one, change both, in the same PR.
CLOUD_TABLE_OUTPUT_KEY = "tables"


class CrossRepoOutputKeyTest(SimpleTestCase):
    def test_the_unwrap_key_matches_what_the_executor_emits(self) -> None:
        table = EXTRACTOR_AGENTS[ExtractorAgentKey.TABLE]
        self.assertEqual(
            table.output_key,
            CLOUD_TABLE_OUTPUT_KEY,
            "output_key no longer equals the key ExtractionOutput.to_dict() "
            "emits in the cloud repo's agentic_table_engine. Every table run "
            "will complete and then substitute run metadata into the user's "
            "schema field instead of their rows, with no exception and no log "
            "line. Update both sides, and the cloud twin of this test.",
        )
