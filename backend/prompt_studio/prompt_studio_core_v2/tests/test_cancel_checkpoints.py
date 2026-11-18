"""UN-1031: cancel checkpoints in the blocking (Phase A) stages.

Extraction and indexing run synchronously inside the Django request thread, so
a Stop during them has to unwind the request itself — no callback will ever
fire for work that was never dispatched. Two things must hold:

* the document's indexing flag is cleared on the way out (left set, it blocks
  every prompt on that document for INDEXING_FLAG_TTL);
* a stop is not recorded as an extraction failure, which would leave a bogus
  error on the document and make the next run believe extraction was tried.

Unit tests: collaborators are patched on the helper module, no DB is touched.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from prompt_studio.prompt_studio_core_v2 import prompt_studio_helper as _psh_mod
from prompt_studio.prompt_studio_core_v2.exceptions import PromptRunCancelled

from unstract.core.prompt_run_cancellation import PROMPT_RUN_CANCELLED_ERROR

PromptStudioHelper = _psh_mod.PromptStudioHelper

_ORG = "org-1"
_RUN = "run-1"
_DOC_KEY = "doc-key-1"


def _profile(chunk_size=512):
    profile = MagicMock(name="ProfileManager")
    profile.chunk_size = chunk_size
    profile.chunk_overlap = 64
    profile.embedding_model.id = "emb-1"
    profile.vector_store.id = "vdb-1"
    profile.x2text.id = "x2t-1"
    profile.x2text.metadata = {"model": "default"}
    return profile


class TestRaiseIfCancelled:
    def test_raises_the_shared_sentinel(self):
        with patch.object(_psh_mod, "is_cancelled", return_value=True):
            with pytest.raises(PromptRunCancelled) as exc:
                PromptStudioHelper._raise_if_cancelled(_ORG, _RUN)
        assert str(exc.value) == PROMPT_RUN_CANCELLED_ERROR

    def test_passes_through_when_not_cancelled(self):
        with patch.object(_psh_mod, "is_cancelled", return_value=False):
            PromptStudioHelper._raise_if_cancelled(_ORG, _RUN)  # must not raise

    def test_no_run_id_is_a_no_op(self):
        with patch.object(_psh_mod, "is_cancelled") as is_cancelled:
            PromptStudioHelper._raise_if_cancelled(_ORG, None)
        is_cancelled.assert_not_called()


class TestIndexerCancel:
    """The indexing flag MUST be cleared however the stage exits."""

    def _run_indexer(self, cancelled_at):
        """Drive dynamic_indexer with the cancel firing at *cancelled_at*."""
        calls = {"n": 0}

        def _raise_if_cancelled(org_id, run_id):
            calls["n"] += 1
            if calls["n"] >= cancelled_at:
                raise PromptRunCancelled(PROMPT_RUN_CANCELLED_ERROR)

        with (
            patch.object(
                PromptStudioHelper, "_raise_if_cancelled", side_effect=_raise_if_cancelled
            ),
            patch.object(_psh_mod, "DocumentIndexingService") as indexing_service,
            patch.object(_psh_mod, "PromptStudioIndexHelper"),
            patch.object(PromptStudioHelper, "_get_platform_api_key", return_value="pk"),
            patch.object(PromptStudioHelper, "_get_dispatcher") as dispatcher,
        ):
            indexing_service.get_indexed_document_id.return_value = None
            dispatcher.return_value.dispatch.return_value = MagicMock(
                success=True, data={"doc_id": "doc-1"}
            )
            with patch.object(
                PromptStudioHelper, "_wait_for_indexing", return_value=None
            ):
                with pytest.raises(PromptRunCancelled):
                    PromptStudioHelper.dynamic_indexer(
                        profile_manager=_profile(),
                        tool_id="tool-1",
                        file_path="/tmp/doc.pdf",
                        org_id=_ORG,
                        document_id="doc-1",
                        user_id="user-1",
                        extracted_text="text",
                        run_id=_RUN,
                        doc_id_key=_DOC_KEY,
                    )
            return indexing_service, dispatcher

    def test_clears_the_indexing_flag_on_cancel(self):
        indexing_service, _ = self._run_indexer(cancelled_at=1)

        indexing_service.remove_document_indexing.assert_called_once_with(
            org_id=_ORG, user_id="user-1", doc_id_key=_DOC_KEY
        )

    def test_does_not_dispatch_the_index_work(self):
        _, dispatcher = self._run_indexer(cancelled_at=1)

        dispatcher.return_value.dispatch.assert_not_called()

    def test_a_stop_while_waiting_leaves_another_request_s_flag_alone(self):
        """The flag we are waiting ON belongs to a different request.

        Clearing it here would let a third caller conclude nothing is indexing
        and start a duplicate index — duplicate embedding spend and duplicate
        vector writes — while the original request is still working.
        """
        with (
            patch.object(_psh_mod, "DocumentIndexingService") as indexing_service,
            patch.object(_psh_mod, "PromptStudioIndexHelper"),
            patch.object(
                PromptStudioHelper,
                "_wait_for_indexing",
                side_effect=PromptRunCancelled(PROMPT_RUN_CANCELLED_ERROR),
            ),
        ):
            indexing_service.get_indexed_document_id.return_value = None
            with pytest.raises(PromptRunCancelled):
                PromptStudioHelper.dynamic_indexer(
                    profile_manager=_profile(),
                    tool_id="tool-1",
                    file_path="/tmp/doc.pdf",
                    org_id=_ORG,
                    document_id="doc-1",
                    user_id="user-1",
                    extracted_text="text",
                    run_id=_RUN,
                    doc_id_key=_DOC_KEY,
                )

            indexing_service.remove_document_indexing.assert_not_called()

    def test_executor_reported_cancel_becomes_a_cancel_not_an_index_error(self):
        with (
            patch.object(PromptStudioHelper, "_raise_if_cancelled"),
            patch.object(_psh_mod, "DocumentIndexingService") as indexing_service,
            patch.object(_psh_mod, "PromptStudioIndexHelper"),
            patch.object(PromptStudioHelper, "_get_platform_api_key", return_value="pk"),
            patch.object(PromptStudioHelper, "_get_dispatcher") as dispatcher,
            patch.object(PromptStudioHelper, "_wait_for_indexing", return_value=None),
        ):
            indexing_service.get_indexed_document_id.return_value = None
            dispatcher.return_value.dispatch.return_value = MagicMock(
                success=False, error=PROMPT_RUN_CANCELLED_ERROR
            )
            with pytest.raises(PromptRunCancelled):
                PromptStudioHelper.dynamic_indexer(
                    profile_manager=_profile(),
                    tool_id="tool-1",
                    file_path="/tmp/doc.pdf",
                    org_id=_ORG,
                    document_id="doc-1",
                    user_id="user-1",
                    extracted_text="text",
                    run_id=_RUN,
                    doc_id_key=_DOC_KEY,
                )
            indexing_service.remove_document_indexing.assert_called_once()


class TestExtractorCancel:
    def _run_extractor(self, *, dispatch_result, cancel_before=False):
        with (
            patch.object(
                PromptStudioHelper,
                "_raise_if_cancelled",
                side_effect=PromptRunCancelled(PROMPT_RUN_CANCELLED_ERROR)
                if cancel_before
                else None,
            ),
            patch.object(_psh_mod, "PromptStudioIndexHelper") as index_helper,
            patch.object(PromptStudioHelper, "_get_platform_api_key", return_value="pk"),
            patch.object(PromptStudioHelper, "_get_dispatcher") as dispatcher,
        ):
            index_helper.check_extraction_status.return_value = False
            dispatcher.return_value.dispatch.return_value = dispatch_result
            with pytest.raises(PromptRunCancelled):
                PromptStudioHelper.dynamic_extractor(
                    file_path="/tmp/doc.pdf",
                    enable_highlight=False,
                    run_id=_RUN,
                    org_id=_ORG,
                    profile_manager=_profile(),
                    document_id="doc-1",
                )
            return index_helper, dispatcher

    def test_stops_before_the_billable_extraction(self):
        _, dispatcher = self._run_extractor(
            dispatch_result=MagicMock(success=True), cancel_before=True
        )

        dispatcher.return_value.dispatch.assert_not_called()

    def test_cancel_is_not_recorded_as_an_extraction_failure(self):
        index_helper, _ = self._run_extractor(
            dispatch_result=MagicMock(success=False, error=PROMPT_RUN_CANCELLED_ERROR)
        )

        # mark_extraction_status(extracted=False) would persist the cancel text
        # as the document's extraction error.
        index_helper.mark_extraction_status.assert_not_called()
