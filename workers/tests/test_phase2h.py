"""Phase 2H: Tests for variable replacement and postprocessor modules.

Covers VariableReplacementHelper, VariableReplacementService, and
the webhook postprocessor — all pure Python with no llama_index deps.
"""

import json
from unittest.mock import MagicMock, patch

import pytest
import requests as real_requests

from executor.executors.constants import VariableConstants, VariableType
from executor.executors.exceptions import CustomDataError, LegacyExecutorError
from executor.executors.postprocessor import (
    _validate_structured_output,
    postprocess_data,
)
from executor.executors.variable_replacement import (
    VariableReplacementHelper,
    VariableReplacementService,
)


# ============================================================================
# 1. VariableReplacementHelper (15 tests)
# ============================================================================


class TestVariableReplacementHelper:
    """Tests for the low-level replacement helper."""

    # --- extract_variables_from_prompt ---

    def test_extract_variables_single(self):
        result = VariableReplacementHelper.extract_variables_from_prompt("{{name}}")
        assert result == ["name"]

    def test_extract_variables_multiple(self):
        result = VariableReplacementHelper.extract_variables_from_prompt(
            "{{a}} and {{b}}"
        )
        assert result == ["a", "b"]

    def test_extract_variables_none(self):
        result = VariableReplacementHelper.extract_variables_from_prompt("no vars here")
        assert result == []

    # --- identify_variable_type ---

    def test_identify_static_type(self):
        assert (
            VariableReplacementHelper.identify_variable_type("name")
            == VariableType.STATIC
        )

    def test_identify_dynamic_type(self):
        assert (
            VariableReplacementHelper.identify_variable_type(
                "https://example.com/api[field1]"
            )
            == VariableType.DYNAMIC
        )

    def test_identify_custom_data_type(self):
        assert (
            VariableReplacementHelper.identify_variable_type("custom_data.company")
            == VariableType.CUSTOM_DATA
        )

    # --- handle_json_and_str_types ---

    def test_handle_json_dict(self):
        result = VariableReplacementHelper.handle_json_and_str_types({"k": "v"})
        assert result == '{"k": "v"}'

    def test_handle_json_list(self):
        result = VariableReplacementHelper.handle_json_and_str_types([1, 2])
        assert result == "[1, 2]"

    # --- replace_generic_string_value ---

    def test_replace_generic_string_non_str(self):
        """Non-string values get JSON-formatted before replacement."""
        result = VariableReplacementHelper.replace_generic_string_value(
            prompt="value: {{x}}", variable="{{x}}", value={"nested": True}
        )
        assert result == 'value: {"nested": true}'

    # --- check_static_variable_run_status ---

    def test_check_static_missing_key(self):
        result = VariableReplacementHelper.check_static_variable_run_status(
            structure_output={}, variable="missing"
        )
        assert result is None

    # --- replace_static_variable ---

    def test_replace_static_missing_returns_prompt(self):
        """Missing key in structured_output leaves prompt unchanged."""
        prompt = "Total is {{revenue}}"
        result = VariableReplacementHelper.replace_static_variable(
            prompt=prompt, structured_output={}, variable="revenue"
        )
        assert result == prompt

    # --- replace_custom_data_variable ---

    def test_custom_data_nested_path(self):
        """custom_data.nested.key navigates nested dict."""
        result = VariableReplacementHelper.replace_custom_data_variable(
            prompt="val: {{custom_data.nested.key}}",
            variable="custom_data.nested.key",
            custom_data={"nested": {"key": "deep_value"}},
        )
        assert result == "val: deep_value"

    def test_custom_data_empty_dict_raises(self):
        """Empty custom_data={} raises CustomDataError."""
        with pytest.raises(CustomDataError, match="Custom data is not configured"):
            VariableReplacementHelper.replace_custom_data_variable(
                prompt="{{custom_data.company}}",
                variable="custom_data.company",
                custom_data={},
            )

    # --- fetch_dynamic_variable_value / replace_dynamic_variable ---

    @patch("executor.executors.variable_replacement.pyrequests.post")
    def test_dynamic_variable_success(self, mock_post):
        """Mock HTTP POST, verify URL extraction and replacement."""
        mock_resp = MagicMock()
        mock_resp.headers = {"content-type": "application/json"}
        mock_resp.json.return_value = {"result": "ok"}
        mock_resp.raise_for_status = MagicMock()
        mock_post.return_value = mock_resp

        variable = "https://example.com/api[field1]"
        result = VariableReplacementHelper.replace_dynamic_variable(
            prompt="data: {{" + variable + "}}",
            variable=variable,
            structured_output={"field1": "input_data"},
        )
        mock_post.assert_called_once()
        assert '{"result": "ok"}' in result

    @patch("executor.executors.variable_replacement.pyrequests.post")
    def test_dynamic_variable_http_error(self, mock_post):
        """HTTP error raises LegacyExecutorError."""
        mock_post.side_effect = real_requests.exceptions.ConnectionError("refused")

        with pytest.raises(LegacyExecutorError, match="failed"):
            VariableReplacementHelper.fetch_dynamic_variable_value(
                url="https://example.com/api", data="payload"
            )


# ============================================================================
# 2. VariableReplacementService (8 tests)
# ============================================================================


class TestVariableReplacementService:
    """Tests for the high-level orchestration service."""

    def test_replace_with_variable_map(self):
        """Uses variable_map key from prompt dict when present."""
        prompt = {
            "prompt": "Hello {{name}}",
            "variable_map": {"name": "World"},
        }
        result = VariableReplacementService.replace_variables_in_prompt(
            prompt=prompt,
            structured_output={"name": "Fallback"},
            prompt_name="test",
        )
        assert result == "Hello World"

    def test_replace_fallback_structured_output(self):
        """Falls back to structured_output when no variable_map."""
        prompt = {"prompt": "Hello {{name}}"}
        result = VariableReplacementService.replace_variables_in_prompt(
            prompt=prompt,
            structured_output={"name": "Fallback"},
            prompt_name="test",
        )
        assert result == "Hello Fallback"

    def test_mixed_variable_types(self):
        """Prompt with static + custom_data variables replaces both."""
        prompt = {
            "prompt": "{{name}} works at {{custom_data.company}}",
            "variable_map": {"name": "Alice"},
        }
        result = VariableReplacementService.replace_variables_in_prompt(
            prompt=prompt,
            structured_output={},
            prompt_name="test",
            custom_data={"company": "Acme"},
        )
        assert result == "Alice works at Acme"

    def test_no_variables_noop(self):
        """Prompt without {{}} returns unchanged."""
        prompt = {"prompt": "No variables here"}
        result = VariableReplacementService.replace_variables_in_prompt(
            prompt=prompt,
            structured_output={},
            prompt_name="test",
        )
        assert result == "No variables here"

    def test_replace_with_custom_data(self):
        """custom_data dict gets passed through to helper."""
        prompt = {
            "prompt": "Company: {{custom_data.name}}",
            "variable_map": {},
        }
        result = VariableReplacementService.replace_variables_in_prompt(
            prompt=prompt,
            structured_output={},
            prompt_name="test",
            custom_data={"name": "TestCorp"},
        )
        assert result == "Company: TestCorp"

    def test_is_ide_flag_propagated(self):
        """is_ide=False propagates — error message says 'API request'."""
        prompt = {
            "prompt": "{{custom_data.missing}}",
            "variable_map": {},
        }
        with pytest.raises(CustomDataError, match="API request"):
            VariableReplacementService.replace_variables_in_prompt(
                prompt=prompt,
                structured_output={},
                prompt_name="test",
                custom_data={},
                is_ide=False,
            )

    def test_multiple_same_variable(self):
        """{{x}} and {{x}} — both occurrences replaced."""
        prompt = {
            "prompt": "{{x}} and {{x}}",
            "variable_map": {"x": "val"},
        }
        result = VariableReplacementService.replace_variables_in_prompt(
            prompt=prompt,
            structured_output={},
            prompt_name="test",
        )
        assert result == "val and val"

    def test_json_value_replacement(self):
        """Dict value gets JSON-serialized before replacement."""
        prompt = {
            "prompt": "data: {{info}}",
            "variable_map": {"info": {"key": "value"}},
        }
        result = VariableReplacementService.replace_variables_in_prompt(
            prompt=prompt,
            structured_output={},
            prompt_name="test",
        )
        assert result == 'data: {"key": "value"}'


# ============================================================================
# 3. Postprocessor (15 tests)
# ============================================================================


class TestPostprocessor:
    """Tests for the webhook postprocessor."""

    PARSED = {"field": "original"}
    HIGHLIGHT = [{"page": 1, "spans": []}]

    # --- disabled / no-op paths ---

    def test_disabled_returns_original(self):
        result = postprocess_data(
            parsed_data=self.PARSED,
            webhook_enabled=False,
            highlight_data=self.HIGHLIGHT,
        )
        assert result == (self.PARSED, self.HIGHLIGHT)

    def test_no_url_returns_original(self):
        result = postprocess_data(
            parsed_data=self.PARSED,
            webhook_enabled=True,
            webhook_url=None,
            highlight_data=self.HIGHLIGHT,
        )
        assert result == (self.PARSED, self.HIGHLIGHT)

    # --- successful webhook ---

    @patch("executor.executors.postprocessor.requests.post")
    def test_success_returns_updated(self, mock_post):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"structured_output": {"field": "updated"}}
        mock_post.return_value = mock_resp

        result = postprocess_data(
            parsed_data=self.PARSED,
            webhook_enabled=True,
            webhook_url="https://hook.example.com",
            highlight_data=self.HIGHLIGHT,
        )
        assert result[0] == {"field": "updated"}

    @patch("executor.executors.postprocessor.requests.post")
    def test_success_preserves_highlight_data(self, mock_post):
        """Response without highlight_data preserves original."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"structured_output": {"f": "v"}}
        mock_post.return_value = mock_resp

        _, highlight = postprocess_data(
            parsed_data=self.PARSED,
            webhook_enabled=True,
            webhook_url="https://hook.example.com",
            highlight_data=self.HIGHLIGHT,
        )
        assert highlight == self.HIGHLIGHT

    @patch("executor.executors.postprocessor.requests.post")
    def test_success_updates_highlight_data(self, mock_post):
        """Response with valid list highlight_data uses updated."""
        new_highlight = [{"page": 2}]
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "structured_output": {"f": "v"},
            "highlight_data": new_highlight,
        }
        mock_post.return_value = mock_resp

        _, highlight = postprocess_data(
            parsed_data=self.PARSED,
            webhook_enabled=True,
            webhook_url="https://hook.example.com",
            highlight_data=self.HIGHLIGHT,
        )
        assert highlight == new_highlight

    @patch("executor.executors.postprocessor.requests.post")
    def test_invalid_highlight_data_ignored(self, mock_post):
        """Response with non-list highlight_data keeps original."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "structured_output": {"f": "v"},
            "highlight_data": "not-a-list",
        }
        mock_post.return_value = mock_resp

        _, highlight = postprocess_data(
            parsed_data=self.PARSED,
            webhook_enabled=True,
            webhook_url="https://hook.example.com",
            highlight_data=self.HIGHLIGHT,
        )
        assert highlight == self.HIGHLIGHT

    # --- response validation failures ---

    @patch("executor.executors.postprocessor.requests.post")
    def test_missing_structured_output_key(self, mock_post):
        """Response without structured_output returns original."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"other_key": "value"}
        mock_post.return_value = mock_resp

        result = postprocess_data(
            parsed_data=self.PARSED,
            webhook_enabled=True,
            webhook_url="https://hook.example.com",
            highlight_data=self.HIGHLIGHT,
        )
        assert result == (self.PARSED, self.HIGHLIGHT)

    @patch("executor.executors.postprocessor.requests.post")
    def test_invalid_structured_output_type(self, mock_post):
        """Response with string structured_output returns original."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"structured_output": "just-a-string"}
        mock_post.return_value = mock_resp

        result = postprocess_data(
            parsed_data=self.PARSED,
            webhook_enabled=True,
            webhook_url="https://hook.example.com",
            highlight_data=self.HIGHLIGHT,
        )
        assert result == (self.PARSED, self.HIGHLIGHT)

    # --- HTTP error paths ---

    @patch("executor.executors.postprocessor.requests.post")
    def test_http_error_returns_original(self, mock_post):
        mock_resp = MagicMock()
        mock_resp.status_code = 500
        mock_post.return_value = mock_resp

        result = postprocess_data(
            parsed_data=self.PARSED,
            webhook_enabled=True,
            webhook_url="https://hook.example.com",
            highlight_data=self.HIGHLIGHT,
        )
        assert result == (self.PARSED, self.HIGHLIGHT)

    @patch("executor.executors.postprocessor.requests.post")
    def test_timeout_returns_original(self, mock_post):
        mock_post.side_effect = real_requests.exceptions.Timeout("timed out")

        result = postprocess_data(
            parsed_data=self.PARSED,
            webhook_enabled=True,
            webhook_url="https://hook.example.com",
            highlight_data=self.HIGHLIGHT,
        )
        assert result == (self.PARSED, self.HIGHLIGHT)

    @patch("executor.executors.postprocessor.requests.post")
    def test_connection_error_returns_original(self, mock_post):
        mock_post.side_effect = real_requests.exceptions.ConnectionError("refused")

        result = postprocess_data(
            parsed_data=self.PARSED,
            webhook_enabled=True,
            webhook_url="https://hook.example.com",
            highlight_data=self.HIGHLIGHT,
        )
        assert result == (self.PARSED, self.HIGHLIGHT)

    @patch("executor.executors.postprocessor.requests.post")
    def test_json_decode_error_returns_original(self, mock_post):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.side_effect = json.JSONDecodeError("err", "doc", 0)
        mock_post.return_value = mock_resp

        result = postprocess_data(
            parsed_data=self.PARSED,
            webhook_enabled=True,
            webhook_url="https://hook.example.com",
            highlight_data=self.HIGHLIGHT,
        )
        assert result == (self.PARSED, self.HIGHLIGHT)

    @patch("executor.executors.postprocessor.requests.post")
    def test_custom_timeout_passed(self, mock_post):
        """timeout=5.0 is passed to requests.post()."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"structured_output": {"f": "v"}}
        mock_post.return_value = mock_resp

        postprocess_data(
            parsed_data=self.PARSED,
            webhook_enabled=True,
            webhook_url="https://hook.example.com",
            timeout=5.0,
        )
        _, kwargs = mock_post.call_args
        assert kwargs["timeout"] == 5.0

    # --- _validate_structured_output ---

    def test_validate_structured_output_dict(self):
        assert _validate_structured_output({"k": "v"}) is True

    def test_validate_structured_output_list(self):
        assert _validate_structured_output([1, 2]) is True
