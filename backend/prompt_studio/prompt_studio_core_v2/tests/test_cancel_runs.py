"""UN-1031: PromptStudioCoreView.cancel_runs.

The endpoint records an intent and returns; it never kills anything
synchronously. What matters here is that the ids it turns into signal-store
keys are validated (they come straight from a browser), that a per-prompt stop
stays per-prompt, and that a run whose intent could NOT be recorded is reported
as such — telling the user a still-running run was stopped is worse than
telling them the Stop failed.

NOTE: run via a Django-bootstrapped harness, same as ``test_task_status``.
"""

from unittest.mock import MagicMock, patch

import pytest
from prompt_studio.prompt_studio_core_v2 import views as _views_mod
from prompt_studio.prompt_studio_core_v2.exceptions import PromptRunCancelled
from prompt_studio.prompt_studio_core_v2.views import PromptStudioCoreView

_RUN_A = "11111111-1111-1111-1111-111111111111"
_RUN_B = "22222222-2222-2222-2222-222222222222"
_PROMPT = "33333333-3333-3333-3333-333333333333"

_PATCH_REQUEST_CANCEL = "prompt_studio.prompt_studio_core_v2.views.request_cancel"
_PATCH_ORG = (
    "prompt_studio.prompt_studio_core_v2.views.UserSessionUtils" ".get_organization_id"
)


def _view():
    view = PromptStudioCoreView()
    view.get_object = MagicMock()  # bypass permission/object lookup
    return view


def _call(runs, *, recorded=True):
    """Invoke the action with *runs* as the body; returns (response, mock)."""
    request = MagicMock()
    request.data = {"runs": runs} if runs is not None else {}
    with (
        patch(_PATCH_ORG, return_value="org-1"),
        patch(_PATCH_REQUEST_CANCEL, return_value=recorded) as cancel,
    ):
        response = _view().cancel_runs(request)
    return response, cancel


class TestCancelRuns:
    def test_whole_run_cancel_names_no_prompts(self):
        response, cancel = _call([{"run_id": _RUN_A}])

        assert response.status_code == 202
        assert response.data == {"cancelled": [_RUN_A], "failed": []}
        # None, not []: the run's shared extract/index stages stop too.
        cancel.assert_called_once_with("org-1", _RUN_A, None)

    def test_per_prompt_cancel_forwards_only_that_prompt(self):
        _, cancel = _call([{"run_id": _RUN_A, "prompt_ids": [_PROMPT]}])

        cancel.assert_called_once_with("org-1", _RUN_A, [_PROMPT])

    def test_several_runs_are_each_recorded(self):
        response, cancel = _call([{"run_id": _RUN_A}, {"run_id": _RUN_B}])

        assert cancel.call_count == 2
        assert response.data["cancelled"] == [_RUN_A, _RUN_B]

    def test_unrecordable_run_is_reported_as_failed(self):
        # Redis down: the run is still going. Saying otherwise would leave the
        # user believing they stopped work that keeps billing them.
        response, _ = _call([{"run_id": _RUN_A}], recorded=False)

        assert response.data == {"cancelled": [], "failed": [_RUN_A]}
        assert response.status_code == 202

    def test_org_scoping_comes_from_the_session_not_the_body(self):
        _, cancel = _call([{"run_id": _RUN_A, "org_id": "other-org"}])

        assert cancel.call_args[0][0] == "org-1"


class TestValidation:
    """Ids become signal-store keys, so they are validated, not trusted."""

    def test_missing_runs_is_rejected(self):
        response, cancel = _call(None)

        assert response.status_code == 400
        cancel.assert_not_called()

    def test_empty_runs_is_rejected(self):
        response, cancel = _call([])

        assert response.status_code == 400
        cancel.assert_not_called()

    def test_non_list_runs_is_rejected(self):
        request = MagicMock()
        request.data = {"runs": {"run_id": _RUN_A}}
        with (
            patch(_PATCH_ORG, return_value="org-1"),
            patch(_PATCH_REQUEST_CANCEL) as cancel,
        ):
            response = _view().cancel_runs(request)

        assert response.status_code == 400
        cancel.assert_not_called()

    def test_non_object_entry_is_rejected(self):
        response, cancel = _call([_RUN_A])

        assert response.status_code == 400
        cancel.assert_not_called()

    def test_malformed_run_id_is_rejected(self):
        response, cancel = _call([{"run_id": "../../etc/passwd"}])

        assert response.status_code == 400
        cancel.assert_not_called()

    def test_missing_run_id_is_rejected(self):
        response, cancel = _call([{"prompt_ids": [_PROMPT]}])

        assert response.status_code == 400
        cancel.assert_not_called()

    def test_malformed_prompt_id_is_rejected(self):
        response, cancel = _call([{"run_id": _RUN_A, "prompt_ids": ["not-a-uuid"]}])

        assert response.status_code == 400
        cancel.assert_not_called()

    def test_non_list_prompt_ids_is_rejected(self):
        response, cancel = _call([{"run_id": _RUN_A, "prompt_ids": _PROMPT}])

        assert response.status_code == 400
        cancel.assert_not_called()

    def test_nothing_is_recorded_when_a_later_entry_is_invalid(self):
        # All-or-nothing: a half-applied cancel would stop some runs and leave
        # the caller with no way to know which.
        response, cancel = _call([{"run_id": _RUN_A}, {"run_id": "nope"}])

        assert response.status_code == 400
        cancel.assert_not_called()


# ---------------------------------------------------------------------------
# The run endpoints' own response to a stop
# ---------------------------------------------------------------------------

_BUILDERS = {
    "fetch_response": "build_fetch_response_payload",
    "bulk_fetch_response": "build_bulk_fetch_response_payload",
    "single_pass_extraction": "build_single_pass_payload",
}


@pytest.mark.parametrize("action,builder", sorted(_BUILDERS.items()))
class TestRunEndpointsAnswerACancel:
    """A stop during the blocking stages unwinds the POST itself.

    Nothing was dispatched, so no callback and no socket event will ever fire
    for that run — this response is the only thing that can clear the
    frontend's spinner.
    """

    def _post(self, action, builder):
        request = MagicMock()
        request.data = {
            "id": _PROMPT,
            "prompt_ids": [_PROMPT],
            "document_id": "doc-1",
            "run_id": _RUN_A,
        }
        view = _view()
        with (
            patch(_PATCH_ORG, return_value="org-1"),
            patch.object(
                _views_mod.PromptStudioHelper,
                builder,
                side_effect=PromptRunCancelled("stopped"),
            ),
            patch.object(_views_mod, "ToolStudioPrompt") as prompt_model,
            patch.object(_views_mod, "DocumentManager") as doc_model,
            patch.object(_views_mod, "PromptStudioFileHelper") as file_helper,
            patch.object(
                _views_mod, "_multi_var_lookup_block_response", return_value=None
            ),
        ):
            prompt = MagicMock()
            prompt.enforce_type = "text"
            prompt.prompt_type = "PROMPT"
            prompt.active = True
            prompt.prompt = "q?"
            prompt_model.objects.get.return_value = prompt
            prompt_model.objects.filter.return_value.order_by.return_value = [prompt]
            doc_model.objects.get.return_value = MagicMock(document_name="a.pdf")
            file_helper.get_or_create_prompt_studio_subdirectory.return_value = "/docs"
            return getattr(view, action)(request, pk="tool-1")

    def test_returns_cancelled_rather_than_an_error(self, action, builder):
        response = self._post(action, builder)

        # 200, not 4xx/5xx: the user asked for this.
        assert response.status_code == 200
        assert response.data["status"] == "cancelled"

    def test_echoes_the_run_id_so_the_client_can_retire_it(self, action, builder):
        response = self._post(action, builder)

        assert response.data["run_id"] == _RUN_A
