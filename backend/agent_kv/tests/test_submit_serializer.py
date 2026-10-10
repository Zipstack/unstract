"""Submit-serializer rules for the table extractor.

This deployment routes `table` and nothing else (`EXTRACTOR_ROUTES`), so every
submit built here names `table`. The request-level rules -- file type, size,
page cap, page range, timeout, the extractor-scoped wire format -- are the same
for any extractor and are exercised through that one.

`KVOptionsSerializer` is still in the tree and still tested, but it is tested
*directly* rather than through a submit: with `kv` out of `EXTRACTOR_ROUTES` a
`kv` entry is refused at `validate_name` before any options validator runs, so
driving those rules through `SubmitSerializer` would assert nothing about them.
"""

import json
import os
from unittest import mock

import django
import pytest
from django.apps import apps

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "backend.settings.test")
if not apps.ready:
    django.setup()

from django.core.files.uploadedfile import SimpleUploadedFile  # noqa: E402
from rest_framework import serializers  # noqa: E402

from agent_kv.execution_serializers import (  # noqa: E402
    ExtractorSerializer,
    KVOptionsSerializer,
    SubmitSerializer,
)

FIXTURES = os.path.join(os.path.dirname(__file__), "fixtures")

#: The table extractor's `keys`: the thing being asked for is a table, named.
TABLE_KEYS = {"target_table": "Rent roll"}


def _pdf_upload(name="doc.pdf"):
    with open(os.path.join(FIXTURES, "two_page.pdf"), "rb") as f:
        return SimpleUploadedFile(name, f.read(), content_type="application/pdf")


# Fields that describe the REQUEST rather than an extractor (spec §7.1).
# Anything else passed to _data() is routed into the table extractor's options,
# so each test still reads as "submit with this one thing changed".
_JOB_LEVEL = {
    "file",
    "extractors",
    "page_start",
    "page_end",
    "timeout",
    "tags",
    "custom_data",
    "webhook_url",
}


#: The platform adapters a `table` submit must name. All three are REQUIRED --
#: the engine needs two LLMs and an OCR source, and this API resolves them from
#: the caller's own adapter instances rather than from operator env vars.
#: Ownership and type are checked in the VIEW against the Bearer key's org
#: (`execution_views._resolved_adapters`); the serializer only checks shape, so
#: these can be any UUIDs here.
TABLE_ADAPTERS = {
    "llm": "11111111-1111-1111-1111-111111111111",
    "lite_llm": "22222222-2222-2222-2222-222222222222",
    "x2text": "33333333-3333-3333-3333-333333333333",
}


def _data(**over):
    """Build a submit payload in the extractor-scoped wire format (§7.0)."""
    keys = over.pop("keys", TABLE_KEYS)
    adapters = over.pop("adapters", TABLE_ADAPTERS)
    options = {k: over.pop(k) for k in list(over) if k not in _JOB_LEVEL}
    d = {
        "file": _pdf_upload(),
        "extractors": json.dumps(
            [
                {
                    "name": "table",
                    "keys": keys,
                    "adapters": adapters,
                    "options": options,
                }
            ]
        ),
    }
    d.update(over)
    return d


def _errs(s):
    """All validation errors as one string.

    Per-extractor failures surface nested under `extractors`, so asserting on a
    specific top-level key would just be asserting on DRF's nesting shape rather
    than on the rejection actually happening.
    """
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


# ---------------------------------------------------------------------------
# The routing this deployment actually ships
# ---------------------------------------------------------------------------
def test_a_kv_submit_is_refused_at_the_serializer():
    """The guard on the single most important line in this carve-out.

    `agentic_kv` is not deployed here, so nothing consumes
    `celery_executor_agentic_kv`. If `kv` were routable, this submit would
    return 202, dispatch into a queue with no consumer, and sit in DISPATCHED
    forever -- no error at the producer, nothing in any log to find. A 400 at
    the serializer is the whole difference between a clear refusal and a job
    that silently never runs.
    """
    s = SubmitSerializer(
        data=_data(
            extractors=json.dumps(
                [{"name": "kv", "keys": {"total": {"description": "Grand total"}}}]
            )
        )
    )
    assert not s.is_valid()
    assert "unknown extractor" in _errs(s)
    assert "'kv'" in _errs(s)


def test_table_is_the_only_supported_extractor():
    from agent_kv.execution_serializers import SUPPORTED_EXTRACTORS

    assert SUPPORTED_EXTRACTORS == ("table",)


# ---------------------------------------------------------------------------
# Request-level rules, exercised through the extractor this deployment serves
# ---------------------------------------------------------------------------
def test_valid_submit_counts_pages_and_defaults_its_options():
    s = SubmitSerializer(data=_data())
    assert s.is_valid(), s.errors
    assert s.pages_total == 2
    entry = s.validated_data["extractors"][0]
    assert entry["name"] == "table"
    assert entry["keys"]["target_table"] == "Rent roll"
    assert entry["options"]["number_format"] == "US"
    assert entry["options"]["enable_header_mapping"] is False


def test_a_table_entry_without_a_target_table_is_rejected():
    """`target_table` is the engine's one required extraction parameter; the
    caller's actual mistake is not naming the table.
    """
    s = SubmitSerializer(data=_data(keys={}))
    assert not s.is_valid()
    assert "target_table" in _errs(s)


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
    """No range given, so the whole document is the selection."""
    with mock.patch("agent_kv.execution_serializers.settings") as m:
        _defaults(m)
        m.AGENT_KV_MAX_PAGES = 1
        s = SubmitSerializer(data=_data())
        assert not s.is_valid()
        assert "pages" in str(s.errors).lower()


def test_page_cap_counts_the_selected_range_not_the_whole_document():
    """The cap bounds the work the job will DO, not the size of the file.

    A caller asking for one page of a two-page document is requesting one page
    of OCR and extraction. Counting the whole document rejected requests that
    were inside the documented limit. Reported by Greptile on #2317.
    """
    with mock.patch("agent_kv.execution_serializers.settings") as m:
        _defaults(m)
        m.AGENT_KV_MAX_PAGES = 1
        s = SubmitSerializer(data=_data(page_start=1, page_end=1))
        assert s.is_valid(), s.errors
        assert s.pages_selected == 1
        # The measured document count is unchanged -- it is what metering and
        # the status document report, and only the cap comparison moved.
        assert s.pages_total == 2


def test_an_open_ended_range_is_capped_at_the_last_page():
    """`page_end` past the end selects to the end, it does not inflate the count."""
    with mock.patch("agent_kv.execution_serializers.settings") as m:
        _defaults(m)
        m.AGENT_KV_MAX_PAGES = 2
        s = SubmitSerializer(data=_data(page_start=2, page_end=999))
        assert s.is_valid(), s.errors
        assert s.pages_selected == 1


def test_a_selected_range_over_the_cap_is_still_rejected():
    with mock.patch("agent_kv.execution_serializers.settings") as m:
        _defaults(m)
        m.AGENT_KV_MAX_PAGES = 1
        s = SubmitSerializer(data=_data(page_start=1, page_end=2))
        assert not s.is_valid()
        assert "Requested 2 pages" in _errs(s)


def test_page_start_past_the_end_of_the_document_is_rejected():
    """Otherwise the selection is empty and the job runs over nothing, billed."""
    s = SubmitSerializer(data=_data(page_start=5))
    assert not s.is_valid()
    assert "past the end" in _errs(s)


def test_extractors_not_json_rejected():
    s = SubmitSerializer(data=_data(extractors="{not json"))
    assert not s.is_valid()
    assert "extractors" in s.errors


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


# ---------------------------------------------------------------------------
# Extractor-scoped wire format (spec §7.0/§7.1). These rules exist so a caller
# learns immediately that something is unsupported, rather than having the
# request quietly run as something other than what they asked for.
# ---------------------------------------------------------------------------
def test_unknown_extractor_name_rejected():
    s = SubmitSerializer(
        data=_data(extractors=json.dumps([{"name": "bogus", "keys": TABLE_KEYS}]))
    )
    assert not s.is_valid()
    assert "unknown extractor" in _errs(s)


def test_multiple_extractors_rejected_until_fan_out_exists():
    """The FORMAT is fixed before launch; the fan-out execution is not built.

    Accepting two entries and running only the first would be the silent kind
    of wrong -- the caller is billed for a job that ignored half the request.
    """
    two = [
        {"name": "table", "keys": TABLE_KEYS},
        {"name": "table", "keys": TABLE_KEYS},
    ]
    s = SubmitSerializer(data=_data(extractors=json.dumps(two)))
    assert not s.is_valid()
    assert "multiple extractors are not supported yet" in _errs(s)


def test_empty_or_non_list_extractors_rejected():
    for bad in ("[]", '{"name": "table"}', '"table"'):
        s = SubmitSerializer(data=_data(extractors=bad))
        assert not s.is_valid(), bad
        assert "non-empty JSON array" in _errs(s)


def test_unknown_option_is_rejected_not_silently_dropped():
    """DRF drops unknown fields by default; for per-extractor options that would
    mean a typo'd or misaddressed knob silently changing what the job runs.
    """
    s = SubmitSerializer(data=_data(number_formatt="EU"))  # typo for `number_format`
    assert not s.is_valid()
    assert "unknown options for extractor 'table'" in _errs(s)
    assert "number_formatt" in _errs(s)


def test_a_kv_option_on_a_table_entry_is_rejected():
    """The cross-extractor case the per-extractor serializers exist for: `qa`
    is a KV pipeline knob and means nothing to the table engine. Dropped
    silently, the caller would believe they had turned something off.
    """
    s = SubmitSerializer(data=_data(qa=False))
    assert not s.is_valid()
    assert "unknown options for extractor 'table'" in _errs(s)
    assert "qa" in _errs(s)


def test_old_flat_format_is_no_longer_accepted():
    """Hard switch (§7.1): the pre-§7.0 shape has no alias. A caller still
    sending the flat form must get a clear 400, not a job that silently ran
    with default options.
    """
    s = SubmitSerializer(
        data={
            "file": _pdf_upload(),
            "keys": json.dumps(TABLE_KEYS),
            "number_format": "EU",
        }
    )
    assert not s.is_valid()
    assert "extractors" in s.errors  # the now-required field is missing


def test_unknown_key_on_the_extractor_entry_is_rejected():
    """`options` rejects unknowns; the entry itself must too.

    DRF drops unrecognised keys, so a near-miss like `option` (singular) for
    `options` would be discarded whole: `options` defaults to {}, the job runs
    with every default, and the caller gets a 202 with no sign their
    configuration was ignored.
    """
    s = SubmitSerializer(
        data=_data(
            extractors=json.dumps(
                [{"name": "table", "keys": TABLE_KEYS, "option": {"number_format": "EU"}}]
            )
        )
    )
    assert not s.is_valid()
    assert "unknown keys on extractor entry" in _errs(s)
    assert "option" in _errs(s)


# ---------------------------------------------------------------------------
# KVOptionsSerializer, tested directly.
#
# The class is dormant on this deployment -- `kv` is not routable, so nothing
# reaches it through a submit -- but it stays in the tree so the branch that
# carries the KV engine re-enables the extractor with one line rather than a
# content merge. Dormant and untested is how a one-line re-enable turns into a
# regression, so its rules are asserted here against the serializer itself.
# ---------------------------------------------------------------------------
def _kv_options(**over):
    s = KVOptionsSerializer(data=over)
    return s


def test_kv_options_default_qa_and_challenge_on():
    with mock.patch("agent_kv.execution_serializers.settings") as m:
        _defaults(m)
        s = _kv_options()
        assert s.is_valid(), s.errors
        assert s.validated_data["qa"] is True
        assert s.validated_data["challenge"] is True
        assert s.validated_data["extraction_mode"] == "whole-doc"


def test_kv_calculations_rejected_when_disabled():
    with mock.patch("agent_kv.execution_serializers.settings") as m:
        _defaults(m)
        m.AGENT_KV_CALCULATIONS_ENABLED = False
        s = _kv_options(calculations="annualize rent")
        assert not s.is_valid()
        assert "not available" in str(s.errors)


def test_kv_calculations_accepted_when_enabled():
    with mock.patch("agent_kv.execution_serializers.settings") as m:
        _defaults(m)
        m.AGENT_KV_CALCULATIONS_ENABLED = True
        assert _kv_options(calculations="annualize rent").is_valid()


def test_kv_calculations_cap():
    # AGENT_KV_CALCULATIONS_ENABLED must be mocked True here: real settings
    # default it False, so an unmocked run hits the feature-gate branch (a
    # different error) instead of the byte-size cap this test is named for.
    with mock.patch("agent_kv.execution_serializers.settings") as m:
        _defaults(m)
        m.AGENT_KV_CALCULATIONS_ENABLED = True
        s = _kv_options(calculations="x" * 30_000)
        assert not s.is_valid()
        assert "calculations" in str(s.errors)
        assert "20000 bytes" in str(s.errors)


def test_kv_structured_output_rejected_when_disabled():
    with mock.patch("agent_kv.execution_serializers.settings") as m:
        _defaults(m)
        m.AGENT_KV_STRUCTURED_OUTPUT_ENABLED = False
        s = _kv_options(structured_output=True)
        assert not s.is_valid()
        assert "structured_output" in str(s.errors)


def test_kv_empty_calculations_and_false_structured_output_pass_when_disabled():
    with mock.patch("agent_kv.execution_serializers.settings") as m:
        _defaults(m)
        assert _kv_options(calculations="", structured_output=False).is_valid()


def test_kv_unknown_option_is_rejected():
    with mock.patch("agent_kv.execution_serializers.settings") as m:
        _defaults(m)
        s = _kv_options(qaa=True)  # typo for `qa`
        assert not s.is_valid()
        assert "unknown options for extractor 'kv'" in str(s.errors)


# ---------------------------------------------------------------------------
# Extractor identity must be decided ONCE.
#
# `validate_keys` used to branch on raw `initial_data["name"]` while
# `validate_name` saw the value DRF had already trimmed
# (`CharField.trim_whitespace` defaults True). So `" table "` passed the name
# check as `table` and then took the **kv** branch for keys, never running
# `TableKeysSerializer`.
#
# A kv-shaped payload compiles cleanly as a KV schema, so the submit returned
# 202 and dispatched to `agentic_table` with a `target_table` that is a dict
# rather than the string the binding requires -- staged, billed, then failed at
# the executor.
#
# Reported as 2.1 in the branch review.
# ---------------------------------------------------------------------------
def test_a_padded_extractor_name_still_validates_keys_as_that_extractor():
    s = SubmitSerializer(
        data=_data(
            extractors=json.dumps(
                [
                    {
                        # Trimmed to "table" by validate_name...
                        "name": " table ",
                        # ...but this is a KV-shaped schema, not a table one. It
                        # compiles fine as KV, which is how it used to reach 202.
                        "keys": {"target_table": {"description": "Grand total"}},
                    }
                ]
            )
        )
    )

    assert not s.is_valid(), (
        "a kv-shaped keys payload was accepted for the table extractor; the "
        "job would stage, bill and then fail at the executor on target_table"
    )
    assert "target_table" in _errs(s)


def test_a_padded_name_is_still_normalised_for_routing():
    """The trim itself is fine and worth keeping -- the bug was deciding
    identity twice, not accepting whitespace.
    """
    s = SubmitSerializer(
        data=_data(
            extractors=json.dumps(
                [{"name": " table ", "keys": TABLE_KEYS, "adapters": TABLE_ADAPTERS}]
            )
        )
    )

    assert s.is_valid(), s.errors
    assert s.validated_data["extractors"][0]["name"] == "table"


def test_table_keys_are_validated_through_the_keys_serializer():
    """Reaching TableKeysSerializer is what rejects unknown members; the kv
    fallback would have compiled them as a schema instead.
    """
    s = SubmitSerializer(
        data=_data(
            extractors=json.dumps(
                [{"name": "table", "keys": {"target_table": "T", "bogus": 1}}]
            )
        )
    )

    assert not s.is_valid()
    assert "unknown keys for extractor 'table'" in _errs(s)


# ---------------------------------------------------------------------------
# 2.20: `compile_schema` is called in the no-keys-serializer fall-through for
# what it REFUSES, not for what it returns.
#
# The `CompiledSchema` used to be stashed on `ExtractorSerializer.compiled` and
# collected into `SubmitSerializer.compiled`, which no non-test code read --
# `dispatch_job` sends the raw `keys` dict and the engine recompiles. Deleting
# the attribute must not quietly delete the 400, which is the only reason the
# call is there.
#
# The branch is DORMANT on this deployment: `kv` is the only extractor without
# a keys serializer and `validate_name` refuses it before `_validated_keys`
# runs, so it is reached by calling it directly. That is the point -- it is the
# contract for the next extractor added without one, and nothing else covers it.
# ---------------------------------------------------------------------------


def test_the_schema_compiler_fallthrough_still_rejects_a_bad_schema():
    ser = ExtractorSerializer()

    with pytest.raises(serializers.ValidationError) as exc:
        # A leaf with no `description` is refused by the ported compiler.
        ser._validated_keys("some_future_extractor", {"total": {}})

    assert "keys" in exc.value.detail


def test_the_schema_compiler_fallthrough_returns_the_raw_spec():
    """What reaches `dispatch_job` is the submitted dict, unchanged."""
    ser = ExtractorSerializer()
    spec = {"total": {"description": "The grand total", "format": "currency"}}

    assert ser._validated_keys("some_future_extractor", spec) is spec


def test_neither_serializer_still_carries_a_compiled_attribute():
    """A `compiled` that is populated and never read reads as plumbing."""
    for cls in (ExtractorSerializer, SubmitSerializer):
        assert not hasattr(cls, "compiled"), (
            f"{cls.__name__}.compiled was dead: `dispatch_job` sends the raw "
            "keys dict, and the compiled form cannot cross the queue anyway"
        )
