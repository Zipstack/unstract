import os
from unittest import mock

import django
from django.apps import apps

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "backend.settings.test")
if not apps.ready:
    django.setup()

from agent_kv import storage  # noqa: E402
from agent_kv.models import AgentKVJob  # noqa: E402


@mock.patch.object(storage, "FileSystem")
def test_stage_input_path_and_write(m_fs):
    fh = m_fs.return_value.get_file_storage.return_value
    up = mock.Mock()
    up.name = "invoice.PDF"
    up.chunks.return_value = [b"a", b"b"]
    ref = storage.stage_input("org1", "job1", up)
    assert ref == "org/org1/agent_kv/job1/input.pdf"
    assert fh.write.called
    kwargs = fh.write.call_args.kwargs
    assert kwargs["path"] == "org/org1/agent_kv/job1/input.pdf"
    assert kwargs["data"] == b"ab"


@mock.patch.object(storage, "FileSystem")
def test_stage_input_defaults_extension_when_missing(m_fs):
    up = mock.Mock()
    up.name = "noext"
    up.chunks.return_value = [b"x"]
    ref = storage.stage_input("org1", "job1", up)
    assert ref == "org/org1/agent_kv/job1/input.bin"


@mock.patch.object(storage, "FileSystem")
def test_write_and_read_result_roundtrip_path(m_fs):
    fh = m_fs.return_value.get_file_storage.return_value
    ref = storage.write_result("org1", "job1", {"success": True})
    assert ref == "org/org1/agent_kv/job1/result.json"
    fh.json_dump.assert_called_once()
    assert fh.json_dump.call_args.kwargs["path"] == ref
    assert fh.json_dump.call_args.kwargs["data"] == {"success": True}


@mock.patch.object(storage, "FileSystem")
def test_read_result_returns_parsed_json(m_fs):
    fh = m_fs.return_value.get_file_storage.return_value
    fh.json_load.return_value = {"success": True}
    out = storage.read_result("org/org1/agent_kv/job1/result.json")
    assert out == {"success": True}
    fh.json_load.assert_called_once_with(path="org/org1/agent_kv/job1/result.json")


@mock.patch.object(storage, "FileSystem")
def test_delete_job_files_removes_both_refs(m_fs):
    fh = m_fs.return_value.get_file_storage.return_value
    job = AgentKVJob(
        input_ref="org/o/agent_kv/j/input.pdf",
        result_ref="org/o/agent_kv/j/result.json",
    )
    storage.delete_job_files(job)
    removed = {c.kwargs["path"] for c in fh.rm.call_args_list}
    assert removed == {job.input_ref, job.result_ref}


@mock.patch.object(storage, "FileSystem")
def test_delete_job_files_tolerates_missing_files(m_fs):
    fh = m_fs.return_value.get_file_storage.return_value
    fh.rm.side_effect = FileNotFoundError("gone")
    job = AgentKVJob(
        input_ref="org/o/agent_kv/j/input.pdf",
        result_ref="org/o/agent_kv/j/result.json",
    )
    # Must not raise.
    storage.delete_job_files(job)
    assert fh.rm.call_count == 2


@mock.patch.object(storage, "FileSystem")
def test_delete_job_files_skips_blank_refs(m_fs):
    fh = m_fs.return_value.get_file_storage.return_value
    job = AgentKVJob(input_ref="", result_ref="")
    storage.delete_job_files(job)
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
