"""Tests for the RetrievalService factory and complete-context path.

Retriever internals are NOT tested here — they're llama_index wrappers
that will be validated in Phase 2-SANITY integration tests.
"""

from unittest.mock import MagicMock, patch

import pytest

from executor.executors.constants import RetrievalStrategy
from executor.executors.retrieval import RetrievalService


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_output(prompt: str = "What is X?", top_k: int = 5, name: str = "field_a"):
    """Build a minimal ``output`` dict matching PromptServiceConstants keys."""
    return {
        "promptx": prompt,
        "similarity-top-k": top_k,
        "name": name,
    }


def _mock_retriever_class(return_value=None):
    """Return a mock class whose instances have a ``.retrieve()`` method."""
    if return_value is None:
        return_value = {"chunk1", "chunk2"}
    cls = MagicMock()
    instance = MagicMock()
    instance.retrieve.return_value = return_value
    cls.return_value = instance
    return cls, instance


# ---------------------------------------------------------------------------
# Factory — run_retrieval
# ---------------------------------------------------------------------------

class TestRunRetrieval:
    """Tests for RetrievalService.run_retrieval()."""

    @pytest.mark.parametrize("strategy", list(RetrievalStrategy))
    @patch("executor.executors.retrieval.RetrievalService._get_retriever_map")
    def test_correct_class_selected_for_each_strategy(self, mock_map, strategy):
        """Factory returns the correct retriever class for each strategy."""
        cls, _inst = _mock_retriever_class()
        mock_map.return_value = {strategy.value: cls}

        result = RetrievalService.run_retrieval(
            output=_make_output(),
            doc_id="doc-1",
            llm=MagicMock(),
            vector_db=MagicMock(),
            retrieval_type=strategy.value,
        )
        cls.assert_called_once()
        assert isinstance(result, list)

    @patch("executor.executors.retrieval.RetrievalService._get_retriever_map")
    def test_unknown_strategy_raises_value_error(self, mock_map):
        """Passing an invalid strategy string raises ValueError."""
        mock_map.return_value = {}

        with pytest.raises(ValueError, match="Unknown retrieval type"):
            RetrievalService.run_retrieval(
                output=_make_output(),
                doc_id="doc-1",
                llm=MagicMock(),
                vector_db=MagicMock(),
                retrieval_type="nonexistent",
            )

    @patch("executor.executors.retrieval.RetrievalService._get_retriever_map")
    def test_retriever_instantiated_with_correct_params(self, mock_map):
        """Verify vector_db, doc_id, prompt, top_k, llm passed through."""
        cls, _inst = _mock_retriever_class()
        mock_map.return_value = {RetrievalStrategy.SIMPLE.value: cls}

        llm = MagicMock(name="llm")
        vdb = MagicMock(name="vdb")
        output = _make_output(prompt="Find revenue", top_k=10, name="revenue")

        RetrievalService.run_retrieval(
            output=output,
            doc_id="doc-42",
            llm=llm,
            vector_db=vdb,
            retrieval_type=RetrievalStrategy.SIMPLE.value,
        )

        cls.assert_called_once_with(
            vector_db=vdb,
            doc_id="doc-42",
            prompt="Find revenue",
            top_k=10,
            llm=llm,
        )

    @patch("executor.executors.retrieval.RetrievalService._get_retriever_map")
    def test_retrieve_result_converted_to_list(self, mock_map):
        """Mock retriever returns a set; run_retrieval returns a list."""
        cls, _inst = _mock_retriever_class(return_value={"a", "b", "c"})
        mock_map.return_value = {RetrievalStrategy.FUSION.value: cls}

        result = RetrievalService.run_retrieval(
            output=_make_output(),
            doc_id="doc-1",
            llm=MagicMock(),
            vector_db=MagicMock(),
            retrieval_type=RetrievalStrategy.FUSION.value,
        )
        assert isinstance(result, list)
        assert set(result) == {"a", "b", "c"}

    @patch("executor.executors.retrieval.RetrievalService._get_retriever_map")
    def test_metrics_recorded(self, mock_map):
        """Verify context_retrieval_metrics dict populated with timing."""
        cls, _inst = _mock_retriever_class()
        mock_map.return_value = {RetrievalStrategy.SIMPLE.value: cls}

        metrics: dict = {}
        RetrievalService.run_retrieval(
            output=_make_output(name="my_field"),
            doc_id="doc-1",
            llm=MagicMock(),
            vector_db=MagicMock(),
            retrieval_type=RetrievalStrategy.SIMPLE.value,
            context_retrieval_metrics=metrics,
        )

        assert "my_field" in metrics
        assert "time_taken(s)" in metrics["my_field"]
        assert isinstance(metrics["my_field"]["time_taken(s)"], float)

    @patch("executor.executors.retrieval.RetrievalService._get_retriever_map")
    def test_metrics_optional_none_does_not_crash(self, mock_map):
        """context_retrieval_metrics=None doesn't crash."""
        cls, _inst = _mock_retriever_class()
        mock_map.return_value = {RetrievalStrategy.SIMPLE.value: cls}

        # Should not raise
        RetrievalService.run_retrieval(
            output=_make_output(),
            doc_id="doc-1",
            llm=MagicMock(),
            vector_db=MagicMock(),
            retrieval_type=RetrievalStrategy.SIMPLE.value,
            context_retrieval_metrics=None,
        )


# ---------------------------------------------------------------------------
# Complete context — retrieve_complete_context
# ---------------------------------------------------------------------------

class TestRetrieveCompleteContext:
    """Tests for RetrievalService.retrieve_complete_context()."""

    @patch("executor.executors.file_utils.FileUtils.get_fs_instance")
    def test_reads_file_with_correct_path(self, mock_get_fs):
        """Mock FileUtils.get_fs_instance, verify fs.read() called correctly."""
        mock_fs = MagicMock()
        mock_fs.read.return_value = "full document text"
        mock_get_fs.return_value = mock_fs

        RetrievalService.retrieve_complete_context(
            execution_source="ide",
            file_path="/data/doc.txt",
        )

        mock_get_fs.assert_called_once_with(execution_source="ide")
        mock_fs.read.assert_called_once_with(path="/data/doc.txt", mode="r")

    @patch("executor.executors.file_utils.FileUtils.get_fs_instance")
    def test_returns_list_with_single_item(self, mock_get_fs):
        """Verify [content] shape."""
        mock_fs = MagicMock()
        mock_fs.read.return_value = "hello world"
        mock_get_fs.return_value = mock_fs

        result = RetrievalService.retrieve_complete_context(
            execution_source="tool",
            file_path="/data/doc.txt",
        )

        assert result == ["hello world"]
        assert len(result) == 1

    @patch("executor.executors.file_utils.FileUtils.get_fs_instance")
    def test_complete_context_records_metrics(self, mock_get_fs):
        """Timing dict populated."""
        mock_fs = MagicMock()
        mock_fs.read.return_value = "content"
        mock_get_fs.return_value = mock_fs

        metrics: dict = {}
        RetrievalService.retrieve_complete_context(
            execution_source="ide",
            file_path="/data/doc.txt",
            context_retrieval_metrics=metrics,
            prompt_key="total_revenue",
        )

        assert "total_revenue" in metrics
        assert "time_taken(s)" in metrics["total_revenue"]
        assert isinstance(metrics["total_revenue"]["time_taken(s)"], float)

    @patch("executor.executors.file_utils.FileUtils.get_fs_instance")
    def test_complete_context_metrics_none_does_not_crash(self, mock_get_fs):
        """context_retrieval_metrics=None doesn't crash."""
        mock_fs = MagicMock()
        mock_fs.read.return_value = "content"
        mock_get_fs.return_value = mock_fs

        # Should not raise
        RetrievalService.retrieve_complete_context(
            execution_source="ide",
            file_path="/data/doc.txt",
            context_retrieval_metrics=None,
        )


# ---------------------------------------------------------------------------
# BaseRetriever interface
# ---------------------------------------------------------------------------

class TestBaseRetriever:
    """Tests for BaseRetriever base class."""

    def test_default_retrieve_returns_empty_set(self):
        """Default retrieve() returns empty set."""
        from executor.executors.retrievers.base_retriever import BaseRetriever

        r = BaseRetriever(
            vector_db=MagicMock(),
            prompt="test",
            doc_id="doc-1",
            top_k=5,
        )
        assert r.retrieve() == set()

    def test_constructor_stores_all_params(self):
        """Constructor stores vector_db, prompt, doc_id, top_k, llm."""
        from executor.executors.retrievers.base_retriever import BaseRetriever

        vdb = MagicMock(name="vdb")
        llm = MagicMock(name="llm")
        r = BaseRetriever(
            vector_db=vdb,
            prompt="my prompt",
            doc_id="doc-99",
            top_k=3,
            llm=llm,
        )
        assert r.vector_db is vdb
        assert r.prompt == "my prompt"
        assert r.doc_id == "doc-99"
        assert r.top_k == 3
        assert r.llm is llm

    def test_constructor_llm_defaults_to_none(self):
        """When llm not provided, it defaults to None."""
        from executor.executors.retrievers.base_retriever import BaseRetriever

        r = BaseRetriever(
            vector_db=MagicMock(),
            prompt="test",
            doc_id="doc-1",
            top_k=5,
        )
        assert r.llm is None
