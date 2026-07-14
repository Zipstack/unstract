"""Direct unit tests for ``file_processing.structure_tool_task`` helpers.

Locks contracts that the integration test in ``test_sanity_phase5.py``
exercises indirectly. Specifically guards ``_fairness_headers``:

* The hard-coded ``WorkloadType.NON_API`` default. Per the docstring,
  ``API`` is "strictly worse" here — flipping it would silently
  preempt ETL work under API traffic.
* The wire shape consumers see at the dispatcher. A regression in
  ``FairnessKey.as_header()``'s serialisation surfaces here too.

Paired with the ``headers=`` assertion in
``test_sanity_phase5.TestStructureToolSingleDispatch`` — together
they cover both "the helper returns the right thing" and "the call
site forwards it".
"""

from __future__ import annotations

import pytest

from file_processing.structure_tool_task import (
    _fairness_headers,
    _should_skip_extraction_for_vision,
)
from queue_backend.fairness import WorkloadType


class TestFairnessHeaders:
    def test_returns_non_api_wire_shape(self):
        """``_fairness_headers`` emits the canonical ``x-fairness-key``
        envelope with ``workload_type='non_api'`` and the default
        ``pipeline_priority=5``."""
        assert _fairness_headers("org-1") == {
            "x-fairness-key": {
                "org_id": "org-1",
                "workload_type": "non_api",
                "pipeline_priority": 5,
            }
        }

    def test_org_id_is_propagated_verbatim(self):
        wire = _fairness_headers("another-org")
        assert wire["x-fairness-key"]["org_id"] == "another-org"

    def test_workload_type_is_non_api_not_api(self):
        """Pinned because the docstring calls ``NON_API`` "the safe
        default" and ``API`` "strictly worse" — a regression that
        flips this would silently let API traffic preempt ETL work.
        """
        wire = _fairness_headers("org-1")
        assert wire["x-fairness-key"]["workload_type"] == WorkloadType.NON_API.value
        assert wire["x-fairness-key"]["workload_type"] != WorkloadType.API.value


class TestShouldSkipExtractionForVision:
    """Tests for ``_should_skip_extraction_for_vision``.

    Extraction should be skipped only when ALL prompts use image-only
    vision mode (extraction_inputs="image").
    """

    def test_empty_outputs_returns_false(self):
        assert _should_skip_extraction_for_vision([]) is False

    def test_all_text_only_returns_false(self):
        outputs = [
            {"name": "p1", "extraction_inputs": "text"},
            {"name": "p2", "extraction_inputs": "text"},
        ]
        assert _should_skip_extraction_for_vision(outputs) is False

    def test_all_image_only_returns_true(self):
        outputs = [
            {"name": "p1", "extraction_inputs": "image"},
            {"name": "p2", "extraction_inputs": "image"},
        ]
        assert _should_skip_extraction_for_vision(outputs) is True

    def test_mixed_modes_returns_false(self):
        """If any prompt needs text, extraction must run."""
        outputs = [
            {"name": "p1", "extraction_inputs": "image"},
            {"name": "p2", "extraction_inputs": "both"},
        ]
        assert _should_skip_extraction_for_vision(outputs) is False

    def test_both_mode_returns_false(self):
        outputs = [{"name": "p1", "extraction_inputs": "both"}]
        assert _should_skip_extraction_for_vision(outputs) is False

    def test_missing_field_defaults_to_text(self):
        """Outputs without extraction_inputs should default to text."""
        outputs = [{"name": "p1"}]
        assert _should_skip_extraction_for_vision(outputs) is False

    def test_single_image_only_returns_true(self):
        outputs = [{"name": "p1", "extraction_inputs": "image"}]
        assert _should_skip_extraction_for_vision(outputs) is True


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
