"""The envelope key that drifts silently across the two repos.

``EXTRACTOR_AGENTS[TABLE].output_key`` here is the key the Studio unwraps the
table rows from. ``ExtractionOutput.to_dict()`` in the cloud repo's
``workers/plugins/agentic_table_engine/src/interface/runner.py`` is what
actually emits it. They must be equal, and nothing enforces it: the consumer
(``agentic_studio_v1.services.schema_placeholder.unwrap_agent_output``) falls
back to returning the WHOLE envelope on a key miss, and ``apply_agent_output``
then counts that as placed -- so the "not placed" warning never fires.

On drift the job completes normally, bills normally, and the user's schema
field holds ``{"tables": [...], "page_count": 7, ...}`` where their rows were
supposed to go. No exception, no log line. This file is one half of the lock;
the cloud half belongs in
``workers/plugins/agentic_table_engine/tests/`` asserting the same literal
against ``to_dict()``.

A literal, not an import: the two repos are separate checkouts and the
producer is not tracked here at all (``workers/plugins/`` is gitignored in
OSS), so an import would make this pass vacuously in exactly the environment
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
