import io
import json
import os
from unittest import mock

import django
from django.apps import apps

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "backend.settings.test")
if not apps.ready:
    django.setup()

from django.core.files.uploadedfile import SimpleUploadedFile  # noqa: E402
from agent_kv.execution_serializers import SubmitSerializer  # noqa: E402

FIXTURES = os.path.join(os.path.dirname(__file__), "fixtures")
VALID_KEYS = {"total": {"description": "Grand total", "format": "currency"}}


def _pdf_upload(name="doc.pdf"):
    with open(os.path.join(FIXTURES, "two_page.pdf"), "rb") as f:
        return SimpleUploadedFile(name, f.read(), content_type="application/pdf")


def _data(**over):
    d = {"file": _pdf_upload(), "keys": json.dumps(VALID_KEYS)}
    d.update(over)
    return d


def test_valid_submit_compiles_and_counts_pages():
    s = SubmitSerializer(data=_data())
    assert s.is_valid(), s.errors
    assert s.pages_total == 2
    assert [k.path for k in s.compiled.key_specs] == ["total"]
    assert s.validated_data["qa"] is True
    assert s.validated_data["challenge"] is True
    assert s.validated_data["extraction_mode"] == "whole-doc"


def test_disallowed_extension_rejected():
    bad = SimpleUploadedFile("doc.exe", b"MZ", content_type="application/x-dos")
    s = SubmitSerializer(data=_data(file=bad))
    assert not s.is_valid()
    assert "file" in s.errors


def test_oversize_file_rejected():
    with mock.patch("agent_kv.execution_serializers.settings") as m:
        m.AGENT_KV_MAX_FILE_SIZE_MB = 0
        m.AGENT_KV_MAX_PAGES = 100
        m.AGENT_KV_MAX_SCHEMA_BYTES = 262_144
        m.AGENT_KV_MAX_CALCULATIONS_BYTES = 20_000
        m.AGENT_KV_MAX_TIMEOUT_SECONDS = 300
        s = SubmitSerializer(data=_data())
        assert not s.is_valid()
        assert "file" in s.errors


def test_page_cap_rejected():
    with mock.patch("agent_kv.execution_serializers.settings") as m:
        m.AGENT_KV_MAX_FILE_SIZE_MB = 50
        m.AGENT_KV_MAX_PAGES = 1
        m.AGENT_KV_MAX_SCHEMA_BYTES = 262_144
        m.AGENT_KV_MAX_CALCULATIONS_BYTES = 20_000
        m.AGENT_KV_MAX_TIMEOUT_SECONDS = 300
        s = SubmitSerializer(data=_data())
        assert not s.is_valid()
        assert "pages" in str(s.errors).lower()


def test_bad_schema_is_field_error_not_500():
    s = SubmitSerializer(data=_data(keys=json.dumps({"a": {"format": "string"}})))
    assert not s.is_valid()
    assert "keys" in s.errors


def test_keys_not_json_rejected():
    s = SubmitSerializer(data=_data(keys="{not json"))
    assert not s.is_valid()
    assert "keys" in s.errors


def test_calculations_cap():
    s = SubmitSerializer(data=_data(calculations="x" * 30_000))
    assert not s.is_valid()
    assert "calculations" in s.errors


def test_timeout_bounds():
    s = SubmitSerializer(data=_data(timeout=301))
    assert not s.is_valid()
    s2 = SubmitSerializer(data=_data(timeout=0))
    assert s2.is_valid(), s2.errors


def test_page_range_validation():
    s = SubmitSerializer(data=_data(page_start=5, page_end=2))
    assert not s.is_valid()
