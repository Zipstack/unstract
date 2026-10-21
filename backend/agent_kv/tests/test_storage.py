import os
import re
import uuid
from unittest import mock

import django
import pytest
from django.apps import apps

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "backend.settings.test")
if not apps.ready:
    django.setup()

from django.conf import settings  # noqa: E402
from django.test import override_settings  # noqa: E402

from agent_kv import storage  # noqa: E402
from agent_kv.models import AgentKVJob  # noqa: E402

#: A job id of the shape the real paths carry, so the reconstructed job dir in
#: the reap tests is the real thing rather than "None".
_JOB_ID = uuid.UUID("3f2504e0-4f89-41d3-9a0c-0305e82c3301")


def _upload(name: str, data: bytes):
    up = mock.Mock()
    up.name = name
    up.chunks.return_value = [data]
    return up


@mock.patch.object(storage, "FileSystem")
def test_stage_input_path_and_write(m_fs):
    fh = m_fs.return_value.get_file_storage.return_value
    up = mock.Mock()
    up.name = "invoice.PDF"
    up.chunks.return_value = [b"a", b"b"]
    ref = storage.stage_input("org1", "job1", up)
    assert ref == "unstract/agent_kv/org1/job1/input.pdf"
    assert fh.write.called
    kwargs = fh.write.call_args.kwargs
    assert kwargs["path"] == "unstract/agent_kv/org1/job1/input.pdf"
    assert kwargs["data"] == b"ab"


@mock.patch.object(storage, "FileSystem")
def test_stage_input_defaults_extension_when_missing(m_fs):
    up = mock.Mock()
    up.name = "noext"
    up.chunks.return_value = [b"x"]
    ref = storage.stage_input("org1", "job1", up)
    assert ref == "unstract/agent_kv/org1/job1/input.bin"


@mock.patch.object(storage, "FileSystem")
def test_write_and_read_result_roundtrip_path(m_fs):
    fh = m_fs.return_value.get_file_storage.return_value
    ref = storage.write_result("org1", "job1", {"success": True})
    # The result path is UNIQUE per finalize attempt (a nonce suffix) so a
    # guard-losing concurrent finalize deletes only its own orphan, never the
    # winning row's result_ref target (pre-Greptile critical #3). It still
    # lives under the deterministic job dir.
    assert re.fullmatch(
        r"unstract/agent_kv/org1/job1/result-[0-9a-f]{32}\.json", ref
    ), ref
    fh.json_dump.assert_called_once()
    assert fh.json_dump.call_args.kwargs["path"] == ref
    assert fh.json_dump.call_args.kwargs["data"] == {"success": True}


@mock.patch.object(storage, "FileSystem")
def test_write_result_produces_unique_ref_per_call(m_fs):
    # Two writes for the SAME job must yield two DISTINCT refs -- this is what
    # makes a concurrent duplicate-success finalize safe: the guard loser's
    # delete targets its own ref, not the winner's.
    a = storage.write_result("org1", "job1", {"n": 1})
    b = storage.write_result("org1", "job1", {"n": 2})
    assert a != b
    assert a.startswith("unstract/agent_kv/org1/job1/result-")
    assert b.startswith("unstract/agent_kv/org1/job1/result-")


@mock.patch.object(storage, "FileSystem")
def test_write_result_accepts_explicit_nonce(m_fs):
    # A caller may pin the nonce (deterministic ref for a given attempt).
    ref = storage.write_result("org1", "job1", {"n": 1}, nonce="abc123")
    assert ref == "unstract/agent_kv/org1/job1/result-abc123.json"


@mock.patch.object(storage, "FileSystem")
def test_read_result_returns_parsed_json(m_fs):
    fh = m_fs.return_value.get_file_storage.return_value
    fh.json_load.return_value = {"success": True}
    out = storage.read_result("unstract/agent_kv/org1/job1/result.json")
    assert out == {"success": True}
    fh.json_load.assert_called_once_with(path="unstract/agent_kv/org1/job1/result.json")


def _job(**kwargs):
    """An unsaved job that still has the identity the job-dir reap needs."""
    kwargs.setdefault("input_ref", "org/o/agent_kv/j/input.pdf")
    kwargs.setdefault("result_ref", "org/o/agent_kv/j/result.json")
    return AgentKVJob(id=_JOB_ID, organization_id=7, **kwargs)


@mock.patch.object(storage, "FileSystem")
def test_delete_job_files_removes_both_refs(m_fs):
    fh = m_fs.return_value.get_file_storage.return_value
    # Flat object storage: the prefix stops existing with its last object, so
    # the reap below finds nothing to do. That is the ordinary case.
    fh.exists.return_value = False
    job = _job()
    cleared = storage.delete_job_files(job)
    removed = {c.kwargs["path"] for c in fh.rm.call_args_list}
    assert removed == {job.input_ref, job.result_ref}
    assert cleared == ["input_ref", "result_ref"]
    assert not fh.rm_exact.called


@mock.patch.object(storage, "FileSystem")
def test_delete_job_files_reaps_an_orphan_left_in_the_job_dir(m_fs):
    """The hole a failed `delete_result_file` leaves, and the only pass that
    can see it.

    A finalize that loses the attach guard writes a result file and then
    deletes it best-effort. If that delete fails the object stays and NO ref
    anywhere points at it -- `delete_result_file` logs and returns, and TTL
    cleanup selects candidates by the refs stored on the row. Both named files
    being confirmed gone is what makes anything still under the job's own
    directory an orphan by definition.
    """
    fh = m_fs.return_value.get_file_storage.return_value
    fh.exists.return_value = True
    job = _job()

    cleared = storage.delete_job_files(job)

    assert cleared == ["input_ref", "result_ref"]
    fh.rm_exact.assert_called_once_with(f"unstract/agent_kv/7/{_JOB_ID}")


@mock.patch.object(storage, "FileSystem")
def test_the_reaped_dir_is_the_one_the_job_actually_wrote_into(m_fs):
    """Guards the reap's one assumption.

    It reconstructs the directory from the job's org and id rather than from a
    ref, so it still works when both refs are already blank. That is only
    sound while the reconstruction matches what `stage_input`/`write_result`
    actually used -- `org_id` there is `str(agent_kv_key.organization_id)`, the
    same value. If the storage layout or the org identifier changes, this
    fails rather than the reap silently deleting nothing (or something else).
    """
    staged = storage.stage_input("7", str(_JOB_ID), _upload("x.pdf", b"a"))
    written = storage.write_result("7", str(_JOB_ID), {})

    job_dir = storage._base("7", str(_JOB_ID))

    assert staged.rsplit("/", 1)[0] == job_dir
    assert written.rsplit("/", 1)[0] == job_dir


@mock.patch.object(storage, "FileSystem")
def test_a_failing_reap_does_not_change_which_refs_are_reported_clear(m_fs):
    """Best-effort and LAST. The reap runs only after the named deletes have
    succeeded, so its failure cannot cost the caller a ref it was about to
    blank -- and the orphan it could not remove is exactly as reachable as it
    was before (i.e. not), which is a pre-existing hole and not a new one.
    """
    fh = m_fs.return_value.get_file_storage.return_value
    fh.exists.return_value = True
    fh.rm_exact.side_effect = OSError("object store unreachable")

    assert storage.delete_job_files(_job()) == ["input_ref", "result_ref"]


@mock.patch.object(storage, "FileSystem")
def test_delete_job_files_tolerates_missing_files(m_fs):
    fh = m_fs.return_value.get_file_storage.return_value
    fh.rm.side_effect = FileNotFoundError("gone")
    job = AgentKVJob(
        input_ref="org/o/agent_kv/j/input.pdf",
        result_ref="org/o/agent_kv/j/result.json",
    )
    # Must not raise, and both count as CLEARED: the goal is "the file is not
    # there", and a ref whose object is already gone has nothing to retry.
    cleared = storage.delete_job_files(job)
    assert fh.rm.call_count == 2
    assert cleared == ["input_ref", "result_ref"]


@mock.patch.object(storage, "FileSystem")
def test_delete_job_files_skips_blank_refs(m_fs):
    fh = m_fs.return_value.get_file_storage.return_value
    fh.exists.return_value = False
    job = _job(input_ref="", result_ref="")
    cleared = storage.delete_job_files(job)
    assert not fh.rm.called
    # Reported clear: nothing was ever staged, so there is nothing to retry and
    # the caller is free to blank (already-blank) refs.
    assert cleared == ["input_ref", "result_ref"]


# The Greptile-review contract (#3): a ref is reported clear ONLY when its file
# is confirmed gone. A storage error that is not FileNotFoundError leaves the
# ref out, and the ref is what TTL cleanup retries from -- its candidate query
# matches rows by `input_ref > "" OR result_ref > ""`, so a blanked ref whose
# object is still in the bucket orphans that object permanently.
@mock.patch.object(storage, "FileSystem")
def test_delete_job_files_omits_the_ref_whose_delete_raised(m_fs):
    fh = m_fs.return_value.get_file_storage.return_value
    job = _job()

    def rm(*, path):
        if path == job.result_ref:
            raise OSError("object store unreachable")

    fh.rm.side_effect = rm

    cleared = storage.delete_job_files(job)

    # Still attempted both -- one failure must not abort the other's cleanup.
    assert fh.rm.call_count == 2
    assert cleared == ["input_ref"]
    # And NO reap: `result_ref` is being kept as the retry handle, so the file
    # it points at is still wanted. Reaping the directory here would delete
    # the very object the retry exists for, and blank nothing, leaving the row
    # to retry forever against a file that is already gone.
    assert not fh.rm_exact.called


@mock.patch.object(storage, "FileSystem")
def test_delete_job_files_reports_nothing_clear_when_both_deletes_raise(m_fs):
    fh = m_fs.return_value.get_file_storage.return_value
    fh.rm.side_effect = OSError("object store unreachable")
    assert storage.delete_job_files(_job()) == []


# delete_input carries the same confirmed-clear contract as delete_job_files.
# It did not when the Greptile round fixed delete_job_files and its two
# callers: this third ref-blanking site (FinalizeView) was missed, because the
# fix followed one function's callers instead of grepping for every site that
# blanks a ref. A failed delete here orphaned the customer's uploaded document
# permanently -- TTL cleanup only selects rows that still carry a non-blank
# ref, so a blanked row can never be reconsidered.
@mock.patch.object(storage, "FileSystem")
def test_delete_input_reports_clear_on_success(m_fs):
    job = AgentKVJob(input_ref="org/o/agent_kv/j/input.pdf")
    assert storage.delete_input(job) is True


@mock.patch.object(storage, "FileSystem")
def test_delete_input_reports_clear_when_the_file_is_already_gone(m_fs):
    m_fs.return_value.get_file_storage.return_value.rm.side_effect = FileNotFoundError
    job = AgentKVJob(input_ref="org/o/agent_kv/j/input.pdf")
    # Already missing is the goal state -- nothing left to retry.
    assert storage.delete_input(job) is True


@mock.patch.object(storage, "FileSystem")
def test_delete_input_reports_NOT_clear_when_the_delete_raised(m_fs):
    m_fs.return_value.get_file_storage.return_value.rm.side_effect = OSError("down")
    job = AgentKVJob(input_ref="org/o/agent_kv/j/input.pdf")
    # Must not raise, and must not claim the ref is clear.
    assert storage.delete_input(job) is False


@mock.patch.object(storage, "FileSystem")
def test_delete_input_reports_clear_for_a_blank_ref(m_fs):
    fh = m_fs.return_value.get_file_storage.return_value
    assert storage.delete_input(AgentKVJob(input_ref="")) is True
    assert not fh.rm.called


@mock.patch.object(storage, "FileSystem")
def test_delete_input_removes_only_input_ref(m_fs):
    fh = m_fs.return_value.get_file_storage.return_value
    job = AgentKVJob(
        input_ref="org/o/agent_kv/j/input.pdf",
        result_ref="org/o/agent_kv/j/result.json",
    )
    storage.delete_input(job)
    fh.rm.assert_called_once_with(path=job.input_ref)


@mock.patch.object(storage, "FileSystem")
def test_delete_input_tolerates_missing_file(m_fs):
    fh = m_fs.return_value.get_file_storage.return_value
    fh.rm.side_effect = FileNotFoundError("gone")
    job = AgentKVJob(input_ref="org/o/agent_kv/j/input.pdf")
    # Must not raise.
    storage.delete_input(job)
    assert fh.rm.call_count == 1


@mock.patch.object(storage, "FileSystem")
def test_delete_input_skips_blank_ref(m_fs):
    fh = m_fs.return_value.get_file_storage.return_value
    job = AgentKVJob(input_ref="")
    storage.delete_input(job)
    assert not fh.rm.called


@mock.patch.object(storage, "FileSystem")
def test_delete_result_file_removes_the_given_ref(m_fs):
    fh = m_fs.return_value.get_file_storage.return_value
    storage.delete_result_file("org/o/agent_kv/j/result.json")
    fh.rm.assert_called_once_with(path="org/o/agent_kv/j/result.json")


@mock.patch.object(storage, "FileSystem")
def test_delete_result_file_tolerates_missing_file(m_fs):
    fh = m_fs.return_value.get_file_storage.return_value
    fh.rm.side_effect = FileNotFoundError("gone")
    # Must not raise.
    storage.delete_result_file("org/o/agent_kv/j/result.json")
    assert fh.rm.call_count == 1


@mock.patch.object(storage, "FileSystem")
def test_delete_result_file_skips_blank_ref(m_fs):
    fh = m_fs.return_value.get_file_storage.return_value
    storage.delete_result_file("")
    assert not fh.rm.called


def test_default_storage_prefix_is_bucket_rooted():
    """The shipped default roots every path in a real bucket (13b F1).

    s3fs/gcsfs read the first path segment as the bucket, so a prefix without
    one (the old ``org/{org_id}/...``) makes every write fail ``NoSuchBucket``.
    The default must therefore stay ``unstract/agent_kv`` -- bucket ``unstract``
    (created by the MinIO dev bootstrap), directory ``agent_kv`` -- and must
    match the cloud executor's ``AGENT_KV_STORAGE_DIR_PREFIX``.
    """
    if "AGENT_KV_STORAGE_DIR_PREFIX" in os.environ:
        pytest.skip("AGENT_KV_STORAGE_DIR_PREFIX is overridden in this environment")
    assert settings.AGENT_KV_STORAGE_DIR_PREFIX == "unstract/agent_kv"
    bucket, _, rest = settings.AGENT_KV_STORAGE_DIR_PREFIX.partition("/")
    # Split: a composite assert cannot say WHICH half failed, and these two
    # mean different things -- no bucket segment vs. a bucket with no path.
    assert bucket
    assert rest


@mock.patch.object(storage, "FileSystem")
def test_paths_are_rooted_at_the_configured_prefix(m_fs):
    up = mock.Mock()
    up.name = "invoice.pdf"
    up.chunks.return_value = [b"x"]
    with override_settings(AGENT_KV_STORAGE_DIR_PREFIX="mybucket/kv-root"):
        input_ref = storage.stage_input("org1", "job1", up)
        result_ref = storage.write_result("org1", "job1", {"success": True})
    assert input_ref.startswith("mybucket/kv-root/")
    assert result_ref.startswith("mybucket/kv-root/")
    assert input_ref == "mybucket/kv-root/org1/job1/input.pdf"
    assert re.fullmatch(
        r"mybucket/kv-root/org1/job1/result-[0-9a-f]{32}\.json", result_ref
    ), result_ref


def test_storage_prefix_normalisation_matches_executor(monkeypatch):
    """A sloppy operator value must resolve to the same root on both sides:
    the cloud executor strips whitespace and edge slashes before keying its
    OCR cache, so the backend must too, else inputs and cache split roots.
    """
    import importlib

    monkeypatch.setenv("AGENT_KV_STORAGE_DIR_PREFIX", "  /unstract/agent_kv/ ")
    from backend.settings import base

    importlib.reload(base)
    try:
        assert base.AGENT_KV_STORAGE_DIR_PREFIX == "unstract/agent_kv"
        monkeypatch.setenv("AGENT_KV_STORAGE_DIR_PREFIX", "   ")
        importlib.reload(base)
        assert base.AGENT_KV_STORAGE_DIR_PREFIX == "unstract/agent_kv"
    finally:
        monkeypatch.delenv("AGENT_KV_STORAGE_DIR_PREFIX", raising=False)
        importlib.reload(base)
