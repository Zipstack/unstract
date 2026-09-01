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

from unittest.mock import patch

import pytest

from file_processing import structure_tool_task as st
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


class TestDispatcherFactory:
    """Pin the call-site swap this PR makes: the impl builds its dispatcher via
    ``get_executor_dispatcher(celery_app=app)`` (the gate-routed dispatcher), not
    the raw SDK ``ExecutionDispatcher``. A mis-import or wrong arg would otherwise
    silently bypass the PG routing with nothing failing.
    """

    @staticmethod
    def _params() -> dict:
        return {
            "organization_id": "org1",
            "file_execution_id": "fe1",
            "tool_instance_metadata": {},
            "platform_service_api_key": "sk",
            "input_file_path": "/in/f.pdf",
            "output_dir_path": "/out",
            "source_file_name": "f.pdf",
            "execution_data_dir": "/data",
        }

    def test_impl_builds_dispatcher_via_factory_with_app(self):
        # Stub everything up to (and just past) the dispatcher construction, then
        # raise to stop before the heavy tool-metadata work runs.
        with (
            patch("executor.executor_tool_shim.ExecutorToolShim"),
            patch.object(st, "_create_platform_helper"),
            patch.object(st, "_get_file_storage"),
            patch.object(st, "get_executor_dispatcher") as factory,
            patch.object(st, "_fetch_tool_metadata", side_effect=RuntimeError("stop")),
        ):
            params = self._params()
            with pytest.raises(RuntimeError, match="stop"):
                st._execute_structure_tool_impl(params)
        factory.assert_called_once_with(celery_app=st.app)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
