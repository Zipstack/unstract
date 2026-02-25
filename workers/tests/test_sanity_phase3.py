"""Phase 3-SANITY — Integration tests for the structure tool Celery task.

Tests the full structure tool pipeline with mocked platform API and
ExecutionDispatcher. After Phase 5E, the structure tool task dispatches a
single ``structure_pipeline`` operation to the executor worker instead of
3 sequential dispatches.  These tests verify the correct pipeline params
are assembled and the result is written to filesystem.
"""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from shared.enums.task_enums import TaskName
from unstract.sdk1.execution.context import ExecutionContext
from unstract.sdk1.execution.result import ExecutionResult

# ---------------------------------------------------------------------------
# Patch targets
# ---------------------------------------------------------------------------

_PATCH_DISPATCHER = (
    "file_processing.structure_tool_task.ExecutionDispatcher"
)
_PATCH_PLATFORM_HELPER = (
    "file_processing.structure_tool_task._create_platform_helper"
)
_PATCH_FILE_STORAGE = (
    "file_processing.structure_tool_task._get_file_storage"
)
_PATCH_SHIM = (
    "executor.executor_tool_shim.ExecutorToolShim"
)
_PATCH_SERVICE_IS_STRUCTURE = (
    "shared.workflow.execution.service."
    "WorkerWorkflowExecutionService._is_structure_tool_workflow"
)
_PATCH_SERVICE_EXECUTE_STRUCTURE = (
    "shared.workflow.execution.service."
    "WorkerWorkflowExecutionService._execute_structure_tool_workflow"
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_fs():
    """Create a mock file storage."""
    fs = MagicMock(name="file_storage")
    fs.exists.return_value = False
    fs.read.return_value = ""
    fs.json_dump.return_value = None
    fs.write.return_value = None
    fs.get_hash_from_file.return_value = "abc123hash"
    return fs


@pytest.fixture
def mock_dispatcher():
    """Create a mock ExecutionDispatcher that returns success results."""
    dispatcher = MagicMock(name="ExecutionDispatcher")
    return dispatcher


@pytest.fixture
def mock_platform_helper():
    """Create a mock PlatformHelper."""
    helper = MagicMock(name="PlatformHelper")
    return helper


@pytest.fixture
def tool_metadata_regular():
    """Standard prompt studio tool metadata."""
    return {
        "name": "Test Project",
        "is_agentic": False,
        "tool_id": "tool-123",
        "tool_settings": {
            "vector-db": "vdb-1",
            "embedding": "emb-1",
            "x2text_adapter": "x2t-1",
            "llm": "llm-1",
        },
        "outputs": [
            {
                "name": "field_a",
                "prompt": "What is the revenue?",
                "type": "text",
                "active": True,
                "chunk-size": 512,
                "chunk-overlap": 128,
                "retrieval-strategy": "simple",
                "llm": "llm-1",
                "embedding": "emb-1",
                "vector-db": "vdb-1",
                "x2text_adapter": "x2t-1",
                "similarity-top-k": 5,
            },
        ],
    }


@pytest.fixture
def base_params():
    """Base params dict for execute_structure_tool."""
    return {
        "organization_id": "org-test",
        "workflow_id": "wf-123",
        "execution_id": "exec-456",
        "file_execution_id": "fexec-789",
        "tool_instance_metadata": {
            "prompt_registry_id": "preg-001",
        },
        "platform_service_api_key": "sk-test-key",
        "input_file_path": "/data/test.pdf",
        "output_dir_path": "/output",
        "source_file_name": "test.pdf",
        "execution_data_dir": "/data/exec",
        "messaging_channel": "channel-1",
        "file_hash": "filehash123",
        "exec_metadata": {"tags": ["tag1"]},
    }


def _make_pipeline_result(
    output: dict | None = None,
    metadata: dict | None = None,
    metrics: dict | None = None,
) -> ExecutionResult:
    """Create a mock structure_pipeline result."""
    return ExecutionResult(
        success=True,
        data={
            "output": output or {},
            "metadata": metadata or {},
            "metrics": metrics or {},
        },
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestTaskEnumRegistered:
    """3-SANITY: Verify TaskName enum exists."""

    def test_task_enum_registered(self):
        assert hasattr(TaskName, "EXECUTE_STRUCTURE_TOOL")
        assert str(TaskName.EXECUTE_STRUCTURE_TOOL) == "execute_structure_tool"


class TestStructureToolPipeline:
    """Full pipeline dispatched as single structure_pipeline operation."""

    @patch(_PATCH_SHIM)
    @patch(_PATCH_FILE_STORAGE)
    @patch(_PATCH_PLATFORM_HELPER)
    @patch(_PATCH_DISPATCHER)
    def test_structure_tool_single_dispatch(
        self,
        MockDispatcher,
        mock_create_ph,
        mock_get_fs,
        MockShim,
        base_params,
        tool_metadata_regular,
        mock_fs,
        mock_platform_helper,
    ):
        """Single structure_pipeline dispatch for extract+index+answer."""
        from file_processing.structure_tool_task import (
            _execute_structure_tool_impl as execute_structure_tool,
        )

        mock_get_fs.return_value = mock_fs
        mock_create_ph.return_value = mock_platform_helper
        mock_platform_helper.get_prompt_studio_tool.return_value = {
            "tool_metadata": tool_metadata_regular,
        }

        dispatcher_instance = MagicMock()
        MockDispatcher.return_value = dispatcher_instance

        pipeline_result = _make_pipeline_result(
            output={"field_a": "$1M"},
            metadata={"run_id": "fexec-789", "file_name": "test.pdf"},
            metrics={"field_a": {"extraction_llm": {"tokens": 50}}},
        )
        dispatcher_instance.dispatch.return_value = pipeline_result

        result = execute_structure_tool(base_params)

        assert result["success"] is True
        assert result["data"]["output"]["field_a"] == "$1M"
        assert result["data"]["metadata"]["file_name"] == "test.pdf"
        mock_fs.json_dump.assert_called_once()

        # Single dispatch with structure_pipeline
        assert dispatcher_instance.dispatch.call_count == 1
        ctx = dispatcher_instance.dispatch.call_args[0][0]
        assert ctx.operation == "structure_pipeline"
        assert ctx.execution_source == "tool"
        assert ctx.executor_name == "legacy"

    @patch(_PATCH_SHIM)
    @patch(_PATCH_FILE_STORAGE)
    @patch(_PATCH_PLATFORM_HELPER)
    @patch(_PATCH_DISPATCHER)
    def test_pipeline_params_structure(
        self,
        MockDispatcher,
        mock_create_ph,
        mock_get_fs,
        MockShim,
        base_params,
        tool_metadata_regular,
        mock_fs,
        mock_platform_helper,
    ):
        """Verify executor_params contains all pipeline sub-params."""
        from file_processing.structure_tool_task import (
            _execute_structure_tool_impl as execute_structure_tool,
        )

        mock_get_fs.return_value = mock_fs
        mock_create_ph.return_value = mock_platform_helper
        mock_platform_helper.get_prompt_studio_tool.return_value = {
            "tool_metadata": tool_metadata_regular,
        }

        dispatcher_instance = MagicMock()
        MockDispatcher.return_value = dispatcher_instance
        dispatcher_instance.dispatch.return_value = _make_pipeline_result()

        execute_structure_tool(base_params)

        ctx = dispatcher_instance.dispatch.call_args[0][0]
        ep = ctx.executor_params

        # All required keys present
        assert "extract_params" in ep
        assert "index_template" in ep
        assert "answer_params" in ep
        assert "pipeline_options" in ep

        # Extract params
        assert ep["extract_params"]["file_path"] == "/data/test.pdf"

        # Index template
        assert ep["index_template"]["tool_id"] == "tool-123"
        assert ep["index_template"]["file_hash"] == "filehash123"

        # Answer params
        assert ep["answer_params"]["tool_id"] == "tool-123"
        assert ep["answer_params"]["run_id"] == "fexec-789"

        # Pipeline options (normal flow)
        opts = ep["pipeline_options"]
        assert opts["skip_extraction_and_indexing"] is False
        assert opts["is_summarization_enabled"] is False
        assert opts["is_single_pass_enabled"] is False
        assert opts["source_file_name"] == "test.pdf"


class TestStructureToolSinglePass:
    """Single-pass flag passed to pipeline_options."""

    @patch(_PATCH_SHIM)
    @patch(_PATCH_FILE_STORAGE)
    @patch(_PATCH_PLATFORM_HELPER)
    @patch(_PATCH_DISPATCHER)
    def test_structure_tool_single_pass(
        self,
        MockDispatcher,
        mock_create_ph,
        mock_get_fs,
        MockShim,
        base_params,
        tool_metadata_regular,
        mock_fs,
        mock_platform_helper,
    ):
        from file_processing.structure_tool_task import (
            _execute_structure_tool_impl as execute_structure_tool,
        )

        mock_get_fs.return_value = mock_fs
        mock_create_ph.return_value = mock_platform_helper
        mock_platform_helper.get_prompt_studio_tool.return_value = {
            "tool_metadata": tool_metadata_regular,
        }

        base_params["tool_instance_metadata"]["single_pass_extraction_mode"] = True

        dispatcher_instance = MagicMock()
        MockDispatcher.return_value = dispatcher_instance
        dispatcher_instance.dispatch.return_value = _make_pipeline_result(
            output={"field_a": "answer"},
        )

        result = execute_structure_tool(base_params)

        assert result["success"] is True
        # Single dispatch with is_single_pass_enabled flag
        assert dispatcher_instance.dispatch.call_count == 1
        ctx = dispatcher_instance.dispatch.call_args[0][0]
        assert ctx.operation == "structure_pipeline"
        opts = ctx.executor_params["pipeline_options"]
        assert opts["is_single_pass_enabled"] is True


class TestStructureToolSummarize:
    """Summarization params passed to pipeline."""

    @patch(_PATCH_SHIM)
    @patch(_PATCH_FILE_STORAGE)
    @patch(_PATCH_PLATFORM_HELPER)
    @patch(_PATCH_DISPATCHER)
    def test_structure_tool_summarize_flow(
        self,
        MockDispatcher,
        mock_create_ph,
        mock_get_fs,
        MockShim,
        base_params,
        tool_metadata_regular,
        mock_fs,
        mock_platform_helper,
    ):
        from file_processing.structure_tool_task import (
            _execute_structure_tool_impl as execute_structure_tool,
        )

        mock_get_fs.return_value = mock_fs
        mock_create_ph.return_value = mock_platform_helper
        mock_platform_helper.get_prompt_studio_tool.return_value = {
            "tool_metadata": tool_metadata_regular,
        }

        tool_metadata_regular["tool_settings"]["summarize_prompt"] = (
            "Summarize this doc"
        )
        base_params["tool_instance_metadata"]["summarize_as_source"] = True

        dispatcher_instance = MagicMock()
        MockDispatcher.return_value = dispatcher_instance
        dispatcher_instance.dispatch.return_value = _make_pipeline_result(
            output={"field_a": "answer"},
        )

        result = execute_structure_tool(base_params)

        assert result["success"] is True
        assert dispatcher_instance.dispatch.call_count == 1
        ctx = dispatcher_instance.dispatch.call_args[0][0]
        assert ctx.operation == "structure_pipeline"

        opts = ctx.executor_params["pipeline_options"]
        assert opts["is_summarization_enabled"] is True

        # Summarize params included
        sp = ctx.executor_params["summarize_params"]
        assert sp is not None
        assert sp["summarize_prompt"] == "Summarize this doc"
        assert sp["llm_adapter_instance_id"] == "llm-1"
        assert "extract_file_path" in sp
        assert "summarize_file_path" in sp


class TestStructureToolSmartTable:
    """Excel with valid JSON schema sets skip_extraction_and_indexing."""

    @patch(_PATCH_SHIM)
    @patch(_PATCH_FILE_STORAGE)
    @patch(_PATCH_PLATFORM_HELPER)
    @patch(_PATCH_DISPATCHER)
    def test_structure_tool_skip_extraction_smart_table(
        self,
        MockDispatcher,
        mock_create_ph,
        mock_get_fs,
        MockShim,
        base_params,
        tool_metadata_regular,
        mock_fs,
        mock_platform_helper,
    ):
        from file_processing.structure_tool_task import (
            _execute_structure_tool_impl as execute_structure_tool,
        )

        mock_get_fs.return_value = mock_fs
        mock_create_ph.return_value = mock_platform_helper

        tool_metadata_regular["outputs"][0]["table_settings"] = {
            "is_directory_mode": False,
        }
        tool_metadata_regular["outputs"][0]["prompt"] = '{"key": "value"}'

        mock_platform_helper.get_prompt_studio_tool.return_value = {
            "tool_metadata": tool_metadata_regular,
        }

        dispatcher_instance = MagicMock()
        MockDispatcher.return_value = dispatcher_instance
        dispatcher_instance.dispatch.return_value = _make_pipeline_result(
            output={"field_a": "table_answer"},
        )

        result = execute_structure_tool(base_params)

        assert result["success"] is True
        # Single pipeline dispatch with skip flag
        assert dispatcher_instance.dispatch.call_count == 1
        ctx = dispatcher_instance.dispatch.call_args[0][0]
        assert ctx.operation == "structure_pipeline"
        opts = ctx.executor_params["pipeline_options"]
        assert opts["skip_extraction_and_indexing"] is True


class TestStructureToolAgentic:
    """Agentic project routes to agentic_extraction."""

    @patch(_PATCH_SHIM)
    @patch(_PATCH_FILE_STORAGE)
    @patch(_PATCH_PLATFORM_HELPER)
    @patch(_PATCH_DISPATCHER)
    def test_structure_tool_agentic_routing(
        self,
        MockDispatcher,
        mock_create_ph,
        mock_get_fs,
        MockShim,
        base_params,
        mock_fs,
        mock_platform_helper,
    ):
        from file_processing.structure_tool_task import (
            _execute_structure_tool_impl as execute_structure_tool,
        )

        mock_get_fs.return_value = mock_fs
        mock_create_ph.return_value = mock_platform_helper

        # Prompt studio lookup fails, agentic succeeds
        mock_platform_helper.get_prompt_studio_tool.return_value = None

        agentic_metadata = {
            "name": "Agentic Project",
            "project_id": "ap-001",
            "json_schema": {"field": "string"},
        }
        mock_platform_helper.get_agentic_studio_tool.return_value = {
            "tool_metadata": agentic_metadata,
        }

        dispatcher_instance = MagicMock()
        MockDispatcher.return_value = dispatcher_instance

        # Agentic extraction currently fails (plugin not available)
        agentic_result = ExecutionResult.failure(
            error="Agentic extraction requires the agentic extraction plugin"
        )
        dispatcher_instance.dispatch.return_value = agentic_result

        result = execute_structure_tool(base_params)

        assert result["success"] is False
        assert "agentic" in result["error"].lower()

        # Should dispatch to agentic_extraction
        calls = dispatcher_instance.dispatch.call_args_list
        assert len(calls) == 1
        assert calls[0][0][0].operation == "agentic_extraction"


class TestStructureToolProfileOverrides:
    """Profile overrides modify tool_metadata before pipeline dispatch."""

    @patch(_PATCH_SHIM)
    @patch(_PATCH_FILE_STORAGE)
    @patch(_PATCH_PLATFORM_HELPER)
    @patch(_PATCH_DISPATCHER)
    def test_structure_tool_profile_overrides(
        self,
        MockDispatcher,
        mock_create_ph,
        mock_get_fs,
        MockShim,
        base_params,
        tool_metadata_regular,
        mock_fs,
        mock_platform_helper,
    ):
        from file_processing.structure_tool_task import (
            _execute_structure_tool_impl as execute_structure_tool,
        )

        mock_get_fs.return_value = mock_fs
        mock_create_ph.return_value = mock_platform_helper
        mock_platform_helper.get_prompt_studio_tool.return_value = {
            "tool_metadata": tool_metadata_regular,
        }

        base_params["exec_metadata"]["llm_profile_id"] = "profile-1"
        mock_platform_helper.get_llm_profile.return_value = {
            "profile_name": "Test Profile",
            "llm_id": "llm-override",
        }

        dispatcher_instance = MagicMock()
        MockDispatcher.return_value = dispatcher_instance
        dispatcher_instance.dispatch.return_value = _make_pipeline_result(
            output={"field_a": "answer"},
        )

        result = execute_structure_tool(base_params)

        assert result["success"] is True
        mock_platform_helper.get_llm_profile.assert_called_once_with("profile-1")
        assert tool_metadata_regular["tool_settings"]["llm"] == "llm-override"


class TestStructureToolPipelineFailure:
    """Pipeline failure propagated to caller."""

    @patch(_PATCH_SHIM)
    @patch(_PATCH_FILE_STORAGE)
    @patch(_PATCH_PLATFORM_HELPER)
    @patch(_PATCH_DISPATCHER)
    def test_structure_tool_pipeline_failure(
        self,
        MockDispatcher,
        mock_create_ph,
        mock_get_fs,
        MockShim,
        base_params,
        tool_metadata_regular,
        mock_fs,
        mock_platform_helper,
    ):
        from file_processing.structure_tool_task import (
            _execute_structure_tool_impl as execute_structure_tool,
        )

        mock_get_fs.return_value = mock_fs
        mock_create_ph.return_value = mock_platform_helper
        mock_platform_helper.get_prompt_studio_tool.return_value = {
            "tool_metadata": tool_metadata_regular,
        }

        dispatcher_instance = MagicMock()
        MockDispatcher.return_value = dispatcher_instance

        pipeline_failure = ExecutionResult.failure(
            error="X2Text adapter error: connection refused"
        )
        dispatcher_instance.dispatch.return_value = pipeline_failure

        result = execute_structure_tool(base_params)

        assert result["success"] is False
        assert "X2Text" in result["error"]
        assert dispatcher_instance.dispatch.call_count == 1


class TestStructureToolMultipleOutputs:
    """Multiple outputs are passed to executor in answer_params."""

    @patch(_PATCH_SHIM)
    @patch(_PATCH_FILE_STORAGE)
    @patch(_PATCH_PLATFORM_HELPER)
    @patch(_PATCH_DISPATCHER)
    def test_structure_tool_multiple_outputs(
        self,
        MockDispatcher,
        mock_create_ph,
        mock_get_fs,
        MockShim,
        base_params,
        tool_metadata_regular,
        mock_fs,
        mock_platform_helper,
    ):
        from file_processing.structure_tool_task import (
            _execute_structure_tool_impl as execute_structure_tool,
        )

        mock_get_fs.return_value = mock_fs
        mock_create_ph.return_value = mock_platform_helper

        # Add a second output with same chunking params
        second_output = dict(tool_metadata_regular["outputs"][0])
        second_output["name"] = "field_b"
        tool_metadata_regular["outputs"].append(second_output)

        mock_platform_helper.get_prompt_studio_tool.return_value = {
            "tool_metadata": tool_metadata_regular,
        }

        dispatcher_instance = MagicMock()
        MockDispatcher.return_value = dispatcher_instance
        dispatcher_instance.dispatch.return_value = _make_pipeline_result(
            output={"field_a": "a", "field_b": "b"},
        )

        result = execute_structure_tool(base_params)

        assert result["success"] is True
        # Single dispatch — index dedup handled inside executor
        assert dispatcher_instance.dispatch.call_count == 1
        ctx = dispatcher_instance.dispatch.call_args[0][0]
        outputs = ctx.executor_params["answer_params"]["outputs"]
        assert len(outputs) == 2
        assert outputs[0]["name"] == "field_a"
        assert outputs[1]["name"] == "field_b"


class TestStructureToolOutputWritten:
    """Output JSON written to correct path with correct structure."""

    @patch(_PATCH_SHIM)
    @patch(_PATCH_FILE_STORAGE)
    @patch(_PATCH_PLATFORM_HELPER)
    @patch(_PATCH_DISPATCHER)
    def test_structure_tool_output_written(
        self,
        MockDispatcher,
        mock_create_ph,
        mock_get_fs,
        MockShim,
        base_params,
        tool_metadata_regular,
        mock_fs,
        mock_platform_helper,
    ):
        from file_processing.structure_tool_task import (
            _execute_structure_tool_impl as execute_structure_tool,
        )

        mock_get_fs.return_value = mock_fs
        mock_create_ph.return_value = mock_platform_helper
        mock_platform_helper.get_prompt_studio_tool.return_value = {
            "tool_metadata": tool_metadata_regular,
        }

        dispatcher_instance = MagicMock()
        MockDispatcher.return_value = dispatcher_instance
        dispatcher_instance.dispatch.return_value = _make_pipeline_result(
            output={"field_a": "answer"},
        )

        result = execute_structure_tool(base_params)

        assert result["success"] is True

        # Check json_dump was called with correct path
        json_dump_call = mock_fs.json_dump.call_args
        output_path = json_dump_call.kwargs.get(
            "path", json_dump_call[1].get("path") if len(json_dump_call) > 1 else None
        )
        if output_path is None:
            output_path = json_dump_call[0][0] if json_dump_call[0] else None

        assert str(output_path).endswith("test.json")


class TestStructureToolMetadataFileName:
    """metadata.file_name in pipeline result preserved."""

    @patch(_PATCH_SHIM)
    @patch(_PATCH_FILE_STORAGE)
    @patch(_PATCH_PLATFORM_HELPER)
    @patch(_PATCH_DISPATCHER)
    def test_structure_tool_metadata_file_name(
        self,
        MockDispatcher,
        mock_create_ph,
        mock_get_fs,
        MockShim,
        base_params,
        tool_metadata_regular,
        mock_fs,
        mock_platform_helper,
    ):
        from file_processing.structure_tool_task import (
            _execute_structure_tool_impl as execute_structure_tool,
        )

        mock_get_fs.return_value = mock_fs
        mock_create_ph.return_value = mock_platform_helper
        mock_platform_helper.get_prompt_studio_tool.return_value = {
            "tool_metadata": tool_metadata_regular,
        }

        dispatcher_instance = MagicMock()
        MockDispatcher.return_value = dispatcher_instance
        dispatcher_instance.dispatch.return_value = _make_pipeline_result(
            output={"field_a": "answer"},
            metadata={"run_id": "123", "file_name": "test.pdf"},
        )

        result = execute_structure_tool(base_params)

        assert result["success"] is True
        assert result["data"]["metadata"]["file_name"] == "test.pdf"


class TestStructureToolNoSummarize:
    """No summarize_params when summarization is not enabled."""

    @patch(_PATCH_SHIM)
    @patch(_PATCH_FILE_STORAGE)
    @patch(_PATCH_PLATFORM_HELPER)
    @patch(_PATCH_DISPATCHER)
    def test_no_summarize_params_when_disabled(
        self,
        MockDispatcher,
        mock_create_ph,
        mock_get_fs,
        MockShim,
        base_params,
        tool_metadata_regular,
        mock_fs,
        mock_platform_helper,
    ):
        from file_processing.structure_tool_task import (
            _execute_structure_tool_impl as execute_structure_tool,
        )

        mock_get_fs.return_value = mock_fs
        mock_create_ph.return_value = mock_platform_helper
        mock_platform_helper.get_prompt_studio_tool.return_value = {
            "tool_metadata": tool_metadata_regular,
        }

        dispatcher_instance = MagicMock()
        MockDispatcher.return_value = dispatcher_instance
        dispatcher_instance.dispatch.return_value = _make_pipeline_result()

        execute_structure_tool(base_params)

        ctx = dispatcher_instance.dispatch.call_args[0][0]
        assert ctx.executor_params["summarize_params"] is None
        assert ctx.executor_params["pipeline_options"]["is_summarization_enabled"] is False


class TestWorkflowServiceDetection:
    """Test _is_structure_tool_workflow detection."""

    def test_is_structure_tool_detection(self):
        from shared.workflow.execution.service import (
            WorkerWorkflowExecutionService,
        )

        service = WorkerWorkflowExecutionService()

        # Mock execution_service with a structure tool instance
        mock_exec_service = MagicMock()
        ti = MagicMock()
        ti.image_name = "unstract/tool-structure"
        mock_exec_service.tool_instances = [ti]

        result = service._is_structure_tool_workflow(mock_exec_service)
        assert result is True

    def test_non_structure_tool_uses_docker(self):
        from shared.workflow.execution.service import (
            WorkerWorkflowExecutionService,
        )

        service = WorkerWorkflowExecutionService()

        # Mock execution_service with a non-structure tool
        mock_exec_service = MagicMock()
        ti = MagicMock()
        ti.image_name = "unstract/tool-classifier"
        mock_exec_service.tool_instances = [ti]

        result = service._is_structure_tool_workflow(mock_exec_service)
        assert result is False

    @patch.dict("os.environ", {"STRUCTURE_TOOL_IMAGE_NAME": "custom/structure"})
    def test_custom_structure_image_name(self):
        from shared.workflow.execution.service import (
            WorkerWorkflowExecutionService,
        )

        service = WorkerWorkflowExecutionService()

        mock_exec_service = MagicMock()
        ti = MagicMock()
        ti.image_name = "custom/structure"
        mock_exec_service.tool_instances = [ti]

        result = service._is_structure_tool_workflow(mock_exec_service)
        assert result is True


class TestStructureToolParamsPassthrough:
    """Task receives correct params from WorkerWorkflowExecutionService."""

    @patch(
        "shared.workflow.execution.service.WorkerWorkflowExecutionService."
        "_execute_structure_tool_workflow"
    )
    @patch(
        "shared.workflow.execution.service.WorkerWorkflowExecutionService."
        "_is_structure_tool_workflow",
        return_value=True,
    )
    def test_structure_tool_params_passthrough(
        self, mock_is_struct, mock_exec_struct
    ):
        from shared.workflow.execution.service import (
            WorkerWorkflowExecutionService,
        )

        service = WorkerWorkflowExecutionService()

        mock_exec_service = MagicMock()
        mock_exec_service.tool_instances = [MagicMock()]

        service._build_and_execute_workflow(mock_exec_service, "test.pdf")

        # Verify _execute_structure_tool_workflow was called
        mock_exec_struct.assert_called_once_with(
            mock_exec_service, "test.pdf"
        )


class TestHelperFunctions:
    """Test standalone helper functions."""

    def test_apply_profile_overrides(self):
        from file_processing.structure_tool_task import (
            _apply_profile_overrides,
        )

        tool_metadata = {
            "tool_settings": {
                "llm": "old-llm",
                "embedding": "old-emb",
            },
            "outputs": [
                {
                    "name": "field_a",
                    "llm": "old-llm",
                    "embedding": "old-emb",
                },
            ],
        }
        profile_data = {
            "llm_id": "new-llm",
            "embedding_model_id": "new-emb",
        }

        changes = _apply_profile_overrides(tool_metadata, profile_data)

        assert len(changes) == 4  # 2 in tool_settings + 2 in output
        assert tool_metadata["tool_settings"]["llm"] == "new-llm"
        assert tool_metadata["tool_settings"]["embedding"] == "new-emb"
        assert tool_metadata["outputs"][0]["llm"] == "new-llm"
        assert tool_metadata["outputs"][0]["embedding"] == "new-emb"

    def test_should_skip_extraction_no_table_settings(self):
        from file_processing.structure_tool_task import (
            _should_skip_extraction_for_smart_table,
        )

        outputs = [{"name": "field_a", "prompt": "What?"}]
        assert (
            _should_skip_extraction_for_smart_table("file.xlsx", outputs)
            is False
        )

    def test_should_skip_extraction_with_json_schema(self):
        from file_processing.structure_tool_task import (
            _should_skip_extraction_for_smart_table,
        )

        outputs = [
            {
                "name": "field_a",
                "table_settings": {},
                "prompt": '{"col1": "string", "col2": "number"}',
            }
        ]
        assert (
            _should_skip_extraction_for_smart_table("file.xlsx", outputs)
            is True
        )

