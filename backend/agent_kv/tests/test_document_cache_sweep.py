"""`sweep_document_cache`: the OCR document-cache tier is swept BY AGE.

Nothing else reaches this tier. The entries are content-addressed
(`{prefix}/{org}/cache/{doc_sha256}-...json`) with no job row, so
`delete_job_files` and the row-driven TTL cleanup both miss them, and an
object-store lifecycle rule cannot select them either because `org_id` sits
above `cache/` and S3/MinIO lifecycle prefixes are literal. Before this sweep
existed, a customer's extracted document text stayed in the bucket after the
job was deleted, indefinitely, and accumulated. Reported by greptile on
unstract-cloud#1816.

No database: the sweep talks to object storage only, so these drive it through
a fake file storage and assert what it asked the store to do.
"""

from datetime import datetime, timedelta, timezone

import pytest

from agent_kv import storage


class FakeFS:
    """Minimal stand-in for the `FileStorage` surface the sweep uses."""

    def __init__(
        self, entries: dict, *, glob_raises=False, rm_raises=(), mtime_raises=()
    ):
        # entries: path -> mtime (datetime, possibly naive)
        self.entries = dict(entries)
        self.glob_raises = glob_raises
        self.rm_raises = set(rm_raises)
        self.mtime_raises = set(mtime_raises)
        self.removed: list[str] = []
        self.globbed: list[str] = []
        self.stat_calls: list[str] = []

    def glob(self, pattern):
        self.globbed.append(pattern)
        if self.glob_raises:
            raise OSError("listing unavailable")
        return list(self.entries)

    def modification_time(self, path):
        self.stat_calls.append(path)
        if path in self.mtime_raises:
            raise OSError("stat refused")
        if path not in self.entries:
            raise FileNotFoundError(path)
        return self.entries[path]

    def rm(self, path):
        if path in self.rm_raises:
            raise OSError("delete refused")
        if path == "__gone__":
            raise FileNotFoundError(path)
        self.removed.append(path)


@pytest.fixture
def patched_fs(monkeypatch):
    def install(fs):
        monkeypatch.setattr(storage, "_fs", lambda: fs)
        return fs

    return install


def _ago(days):
    return datetime.now(timezone.utc) - timedelta(days=days)


def test_an_entry_past_the_ttl_is_deleted(patched_fs):
    fs = patched_fs(FakeFS({"p/o1/cache/a.json": _ago(10)}))
    assert storage.sweep_document_cache(7, 100) == (1, 0)
    assert fs.removed == ["p/o1/cache/a.json"]


def test_an_entry_inside_the_ttl_is_left_alone(patched_fs):
    fs = patched_fs(FakeFS({"p/o1/cache/a.json": _ago(1)}))
    assert storage.sweep_document_cache(7, 100) == (0, 0)
    assert fs.removed == []


def test_the_glob_covers_every_org_and_only_the_cache_tier(patched_fs):
    fs = patched_fs(FakeFS({}))
    storage.sweep_document_cache(7, 100)
    assert fs.globbed and fs.globbed[0].endswith("/*/cache/*.json")


def test_a_delete_that_fails_counts_as_failed_and_keeps_the_object(patched_fs):
    fs = patched_fs(
        FakeFS({"p/o1/cache/a.json": _ago(10)}, rm_raises=["p/o1/cache/a.json"])
    )
    assert storage.sweep_document_cache(7, 100) == (0, 1)
    assert fs.removed == []


def test_an_object_already_gone_counts_as_deleted(patched_fs):
    # Two sweepers racing, or a lifecycle rule that got there first: the end
    # state is the one asked for, so it is not a failure to report.
    patched_fs(FakeFS({"__gone__": _ago(10)}))
    assert storage.sweep_document_cache(7, 100) == (1, 0)


def test_the_limit_caps_work_per_tick(patched_fs):
    entries = {f"p/o1/cache/{i}.json": _ago(10) for i in range(10)}
    fs = patched_fs(FakeFS(entries))
    assert storage.sweep_document_cache(7, 3) == (3, 0)
    assert len(fs.removed) == 3


def test_a_listing_failure_is_swallowed_so_the_tick_survives(patched_fs):
    fs = patched_fs(FakeFS({"p/o1/cache/a.json": _ago(10)}, glob_raises=True))
    assert storage.sweep_document_cache(7, 100) == (0, 0)
    assert fs.removed == []


def test_a_naive_mtime_is_read_as_utc_rather_than_raising(patched_fs):
    # Some backends return a naive datetime; comparing it to an aware cutoff
    # raises TypeError, which would take the whole maintenance tick down.
    naive_old = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=10)
    fs = patched_fs(FakeFS({"p/o1/cache/a.json": naive_old}))
    assert storage.sweep_document_cache(7, 100) == (1, 0)
    assert fs.removed == ["p/o1/cache/a.json"]


# --- the budget bounds WORK, and the scan rotates (greptile, #2309) --------


def test_unexpired_entries_consume_the_budget_too(patched_fs, monkeypatch):
    """Counting only deletes and failures meant a store full of fresh entries
    stat'ed every one of them on every tick and never reached `limit`, so the
    per-tick cost grew with the cache and could hold the internal TTL endpoint
    past its caller's patience.
    """
    monkeypatch.setattr(storage, "_scan_offset", lambda total: 0)
    entries = {f"p/o1/cache/{i}.json": _ago(1) for i in range(10)}
    fs = patched_fs(FakeFS(entries))
    assert storage.sweep_document_cache(7, 3) == (0, 0)
    assert len(fs.stat_calls) == 3, "examined more than the budget allowed"


def test_a_persistently_failing_prefix_cannot_starve_the_rest(
    patched_fs, monkeypatch
):
    """Starting at the front every tick meant entries that always fail ate the
    whole budget forever and nothing behind them was reached. `run_ttl_cleanup`
    has the same hazard and splits its batch; there is no row to mark here, so
    the scan rotates instead.
    """
    paths = [f"p/o1/cache/{i}.json" for i in range(4)]
    entries = {p: _ago(10) for p in paths}
    bad = paths[:2]

    # Front-start: the budget is spent entirely on the two that always fail.
    monkeypatch.setattr(storage, "_scan_offset", lambda total: 0)
    fs = patched_fs(FakeFS(entries, mtime_raises=bad))
    assert storage.sweep_document_cache(7, 2) == (0, 2)
    assert fs.removed == []

    # A later tick starts past them and reaches what the front-start never did.
    monkeypatch.setattr(storage, "_scan_offset", lambda total: 2)
    fs2 = patched_fs(FakeFS(entries, mtime_raises=bad))
    assert storage.sweep_document_cache(7, 2) == (2, 0)
    assert sorted(fs2.removed) == sorted(paths[2:])


def test_the_offset_stays_inside_the_listing(patched_fs):
    # It indexes `paths`, so an out-of-range value is an IndexError on a
    # maintenance tick rather than a bad sweep.
    for total in (1, 2, 7, 500):
        assert 0 <= storage._scan_offset(total) < total


def test_unconfigured_storage_is_a_quiet_noop_not_a_raise(monkeypatch):
    # Regression: `run_ttl_cleanup` calls this on EVERY tick, including one
    # with no candidate rows. Resolving the backend raises where Agent-KV
    # storage was never configured, and a no-candidate tick used to touch
    # storage not at all -- so letting that escape turned a quiet no-op into a
    # 500 on the TTL-cleanup endpoint. Caught by test_sweeps.py's existing
    # no-op cases, which is why they are worth keeping exact.
    def boom():
        raise RuntimeError("AGENT_KV_FILE_STORAGE_CREDENTIALS is unset")

    monkeypatch.setattr(storage, "_fs", boom)
    assert storage.sweep_document_cache(7, 100) == (0, 0)
