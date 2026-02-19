"""Phase 3-SANITY — Integration tests for the structure tool Celery task.

Tests the full structure tool pipeline with mocked platform API and
ExecutionDispatcher. Validates that execute_structure_tool correctly
orchestrates extract → index → answer_prompt operations and writes
output to filesystem.
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


def _make_dispatch_side_effect(operation_results: dict):
    """Create a side_effect for dispatcher.dispatch that returns results by operation."""

    def side_effect(ctx, timeout=None):
        op = ctx.operation
        if op in operation_results:
            return operation_results[op]
        return ExecutionResult(success=True, data={})

    return side_effect


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestTaskEnumRegistered:
    """3-SANITY: Verify TaskName enum exists."""

    def test_task_enum_registered(self):
        assert hasattr(TaskName, "EXECUTE_STRUCTURE_TOOL")
        assert str(TaskName.EXECUTE_STRUCTURE_TOOL) == "execute_structure_tool"


class TestStructureToolExtractIndexAnswer:
    """Full pipeline: extract → index → answer_prompt."""

    @patch(_PATCH_SHIM)
    @patch(_PATCH_FILE_STORAGE)
    @patch(_PATCH_PLATFORM_HELPER)
    @patch(_PATCH_DISPATCHER)
    def test_structure_tool_extract_index_answer(
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
        """Full pipeline: extract → index → answer_prompt."""
        from file_processing.structure_tool_task import (
            _execute_structure_tool_impl as execute_structure_tool,
        )

        # Setup mocks
        mock_get_fs.return_value = mock_fs
        mock_create_ph.return_value = mock_platform_helper
        mock_platform_helper.get_prompt_studio_tool.return_value = {
            "tool_metadata": tool_metadata_regular,
        }

        dispatcher_instance = MagicMock()
        MockDispatcher.return_value = dispatcher_instance

        extract_result = ExecutionResult(
            success=True,
            data={"extracted_text": "Revenue is $1M"},
        )
        answer_result = ExecutionResult(
            success=True,
            data={
                "output": {"field_a": "$1M"},
                "metadata": {"run_id": "fexec-789"},
                "metrics": {"field_a": {"extraction_llm": {"tokens": 50}}},
            },
        )
        # extract, index, answer_prompt
        dispatcher_instance.dispatch.side_effect = [
            extract_result,
            ExecutionResult(success=True, data={"doc_id": "doc-1"}),
            answer_result,
        ]

        result = execute_structure_tool(base_params)

        assert result["success"] is True
        assert result["data"]["output"]["field_a"] == "$1M"
        assert result["data"]["metadata"]["file_name"] == "test.pdf"
        # Verify output was written
        mock_fs.json_dump.assert_called_once()

        # Verify dispatcher was called 3 times (extract, index, answer)
        assert dispatcher_instance.dispatch.call_count == 3
        calls = dispatcher_instance.dispatch.call_args_list
        assert calls[0][0][0].operation == "extract"
        assert calls[1][0][0].operation == "index"
        assert calls[2][0][0].operation == "answer_prompt"


class TestStructureToolSinglePass:
    """Single-pass flag skips indexing, uses single_pass_extraction."""

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

        # Enable single pass
        base_params["tool_instance_metadata"]["single_pass_extraction_mode"] = True

        dispatcher_instance = MagicMock()
        MockDispatcher.return_value = dispatcher_instance

        extract_result = ExecutionResult(
            success=True, data={"extracted_text": "text"}
        )
        answer_result = ExecutionResult(
            success=True,
            data={
                "output": {"field_a": "answer"},
                "metadata": {},
                "metrics": {},
            },
        )
        # extract, then single_pass_extraction (no index)
        dispatcher_instance.dispatch.side_effect = [
            extract_result,
            answer_result,
        ]

        result = execute_structure_tool(base_params)

        assert result["success"] is True
        # Should be 2 calls: extract + single_pass_extraction (no index)
        assert dispatcher_instance.dispatch.call_count == 2
        calls = dispatcher_instance.dispatch.call_args_list
        assert calls[0][0][0].operation == "extract"
        assert calls[1][0][0].operation == "single_pass_extraction"


class TestStructureToolSummarize:
    """Summarization path: extract → summarize → index → answer."""

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

        # Add summarize settings
        tool_metadata_regular["tool_settings"]["summarize_prompt"] = (
            "Summarize this doc"
        )
        base_params["tool_instance_metadata"]["summarize_as_source"] = True

        # Mock that extract file exists for reading
        mock_fs.exists.return_value = False  # No cached summary
        mock_fs.read.return_value = "Full extracted text"

        dispatcher_instance = MagicMock()
        MockDispatcher.return_value = dispatcher_instance

        extract_result = ExecutionResult(
            success=True, data={"extracted_text": "Full text"}
        )
        summarize_result = ExecutionResult(
            success=True, data={"data": "Summarized text"}
        )
        answer_result = ExecutionResult(
            success=True,
            data={
                "output": {"field_a": "answer"},
                "metadata": {},
                "metrics": {},
            },
        )
        dispatcher_instance.dispatch.side_effect = [
            extract_result,
            summarize_result,
            answer_result,
        ]

        result = execute_structure_tool(base_params)

        assert result["success"] is True
        # extract + summarize + answer (no index because summarize changes payload)
        assert dispatcher_instance.dispatch.call_count == 3
        calls = dispatcher_instance.dispatch.call_args_list
        assert calls[0][0][0].operation == "extract"
        assert calls[1][0][0].operation == "summarize"
        assert calls[2][0][0].operation == "answer_prompt"

        # Verify summarized text was written to cache
        mock_fs.write.assert_called()


class TestStructureToolSmartTable:
    """Excel with valid JSON schema skips extract and index."""

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

        # Add table_settings with a valid JSON prompt
        tool_metadata_regular["outputs"][0]["table_settings"] = {
            "is_directory_mode": False,
        }
        tool_metadata_regular["outputs"][0]["prompt"] = '{"key": "value"}'

        mock_platform_helper.get_prompt_studio_tool.return_value = {
            "tool_metadata": tool_metadata_regular,
        }

        dispatcher_instance = MagicMock()
        MockDispatcher.return_value = dispatcher_instance

        answer_result = ExecutionResult(
            success=True,
            data={
                "output": {"field_a": "table_answer"},
                "metadata": {},
                "metrics": {},
            },
        )
        # Only answer_prompt (skip extract and index)
        dispatcher_instance.dispatch.side_effect = [answer_result]

        result = execute_structure_tool(base_params)

        assert result["success"] is True
        # Only 1 call: answer_prompt (no extract, no index)
        assert dispatcher_instance.dispatch.call_count == 1
        calls = dispatcher_instance.dispatch.call_args_list
        assert calls[0][0][0].operation == "answer_prompt"


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
    """Profile overrides modify tool_metadata correctly."""

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

        # Add profile override
        base_params["exec_metadata"]["llm_profile_id"] = "profile-1"
        mock_platform_helper.get_llm_profile.return_value = {
            "profile_name": "Test Profile",
            "llm_id": "llm-override",
        }

        dispatcher_instance = MagicMock()
        MockDispatcher.return_value = dispatcher_instance

        extract_result = ExecutionResult(
            success=True, data={"extracted_text": "text"}
        )
        answer_result = ExecutionResult(
            success=True,
            data={
                "output": {"field_a": "answer"},
                "metadata": {},
                "metrics": {},
            },
        )
        dispatcher_instance.dispatch.side_effect = [
            extract_result,
            ExecutionResult(success=True, data={"doc_id": "d1"}),
            answer_result,
        ]

        result = execute_structure_tool(base_params)

        assert result["success"] is True
        # Verify profile override was applied
        mock_platform_helper.get_llm_profile.assert_called_once_with("profile-1")
        # The tool_settings should now have llm overridden
        assert tool_metadata_regular["tool_settings"]["llm"] == "llm-override"


class TestStructureToolExtractFailure:
    """Dispatcher extract failure → task returns failure."""

    @patch(_PATCH_SHIM)
    @patch(_PATCH_FILE_STORAGE)
    @patch(_PATCH_PLATFORM_HELPER)
    @patch(_PATCH_DISPATCHER)
    def test_structure_tool_extract_failure(
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

        extract_failure = ExecutionResult.failure(
            error="X2Text adapter error: connection refused"
        )
        dispatcher_instance.dispatch.return_value = extract_failure

        result = execute_structure_tool(base_params)

        assert result["success"] is False
        assert "X2Text" in result["error"]
        # Should only call extract, then bail
        assert dispatcher_instance.dispatch.call_count == 1


class TestStructureToolIndexDedup:
    """Same (chunk_size, overlap, vdb, emb) combo indexed only once."""

    @patch(_PATCH_SHIM)
    @patch(_PATCH_FILE_STORAGE)
    @patch(_PATCH_PLATFORM_HELPER)
    @patch(_PATCH_DISPATCHER)
    def test_structure_tool_index_dedup(
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

        extract_result = ExecutionResult(
            success=True, data={"extracted_text": "text"}
        )
        index_result = ExecutionResult(
            success=True, data={"doc_id": "d1"}
        )
        answer_result = ExecutionResult(
            success=True,
            data={
                "output": {"field_a": "a", "field_b": "b"},
                "metadata": {},
                "metrics": {},
            },
        )
        dispatcher_instance.dispatch.side_effect = [
            extract_result,
            index_result,  # Only ONE index call despite 2 outputs
            answer_result,
        ]

        result = execute_structure_tool(base_params)

        assert result["success"] is True
        # 3 calls: extract + 1 index (deduped) + answer
        assert dispatcher_instance.dispatch.call_count == 3
        index_calls = [
            c
            for c in dispatcher_instance.dispatch.call_args_list
            if c[0][0].operation == "index"
        ]
        assert len(index_calls) == 1


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

        extract_result = ExecutionResult(
            success=True, data={"extracted_text": "text"}
        )
        answer_result = ExecutionResult(
            success=True,
            data={
                "output": {"field_a": "answer"},
                "metadata": {},
                "metrics": {},
            },
        )
        dispatcher_instance.dispatch.side_effect = [
            extract_result,
            ExecutionResult(success=True, data={"doc_id": "d1"}),
            answer_result,
        ]

        result = execute_structure_tool(base_params)

        assert result["success"] is True

        # Check json_dump was called with correct path
        json_dump_call = mock_fs.json_dump.call_args
        output_path = json_dump_call.kwargs.get(
            "path", json_dump_call[1].get("path") if len(json_dump_call) > 1 else None
        )
        if output_path is None:
            # Try positional
            output_path = json_dump_call[0][0] if json_dump_call[0] else None

        # Verify it ends with test.json (stem of test.pdf)
        assert str(output_path).endswith("test.json")


class TestStructureToolMetadataFileName:
    """metadata.file_name replaced with actual source filename."""

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

        extract_result = ExecutionResult(
            success=True, data={"extracted_text": "text"}
        )
        answer_result = ExecutionResult(
            success=True,
            data={
                "output": {"field_a": "answer"},
                "metadata": {"run_id": "123"},
                "metrics": {},
            },
        )
        dispatcher_instance.dispatch.side_effect = [
            extract_result,
            ExecutionResult(success=True, data={"doc_id": "d1"}),
            answer_result,
        ]

        result = execute_structure_tool(base_params)

        assert result["success"] is True
        # file_name in metadata should be the source_file_name
        assert result["data"]["metadata"]["file_name"] == "test.pdf"


class TestStructureToolSummarizeCache:
    """Cached summary file skips dispatcher call."""

    @patch(_PATCH_SHIM)
    @patch(_PATCH_FILE_STORAGE)
    @patch(_PATCH_PLATFORM_HELPER)
    @patch(_PATCH_DISPATCHER)
    def test_summarize_cache_hit(
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

        tool_metadata_regular["tool_settings"]["summarize_prompt"] = (
            "Summarize"
        )
        mock_platform_helper.get_prompt_studio_tool.return_value = {
            "tool_metadata": tool_metadata_regular,
        }

        base_params["tool_instance_metadata"]["summarize_as_source"] = True

        # Simulate cached summary exists
        mock_fs.exists.return_value = True
        mock_fs.read.return_value = "Cached summary text"

        dispatcher_instance = MagicMock()
        MockDispatcher.return_value = dispatcher_instance

        extract_result = ExecutionResult(
            success=True, data={"extracted_text": "text"}
        )
        answer_result = ExecutionResult(
            success=True,
            data={
                "output": {"field_a": "from cache"},
                "metadata": {},
                "metrics": {},
            },
        )
        # extract + answer (no summarize call because cache hit)
        dispatcher_instance.dispatch.side_effect = [
            extract_result,
            answer_result,
        ]

        result = execute_structure_tool(base_params)

        assert result["success"] is True
        # Should be 2 calls: extract + answer (no summarize)
        assert dispatcher_instance.dispatch.call_count == 2
        ops = [c[0][0].operation for c in dispatcher_instance.dispatch.call_args_list]
        assert "summarize" not in ops


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

    def test_merge_metrics(self):
        from file_processing.structure_tool_task import _merge_metrics

        m1 = {"field_a": {"extraction_llm": {"tokens": 50}}}
        m2 = {"field_a": {"indexing": {"time_taken(s)": 1.5}}}
        merged = _merge_metrics(m1, m2)
        assert "extraction_llm" in merged["field_a"]
        assert "indexing" in merged["field_a"]

    def test_merge_metrics_empty(self):
        from file_processing.structure_tool_task import _merge_metrics

        assert _merge_metrics({}, {}) == {}
