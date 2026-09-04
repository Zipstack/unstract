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
"""

import json
from types import SimpleNamespace
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


def _resolved(*prompt_ids):
    """What the ORM returns on the happy path.

    prompt_output now compares resolved count to requested count — an org scope
    that drops rows must not answer 200 — so the accept-path stubs have to
    resolve every id they ask for. Only ``prompt_id`` is read on that path.
    """
    return [SimpleNamespace(prompt_id=pid) for pid in prompt_ids]


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


def test_non_mapping_metadata_rejected():
    """metadata is indexed five times at helper lines 135-139, before the
    `if not prompts` early exit — so it 500s even with valid outputs."""
    request = MagicMock()
    request.method = "POST"
    request.body = json.dumps(
        {
            "prompt_ids": ["p1"],
            "document_id": "doc-1",
            "outputs": {"invoice_number": "INV-001"},
            "metadata": [],
        }
    )
    response = prompt_output(request)
    assert response.status_code == 400
    assert "metadata must be a JSON object" in _body(response)["error"]


def test_non_mapping_outputs_rejected():
    for outputs in ("a string", 42, True, [], [1, 2]):
        response = prompt_output(_request(outputs))
        assert response.status_code == 400, f"{outputs!r} was accepted"


def test_helper_is_never_reached_for_invalid_outputs():
    """Rejected at the boundary, before any ORM or helper work happens.

    The ORM is patched so the assertion cannot pass by accident: without it,
    removing the guard makes `filter()` raise on the fake prompt id and the
    helper goes uncalled for the wrong reason.
    """
    with patch(
        "prompt_studio.prompt_studio_v2.models.ToolStudioPrompt.objects"
    ) as prompts, patch(
        "prompt_studio.prompt_studio_output_manager_v2."
        "output_manager_helper.OutputManagerHelper.handle_prompt_output_update"
    ) as handler:
        prompts.filter.return_value.order_by.return_value = []
        response = prompt_output(_request([{"a": 1}]))
    handler.assert_not_called()
    assert response.status_code == 400


def test_dict_outputs_still_reach_the_helper():
    """The guard must not reject the ordinary case."""
    with patch(
        "prompt_studio.prompt_studio_v2.models.ToolStudioPrompt.objects"
    ) as prompts, patch(
        "prompt_studio.prompt_studio_output_manager_v2."
        "output_manager_helper.OutputManagerHelper.handle_prompt_output_update"
    ) as handler:
        prompts.filter.return_value.order_by.return_value = _resolved("p1")
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
        prompts.filter.return_value.order_by.return_value = _resolved("p1")
        handler.return_value = []
        response = prompt_output(request)
    assert response.status_code == 200


# --- The in-backend execution path -------------------------------------
#
# prompt_studio_helper._handle_response is the other route to
# handle_prompt_output_update. It dispatches the same single_pass_extraction
# executor, so it receives the same shapes; guarding only the internal API
# would have left this path still able to 500.

from prompt_studio.prompt_studio_core_v2.exceptions import AnswerFetchError  # noqa: E402
from prompt_studio.prompt_studio_core_v2.prompt_studio_helper import (  # noqa: E402
    PromptStudioHelper,
)


def _handle(outputs, is_single_pass=True):
    return PromptStudioHelper._handle_response(
        response={"output": outputs, "metadata": {}, "status": "COMPLETED"},
        run_id="run-1",
        prompts=[],
        document_id="doc-1",
        is_single_pass=is_single_pass,
    )


def test_in_backend_path_rejects_a_list_with_422():
    try:
        _handle([{"invoice_number": "INV-001"}, {"b": 2}])
    except AnswerFetchError as exc:
        assert exc.status_code == 422
        assert "outputs map" in str(exc.detail)
    else:
        raise AssertionError("a list was accepted on the in-backend path")


def test_in_backend_single_pass_message_points_at_the_prompt():
    try:
        _handle([{"a": 1}], is_single_pass=True)
    except AnswerFetchError as exc:
        assert "all prompts share one response" in str(exc.detail)
    else:
        raise AssertionError("expected AnswerFetchError")


def test_in_backend_single_prompt_omits_the_single_pass_advice():
    """That advice is only true of single pass; it would misdirect otherwise."""
    try:
        _handle([{"a": 1}], is_single_pass=False)
    except AnswerFetchError as exc:
        assert "outputs map" in str(exc.detail)
        assert "all prompts share one response" not in str(exc.detail)
    else:
        raise AssertionError("expected AnswerFetchError")


def test_in_backend_path_still_accepts_a_dict():
    with patch(
        "prompt_studio.prompt_studio_output_manager_v2."
        "output_manager_helper.OutputManagerHelper.handle_prompt_output_update"
    ) as handler:
        handler.return_value = []
        _handle({"invoice_number": "INV-001"})
    handler.assert_called_once()


def test_metadata_rejection_does_not_tell_the_user_to_rephrase_a_prompt():
    """`metadata` is executor-assembled, never LLM output.

    Rewording a prompt cannot change it, so the single-pass advice would send
    the user down a dead end for a defect that is ours.
    """
    try:
        PromptStudioHelper._handle_response(
            response={"output": {"a": 1}, "metadata": [], "status": "COMPLETED"},
            run_id="run-1",
            prompts=[],
            document_id="doc-1",
            is_single_pass=True,
        )
    except AnswerFetchError as exc:
        detail = str(exc.detail)
        assert "metadata map" in detail
        assert "all prompts share one response" not in detail
        assert "Rephrase" not in detail
    else:
        raise AssertionError("non-dict metadata was accepted")
