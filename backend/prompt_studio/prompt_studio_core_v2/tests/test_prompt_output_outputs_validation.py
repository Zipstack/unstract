"""UN-4017: prompt_output rejects a non-mapping ``outputs`` at the boundary.

``outputs`` is indexed by prompt key downstream — OutputManagerHelper.
handle_prompt_output_update does ``outputs.get(prompt.prompt_key)`` — so a list
raised AttributeError deep inside the helper and surfaced to the caller as a
bare 500 with no usable reason.

This is reachable from real traffic, not just a malformed client: single-pass
extraction passes the LLM's parsed JSON straight through as the outputs map,
and that parse returns a list whenever the model wraps its answer in prose, a
reasoning block, or a stray fence marker. Validating here means no future
executor can 500 the backend the same way.

NOTE: run via a Django-bootstrapped harness (no pytest-django in this repo yet;
CI-gating of these view tests is tracked in UN-3692). Verified locally green.
"""

import json
from unittest.mock import MagicMock, patch

from prompt_studio.prompt_studio_core_v2.internal_views import prompt_output

_VIEWS = "prompt_studio.prompt_studio_core_v2.internal_views"


def _request(outputs):
    request = MagicMock()
    # require_http_methods reads request.method; a MagicMock attribute is not
    # the string "POST" and the view short-circuits with 405.
    request.method = "POST"
    request.body = json.dumps(
        {
            "run_id": "run-1",
            "prompt_ids": ["p1"],
            "outputs": outputs,
            "document_id": "doc-1",
            "is_single_pass_extract": True,
        }
    )
    return request


def _body(response):
    return json.loads(response.content)


def test_list_outputs_rejected_with_400_and_a_reason():
    """The regression: this used to reach the helper and raise AttributeError."""
    response = prompt_output(_request([{"invoice_number": "INV-001"}, {"b": 2}]))
    assert response.status_code == 400
    body = _body(response)
    assert body["success"] is False
    assert "outputs must be a JSON object" in body["error"]
    assert "list" in body["error"]
    # A JSON array is valid JSON — the message must not imply it was malformed.
    assert "malformed" not in body["error"].lower()
    assert "invalid json" not in body["error"].lower()


def test_non_mapping_outputs_rejected():
    for outputs in ("a string", 42, True, [], [1, 2]):
        response = prompt_output(_request(outputs))
        assert response.status_code == 400, f"{outputs!r} was accepted"


def test_helper_is_never_reached_for_invalid_outputs():
    """Rejected at the boundary, before any ORM or helper work happens."""
    with patch(f"{_VIEWS}.status") as _status:
        _status.HTTP_400_BAD_REQUEST = 400
        with patch(
            "prompt_studio.prompt_studio_output_manager_v2."
            "output_manager_helper.OutputManagerHelper.handle_prompt_output_update"
        ) as handler:
            prompt_output(_request([{"a": 1}]))
    handler.assert_not_called()


def test_dict_outputs_still_reach_the_helper():
    """The guard must not reject the ordinary case."""
    with patch(
        "prompt_studio.prompt_studio_v2.models.ToolStudioPrompt.objects"
    ) as prompts, patch(
        "prompt_studio.prompt_studio_output_manager_v2."
        "output_manager_helper.OutputManagerHelper.handle_prompt_output_update"
    ) as handler:
        prompts.filter.return_value.order_by.return_value = []
        handler.return_value = []
        response = prompt_output(_request({"invoice_number": "INV-001"}))
    handler.assert_called_once()
    assert response.status_code == 200


def test_missing_outputs_defaults_to_empty_dict_and_is_accepted():
    """Absent `outputs` has always meant {}; the guard must not change that."""
    request = MagicMock()
    request.method = "POST"
    request.body = json.dumps({"prompt_ids": ["p1"], "document_id": "doc-1"})
    with patch(
        "prompt_studio.prompt_studio_v2.models.ToolStudioPrompt.objects"
    ) as prompts, patch(
        "prompt_studio.prompt_studio_output_manager_v2."
        "output_manager_helper.OutputManagerHelper.handle_prompt_output_update"
    ) as handler:
        prompts.filter.return_value.order_by.return_value = []
        handler.return_value = []
        response = prompt_output(request)
    assert response.status_code == 200
