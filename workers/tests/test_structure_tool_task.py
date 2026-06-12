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

from file_processing.structure_tool_task import _fairness_headers
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


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
