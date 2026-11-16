"""skip_local_cache returns the result of its stale-cache retry.

A FileNotFoundError may come from a stale fsspec cache, so the decorator
invalidates the cache and retries; the retried call's result must be returned.
"""

from unittest.mock import MagicMock

import pytest
from unstract.sdk1.file_storage.helper import skip_local_cache


class _Storage:
    def __init__(self, outcomes: list[object]) -> None:
        self.fs = MagicMock()
        self._outcomes = outcomes
        self.calls = 0

    @skip_local_cache
    def read(self) -> object:
        outcome = self._outcomes[self.calls]
        self.calls += 1
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


def test_retry_after_stale_cache_returns_result() -> None:
    storage = _Storage([FileNotFoundError("stale"), "content"])

    assert storage.read() == "content"
    assert storage.calls == 2
    storage.fs.invalidate_cache.assert_called_once_with()


def test_retry_that_still_misses_raises_file_not_found() -> None:
    storage = _Storage([FileNotFoundError("stale"), FileNotFoundError("gone")])

    with pytest.raises(FileNotFoundError):
        storage.read()
