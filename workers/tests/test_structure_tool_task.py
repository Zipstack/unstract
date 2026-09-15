"""Direct unit tests for ``file_processing.structure_tool_task`` helpers.

UN-4046 removed ``TestFairnessHeaders``. It pinned the wire shape of
``_fairness_headers()``, which was passed as ``headers=`` to every executor
dispatch — but the routing dispatcher never forwarded headers to the PG path
(see ``PgExecutionDispatcher.dispatch``'s own docstring), so the value was
inert on the only transport that runs. With the router gone the helper is
deleted and the three tests describe a function that no longer exists.

Fairness on PG is not lost and is not tested here: it rides the enqueue payload
(``transport.enqueue(..., org_id=...)``), and ``queue_backend`` owns its
coverage. The paired "call site forwards it" assertion referenced by the old
docstring lived in a ``test_sanity_phase5.py`` that no longer exists either.

What remains is ``TestDispatcherFactory``, which guards the UN-3779 regression:
the impl must build its dispatcher via the factory, not a raw
``ExecutionDispatcher``.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest
from file_processing import structure_tool_task as st


class TestDispatcherFactory:
    """Pin the call-site swap this PR makes: the impl builds its dispatcher via
    ``get_executor_dispatcher()`` (the shared factory), not
    the raw SDK ``ExecutionDispatcher``. A mis-import would otherwise
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

    def test_impl_builds_dispatcher_via_factory(self):
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
        # No arguments since UN-4046 — the factory's accepted-and-ignored
        # `celery_app` was removed once Sonar flagged it as an unused parameter.
        factory.assert_called_once_with()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
