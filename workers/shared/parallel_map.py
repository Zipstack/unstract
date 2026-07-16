"""Generic bounded-concurrency map for LLM (and other I/O-bound) call sites.

Runs ``worker(item)`` across a thread pool capped at ``max_workers`` and returns
results in input order. Unlike the agentic extractor's older ``parallel_page_map``
(which drops ``None`` results), this is **length-preserving**: the output list is
always the same length as the input, so callers can realign results to inputs by
index — essential for per-row enrichment where row *i* in must map to row *i* out.

``max_workers=1`` runs effectively sequentially, so a single knob covers both the
sequential and bounded-parallel strategies with no code change.

Rate limiting / retries are intentionally NOT handled here — the SDK LLM client
already retries transient errors (429/500/503/... and provider "overloaded")
with backoff and honors ``Retry-After``, so ``max_workers`` concurrent callers
self-throttle without any extra coordination in this utility.

NOTE: there is no early-abort. All submitted work runs to completion even if the
caller is later cancelled or times out — in-flight threads cannot be killed.
Callers that need to stop a doomed run early must gate submission themselves.
"""

import logging
import threading
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")
R = TypeVar("R")


def parallel_map(
    items: list[T],
    worker: Callable[[T], R],
    *,
    max_workers: int,
    on_error: Callable[[int, T, Exception], R] | None = None,
    label: str = "",
) -> list[R]:
    """Apply ``worker`` to each item with bounded concurrency, order preserved.

    Args:
        items: Inputs to process. An empty list returns ``[]``.
        worker: Called as ``worker(item)`` for each item.
        max_workers: Thread-pool cap. ``<= 1`` runs effectively sequentially.
        on_error: Called as ``on_error(index, item, exception)`` to produce a
            fallback result when a worker raises. If omitted, a failed item's
            slot is left as ``None`` (still counted — length is preserved).
        label: Optional label for the progress log line.

    Returns:
        A list the SAME LENGTH as ``items``, results in input order. Failed
        items hold either the ``on_error`` fallback or ``None``.
    """
    if not items:
        return []

    n = len(items)
    effective_workers = max(max_workers, 1)
    results: list[R | None] = [None] * n
    log_lock = threading.Lock()

    if effective_workers > 1:
        suffix = f" ({label})" if label else ""
        logger.info(
            "parallel_map: %d items across up to %d workers%s",
            n,
            effective_workers,
            suffix,
        )

    with ThreadPoolExecutor(max_workers=effective_workers) as executor:
        future_to_idx = {
            executor.submit(worker, item): idx for idx, item in enumerate(items)
        }
        for future in as_completed(future_to_idx):
            idx = future_to_idx[future]
            try:
                results[idx] = future.result()
            except Exception as e:
                with log_lock:
                    logger.error(
                        "parallel_map: item %d/%d failed: %s",
                        idx + 1,
                        n,
                        e,
                        exc_info=True,
                    )
                if on_error is not None:
                    results[idx] = on_error(idx, items[idx], e)

    return results
