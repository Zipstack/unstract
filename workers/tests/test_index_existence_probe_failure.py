"""A failed "already indexed?" check must not lead to a second write (worker path).

Path under test: LegacyExecutor._handle_index -> executor.executors.index.Index
.is_document_indexed -> Index.perform_indexing. Only a 404 from the vector DB (a
Qdrant collection that has not been created yet, i.e. the first index) means "not
indexed". Any other VectorDBError, such as a timeout, has to fail the run instead of
falling through to a second write of the same document.

What is real: the worker's Index, sdk1's VectorDB and Qdrant adapter class (including
its error parsing), llama-index's QdrantVectorStore and qdrant-client, on
qdrant-client's local in-memory backend. No server, no network.

What is stood in: embeddings (llama-index MockEmbedding), the indexing-deps factory,
file-system and platform adapter lookups. The only injected failure is one
QdrantClient.query_points call.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any
from unittest.mock import MagicMock, patch

import httpx
import pytest
from llama_index.core.embeddings import MockEmbedding
from qdrant_client import QdrantClient
from qdrant_client.http import models as rest
from qdrant_client.http.exceptions import ResponseHandlingException, UnexpectedResponse

from unstract.sdk1.exceptions import VectorDBError
from unstract.sdk1.execution.context import ExecutionContext
from unstract.sdk1.execution.registry import ExecutorRegistry
from unstract.sdk1.execution.result import ExecutionResult

EMBED_DIM = 8
TEXT = " ".join(
    f"Clause {i}. The supplier shall deliver item {i} within {i + 2} business days of the "
    f"purchase order, and invoices for item {i} are payable net {30 + i} days."
    for i in range(1, 41)
)


class _Embedding(MockEmbedding):
    """MockEmbedding plus the attribute Unstract's code reads off EmbeddingCompat."""

    def flush_pending_usage(self) -> list:
        return []


class _RecordingTool:
    """Minimal tool: Index only calls stream_log on it."""

    def __init__(self) -> None:
        self.logs: list[tuple[str, str]] = []

    def stream_log(self, log: str, level: Any = None, **kwargs: Any) -> None:
        self.logs.append((str(getattr(level, "value", level) or "INFO"), log))


def _make_embedding() -> _Embedding:
    emb = _Embedding(embed_dim=EMBED_DIM)
    object.__setattr__(emb, "_length", EMBED_DIM)  # VectorDB reads embedding._length
    return emb


def _make_vector_db(
    tool: _RecordingTool, embedding: _Embedding
) -> tuple[Any, QdrantClient, str]:
    """sdk1's real VectorDB around sdk1's real Qdrant adapter on a local Qdrant."""
    from unstract.sdk1.adapters.vectordb.qdrant.src import qdrant as qdrant_mod
    from unstract.sdk1.vector_db import VectorDB

    local = QdrantClient(location=":memory:")
    # The adapter always passes url=; point its client constructor at the local backend.
    with patch.object(qdrant_mod, "QdrantClient", return_value=local):
        adapter = qdrant_mod.Qdrant(
            {"collection_name": "unstract_test", "embedding_dimension": EMBED_DIM}
        )
    # A server keeps its data when a client closes; the in-memory backend would not.
    adapter.close = lambda **kw: None

    vdb = VectorDB.__new__(VectorDB)
    vdb._tool = tool
    vdb._adapter_instance_id = None
    vdb._embedding_instance = embedding
    vdb._embedding_dimension = EMBED_DIM
    vdb._vector_db_instance = adapter.get_vector_db_instance()
    vdb.vector_db_adapter_class = adapter
    vdb._adapter_name = "Qdrant"
    return vdb, local, adapter._collection_name


def _point_ids(client: QdrantClient, collection: str, doc_id: str) -> set[str]:
    """Ids of the points stored under this doc_id, read straight from Qdrant."""
    if not client.collection_exists(collection):
        return set()
    flt = rest.Filter(
        must=[rest.FieldCondition(key="doc_id", match=rest.MatchValue(value=doc_id))]
    )
    points, _ = client.scroll(collection, scroll_filter=flt, limit=10_000)
    return {str(p.id) for p in points}


def _read_timeout() -> Exception:
    """What qdrant-client raises when a request times out."""
    return ResponseHandlingException(httpx.ReadTimeout("timed out"))


def _collection_not_found(collection: str) -> Exception:
    """What qdrant-client raises when a Qdrant server answers 404 for a missing collection.

    Injected because the in-memory backend raises ValueError for a missing collection
    instead of the 404 a server returns.
    """
    return UnexpectedResponse(
        status_code=404,
        reason_phrase="Not Found",
        content=(
            b'{"status":{"error":"Not found: Collection `'
            + collection.encode()
            + b"` doesn't exist!\"},\"time\":0.0}"
        ),
        headers=httpx.Headers({"content-type": "application/json"}),
    )


@contextmanager
def _fail_query_once(exc: Exception) -> Iterator[dict[str, int]]:
    """Make the next QdrantClient.query_points call raise exc; later calls are real."""
    real = QdrantClient.query_points
    state = {"left": 1, "raised": 0}

    def flaky(self: QdrantClient, *args: Any, **kwargs: Any) -> Any:
        if state["left"]:
            state["left"] -= 1
            state["raised"] += 1
            raise exc
        return real(self, *args, **kwargs)

    with patch.object(QdrantClient, "query_points", flaky):
        yield state


@pytest.fixture
def env() -> Iterator[dict[str, Any]]:
    from executor.executors.index import Index as WorkerIndex
    from executor.executors.legacy_executor import LegacyExecutor

    ExecutorRegistry.clear()
    ExecutorRegistry.register(LegacyExecutor)
    tool = _RecordingTool()
    emb = _make_embedding()
    vdb, client, coll = _make_vector_db(tool, emb)
    seen: dict[str, str] = {}

    def index_cls(**kw: Any) -> WorkerIndex:
        idx = WorkerIndex(**kw)
        real_key = idx.generate_index_key

        def key(**k: Any) -> str:
            seen["doc_id"] = real_key(**k)
            return seen["doc_id"]

        idx.generate_index_key = key
        return idx

    deps = (index_cls, lambda **kw: emb, lambda **kw: vdb)
    with (
        patch.object(LegacyExecutor, "_get_indexing_deps", return_value=deps),
        patch(
            "executor.executors.legacy_executor.FileUtils.get_fs_instance",
            return_value=MagicMock(),
        ),
        patch(
            "executor.executors.index.ToolAdapter.get_adapter_config",
            side_effect=lambda tool, iid: {"adapter_id": iid},
        ),
    ):
        executor = ExecutorRegistry.get("legacy")

        def run(reindex: bool = False) -> ExecutionResult:
            ctx = ExecutionContext(
                executor_name="legacy",
                operation="index",
                run_id="run-t",
                execution_source="tool",
                organization_id="org-t",
                request_id="req-t",
                executor_params={
                    "embedding_instance_id": "emb-1",
                    "vector_db_instance_id": "vdb-1",
                    "x2text_instance_id": "x2t-1",
                    "file_path": "/data/contract.pdf",
                    "file_hash": "abc123",
                    "extracted_text": TEXT,
                    "platform_api_key": "pk",
                    "chunk_size": 128,
                    "chunk_overlap": 0,
                    "reindex": reindex,
                },
            )
            return executor.execute(ctx)

        def ids() -> set[str]:
            return _point_ids(client, coll, seen["doc_id"])

        def count() -> int:
            return len(ids())

        def seed() -> int:
            # First index into a fresh collection: a Qdrant server answers the probe 404.
            with _fail_query_once(_collection_not_found(coll)):
                res = run()
            assert res.success, res.error
            return count()

        yield {
            "run": run,
            "count": count,
            "ids": ids,
            "seed": seed,
            "emb": emb,
            "vdb": vdb,
            "tool": tool,
            "seen": seen,
        }
    ExecutorRegistry.clear()
    client.close()


@pytest.mark.parametrize("reindex", [False, True], ids=["reindex=False", "reindex=True"])
def test_probe_timeout_does_not_write_second_copy(
    env: dict[str, Any], reindex: bool
) -> None:
    n = env["seed"]()
    assert n > 0
    before = env["ids"]()
    with _fail_query_once(_read_timeout()) as st:
        res = env["run"](reindex=reindex)
    assert st["raised"] == 1
    assert env["ids"]() == before, (
        f"existence probe failed once and the document now has {env['count']()} points "
        f"where it had {n}"
    )
    assert res.success is False, "a failed existence probe was reported as a successful index"


def test_is_document_indexed_raises_on_probe_failure(env: dict[str, Any]) -> None:
    from executor.executors.dto import (
        ChunkingConfig,
        InstanceIdentifiers,
        ProcessingOptions,
    )
    from executor.executors.index import Index as WorkerIndex

    env["seed"]()
    idx = WorkerIndex(
        tool=env["tool"],
        instance_identifiers=InstanceIdentifiers(
            embedding_instance_id="emb-1",
            vector_db_instance_id="vdb-1",
            x2text_instance_id="x2t-1",
            tool_id="t",
            tags=None,
            llm_instance_id=None,
        ),
        chunking_config=ChunkingConfig(chunk_size=128, chunk_overlap=0),
        processing_options=ProcessingOptions(reindex=False),
    )
    doc_id = env["seen"]["doc_id"]
    with _fail_query_once(_read_timeout()), pytest.raises(VectorDBError):
        idx.is_document_indexed(doc_id=doc_id, embedding=env["emb"], vector_db=env["vdb"])


def test_first_index_then_healthy_probe_skips(env: dict[str, Any]) -> None:
    # The 404 on a fresh collection still means "not indexed", so the seed writes.
    assert env["seed"]() > 0
    before = env["ids"]()
    res = env["run"](reindex=False)
    assert res.success
    assert env["ids"]() == before


def test_healthy_reindex_keeps_one_copy(env: dict[str, Any]) -> None:
    n = env["seed"]()
    res = env["run"](reindex=True)
    assert res.success
    assert env["count"]() == n
