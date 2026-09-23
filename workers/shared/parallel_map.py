"""Generic bounded-concurrency map for LLM (and other I/O-bound) call sites.

Runs ``worker(item)`` across a thread pool capped at ``max_workers`` and returns
results in input order. It is **length-preserving**: the output list is always
the same length as the input and failed items keep their slot, so callers can
realign results to inputs by index (row *i* in maps to row *i* out).

``max_workers=1`` runs effectively sequentially, so a single knob covers both the
sequential and bounded-parallel strategies with no code change.

Rate limiting / retries are intentionally NOT handled here. Bounding
``max_workers`` caps concurrent calls; anything finer (provider rate limits,
``Retry-After``, backoff on 429/5xx/overloaded) is the LLM client's job, not
this generic utility's. Size ``max_workers`` conservatively for the provider.

NOTE: there is no early-abort. All submitted work runs to completion even if the
caller is later cancelled or times out — in-flight threads cannot be killed.
Callers that need to stop a doomed run early must gate submission themselves.
"""

import logging
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")
R = TypeVar("R")

# Cap on how many per-item failures are logged with a full traceback before
# switching to one-line records — stops a dead adapter from emitting hundreds
# of identical stack traces (and Sentry events) for one logical failure.
_MAX_TRACEBACKS = 5


def parallel_map(
    items: list[T],
    worker: Callable[[T], R],
    *,
    max_workers: int,
    on_error: Callable[[int, T, Exception], R] | None = None,
    label: str = "",
) -> list[R | None]:
    """Apply ``worker`` to each item with bounded concurrency, order preserved.

    Args:
        items: Inputs to process. An empty list returns ``[]``.
        worker: Called as ``worker(item)`` for each item.
        max_workers: Thread-pool cap. ``<= 1`` runs effectively sequentially.
        on_error: Called as ``on_error(index, item, exception)`` to produce a
            fallback result when a worker raises. If omitted, a failed item's
            slot is left as ``None`` (still counted — length is preserved).
            Prefer passing ``on_error`` so a failed slot is distinguishable
            from a legitimate ``None`` result.
        label: Optional label for the progress log line.

    Returns:
        A list the SAME LENGTH as ``items``, results in input order. A failed
        item holds the ``on_error`` fallback, or ``None`` when ``on_error`` is
        omitted — hence the ``R | None`` element type.
    """
    if not items:
        return []

    n = len(items)
    effective_workers = max(max_workers, 1)
    results: list[R | None] = [None] * n
    failures = 0

    if effective_workers > 1:
        suffix = f" ({label})" if label else ""
        logger.info(
            "parallel_map: %d items across up to %d workers%s",
            n,
            effective_workers,
            suffix,
        )

    # The as_completed loop body runs on the calling thread (only worker() runs
    # in the pool), so results/logging here need no locking.
    with ThreadPoolExecutor(max_workers=effective_workers) as executor:
        future_to_idx = {
            executor.submit(worker, item): idx for idx, item in enumerate(items)
        }
        for future in as_completed(future_to_idx):
            idx = future_to_idx[future]
            try:
                results[idx] = future.result()
            except Exception as e:
                failures += 1
                # Full traceback for the first few, then one-liners so a
                # systemic failure doesn't flood logs.
                logger.error(
                    "parallel_map: item %d/%d failed: %s",
                    idx + 1,
                    n,
                    e,
                    exc_info=failures <= _MAX_TRACEBACKS,
                )
                if on_error is not None:
                    # Guard on_error itself: if it raises, it would propagate
                    # through the pool's __exit__ (shutdown(wait=True)) and hang
                    # the caller until every in-flight task drains, with no log.
                    try:
                        results[idx] = on_error(idx, items[idx], e)
                    except Exception:
                        logger.error(
                            "parallel_map: on_error raised for item %d/%d",
                            idx + 1,
                            n,
                            exc_info=True,
                        )

    if failures:
        logger.warning(
            "parallel_map: %d/%d items failed%s",
            failures,
            n,
            f" ({label})" if label else "",
        )
    return results
