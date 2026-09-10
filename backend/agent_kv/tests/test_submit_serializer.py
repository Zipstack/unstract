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


# Fields that describe the REQUEST rather than an extractor (spec §7.1).
# Anything else passed to _data() is routed into the kv extractor's options,
# so each test still reads as "submit with this one thing changed".
_JOB_LEVEL = {
    "file", "extractors", "page_start", "page_end",
    "timeout", "tags", "custom_data", "webhook_url",
}


def _data(**over):
    """Build a submit payload in the extractor-scoped wire format (§7.0)."""
    keys = over.pop("keys", VALID_KEYS)
    options = {k: over.pop(k) for k in list(over) if k not in _JOB_LEVEL}
    d = {
        "file": _pdf_upload(),
        "extractors": json.dumps([{"name": "kv", "keys": keys, "options": options}]),
    }
    d.update(over)
    return d


def _errs(s):
    """All validation errors as one string.

    Per-extractor failures surface nested under `extractors`, so asserting on a
    specific top-level key would just be asserting on DRF's nesting shape rather
    than on the rejection actually happening."""
    return str(s.errors)


def _defaults(m):
    """Set every AGENT_KV_* attribute the serializer reads to its production default."""
    m.AGENT_KV_MAX_FILE_SIZE_MB = 50
    m.AGENT_KV_MAX_PAGES = 100
    m.AGENT_KV_MAX_SCHEMA_BYTES = 262_144
    m.AGENT_KV_MAX_CALCULATIONS_BYTES = 20_000
    m.AGENT_KV_MAX_TIMEOUT_SECONDS = 300
    m.AGENT_KV_CALCULATIONS_ENABLED = False
    m.AGENT_KV_STRUCTURED_OUTPUT_ENABLED = False


def test_valid_submit_compiles_and_counts_pages():
    s = SubmitSerializer(data=_data())
    assert s.is_valid(), s.errors
    assert s.pages_total == 2
    # `compiled` is keyed by extractor now -- a multi-extractor job compiles
    # one schema per entry, so a single bare schema could not hold them.
    assert list(s.compiled) == ["kv"]
    assert [k.path for k in s.compiled["kv"].key_specs] == ["total"]
    entry = s.validated_data["extractors"][0]
    assert entry["name"] == "kv"
    assert entry["options"]["qa"] is True
    assert entry["options"]["challenge"] is True
    assert entry["options"]["extraction_mode"] == "whole-doc"


def test_disallowed_extension_rejected():
    bad = SimpleUploadedFile("doc.exe", b"MZ", content_type="application/x-dos")
    s = SubmitSerializer(data=_data(file=bad))
    assert not s.is_valid()
    assert "file" in s.errors


def test_oversize_file_rejected():
    with mock.patch("agent_kv.execution_serializers.settings") as m:
        _defaults(m)
        m.AGENT_KV_MAX_FILE_SIZE_MB = 0
        s = SubmitSerializer(data=_data())
        assert not s.is_valid()
        assert "file" in s.errors


def test_page_cap_rejected():
    with mock.patch("agent_kv.execution_serializers.settings") as m:
        _defaults(m)
        m.AGENT_KV_MAX_PAGES = 1
        s = SubmitSerializer(data=_data())
        assert not s.is_valid()
        assert "pages" in str(s.errors).lower()


def test_bad_schema_is_field_error_not_500():
    s = SubmitSerializer(data=_data(keys={"a": {"format": "string"}}))
    assert not s.is_valid()
    assert "keys" in _errs(s)


def test_extractors_not_json_rejected():
    s = SubmitSerializer(data=_data(extractors="{not json"))
    assert not s.is_valid()
    assert "extractors" in s.errors


def test_calculations_cap():
    # AGENT_KV_CALCULATIONS_ENABLED must be mocked True here: real settings
    # default it False, so an unmocked run hits the feature-gate branch (a
    # different error) instead of the byte-size cap this test is named for.
    with mock.patch("agent_kv.execution_serializers.settings") as m:
        _defaults(m)
        m.AGENT_KV_CALCULATIONS_ENABLED = True
        s = SubmitSerializer(data=_data(calculations="x" * 30_000))
        assert not s.is_valid()
        assert "calculations" in _errs(s)
        assert "20000 bytes" in _errs(s)


def test_timeout_bounds():
    s = SubmitSerializer(data=_data(timeout=301))
    assert not s.is_valid()
    s2 = SubmitSerializer(data=_data(timeout=0))
    assert s2.is_valid(), s2.errors


def test_page_range_validation():
    s = SubmitSerializer(data=_data(page_start=5, page_end=2))
    assert not s.is_valid()


def test_unreadable_pdf_is_field_error_and_stream_is_rewound():
    bad = SimpleUploadedFile("doc.pdf", b"not a pdf", content_type="application/pdf")
    s = SubmitSerializer(data=_data(file=bad))
    assert not s.is_valid()
    assert "file" in s.errors
    # The `finally: f.seek(0)` in validate() must run on the error path too,
    # so a downstream reader (e.g. the view persisting the upload) still sees
    # the whole stream from the start.
    assert bad.tell() == 0
    assert bad.read() == b"not a pdf"


def test_calculations_rejected_when_disabled():
    with mock.patch("agent_kv.execution_serializers.settings") as m:
        _defaults(m); m.AGENT_KV_CALCULATIONS_ENABLED = False
        s = SubmitSerializer(data=_data(calculations="annualize rent"))
        assert not s.is_valid()
        assert "not available" in _errs(s)


def test_calculations_accepted_when_enabled():
    with mock.patch("agent_kv.execution_serializers.settings") as m:
        _defaults(m); m.AGENT_KV_CALCULATIONS_ENABLED = True
        assert SubmitSerializer(data=_data(calculations="annualize rent")).is_valid()


def test_structured_output_rejected_when_disabled():
    with mock.patch("agent_kv.execution_serializers.settings") as m:
        _defaults(m); m.AGENT_KV_STRUCTURED_OUTPUT_ENABLED = False
        s = SubmitSerializer(data=_data(structured_output=True))
        assert not s.is_valid()
        assert "structured_output" in _errs(s)


def test_empty_calculations_and_false_structured_output_pass_when_disabled():
    with mock.patch("agent_kv.execution_serializers.settings") as m:
        _defaults(m)
        assert SubmitSerializer(data=_data()).is_valid()


# ---------------------------------------------------------------------------
# Extractor-scoped wire format (spec §7.0/§7.1). These rules exist so a caller
# learns immediately that something is unsupported, rather than having the
# request quietly run as something other than what they asked for.
# ---------------------------------------------------------------------------
def test_unknown_extractor_name_rejected():
    s = SubmitSerializer(data=_data(extractors=json.dumps(
        [{"name": "table", "keys": VALID_KEYS}]
    )))
    assert not s.is_valid()
    assert "unknown extractor" in _errs(s)


def test_multiple_extractors_rejected_until_fan_out_exists():
    """The FORMAT is fixed before launch; the fan-out execution is not built.

    Accepting two entries and running only the first would be the silent kind
    of wrong -- the caller is billed for a job that ignored half the request.
    """
    two = [{"name": "kv", "keys": VALID_KEYS}, {"name": "kv", "keys": VALID_KEYS}]
    s = SubmitSerializer(data=_data(extractors=json.dumps(two)))
    assert not s.is_valid()
    assert "multiple extractors are not supported yet" in _errs(s)


def test_empty_or_non_list_extractors_rejected():
    for bad in ("[]", '{"name": "kv"}', '"kv"'):
        s = SubmitSerializer(data=_data(extractors=bad))
        assert not s.is_valid(), bad
        assert "non-empty JSON array" in _errs(s)


def test_unknown_option_is_rejected_not_silently_dropped():
    """DRF drops unknown fields by default; for per-extractor options that would
    mean a typo'd or misaddressed knob silently changing what the job runs."""
    s = SubmitSerializer(data=_data(qaa=True))  # typo for `qa`
    assert not s.is_valid()
    assert "unknown options for extractor 'kv'" in _errs(s)
    assert "qaa" in _errs(s)


def test_old_flat_format_is_no_longer_accepted():
    """Hard switch (§7.1): the pre-§7.0 shape has no alias. A caller still
    sending the flat form must get a clear 400, not a job that silently ran
    with default options."""
    s = SubmitSerializer(data={
        "file": _pdf_upload(),
        "keys": json.dumps(VALID_KEYS),
        "qa": "false",
        "calculations": "annualize rent",
    })
    assert not s.is_valid()
    assert "extractors" in s.errors  # the now-required field is missing


def test_unknown_key_on_the_extractor_entry_is_rejected():
    """`options` rejects unknowns; the entry itself must too.

    DRF drops unrecognised keys, so a near-miss like `option` (singular) for
    `options` would be discarded whole: `options` defaults to {}, the job runs
    with qa=True and challenge=True, and the caller gets a 202 with no sign
    their configuration was ignored -- at roughly double the LLM spend they
    asked for, since `challenge` alone about doubles it.
    """
    s = SubmitSerializer(data=_data(extractors=json.dumps(
        [{"name": "kv", "keys": VALID_KEYS, "option": {"qa": False, "challenge": False}}]
    )))
    assert not s.is_valid()
    assert "unknown keys on extractor entry" in _errs(s)
    assert "option" in _errs(s)


def test_non_ascii_schema_is_measured_as_utf8_not_escapes():
    """The inner cap must measure the same bytes the outer `extractors` cap did.

    `json.dumps` defaults to ensure_ascii=True, which counts a CJK character as
    a 6-byte \\uXXXX escape rather than its 3-byte UTF-8 form -- so a schema
    could clear the outer raw-byte cap and then be rejected by the inner one as
    "too large", with nothing in the message to explain the discrepancy.
    """
    cjk_keys = {f"項目_{i}": {"description": "請求書の合計金額"} for i in range(40)}
    with mock.patch("agent_kv.execution_serializers.settings") as m:
        _defaults(m)
        # A budget that fits the UTF-8 encoding but NOT the escaped form.
        utf8_len = len(json.dumps(cjk_keys, ensure_ascii=False).encode("utf-8"))
        escaped_len = len(json.dumps(cjk_keys).encode("utf-8"))
        assert escaped_len > utf8_len, "fixture must actually differ between encodings"
        m.AGENT_KV_MAX_SCHEMA_BYTES = utf8_len + 2_000
        s = SubmitSerializer(data=_data(keys=cjk_keys))
        assert s.is_valid(), s.errors
