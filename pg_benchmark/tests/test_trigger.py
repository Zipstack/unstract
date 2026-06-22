"""Unit tests for trigger response parsing — pins the real Unstract response shape."""

from __future__ import annotations

from pg_benchmark.cli import _parse_kv
from pg_benchmark.trigger import _extract_execution_id, _id_from_url

EID = "b1f16024-45f2-4e39-8756-d40e24148e30"


class TestExtractExecutionId:
    def test_real_api_deployment_shape(self):
        # The exact shape returned by POST /deployment/api/<org>/<api>/ — id is a
        # query param inside message.status_api, not a top-level field.
        payload = {
            "message": {
                "execution_status": "COMPLETED",
                "status_api": f"/deployment/api/org_X/api-test/?execution_id={EID}",
                "error": None,
                "result": [{"file": "dec-2025.pdf"}],
            }
        }
        assert _extract_execution_id(payload) == EID

    def test_top_level_execution_id(self):
        assert _extract_execution_id({"execution_id": EID}) == EID

    def test_nested_under_data(self):
        assert _extract_execution_id({"data": {"id": EID}}) == EID

    def test_none_when_absent(self):
        assert _extract_execution_id({"message": {"status": "ok"}}) is None
        assert _extract_execution_id("not-json") is None

    def test_id_from_url(self):
        assert _id_from_url(f"/x/?execution_id={EID}&foo=1") == EID
        assert _id_from_url("/x/?foo=1") is None


class TestParseKv:
    def test_header_split_on_first_colon(self):
        # A header value can itself contain a colon (e.g. a URL).
        out = _parse_kv(["X-Sub:sub-1", "X-Url:http://x:8000"], sep=":", label="--header")
        assert out == {"X-Sub": "sub-1", "X-Url": "http://x:8000"}

    def test_form_split_on_equals(self):
        assert _parse_kv(["tags=ali1", "timeout=300"], sep="=", label="--form") == {
            "tags": "ali1",
            "timeout": "300",
        }

    def test_missing_separator_raises(self):
        import pytest

        with pytest.raises(SystemExit):
            _parse_kv(["bad"], sep=":", label="--header")
