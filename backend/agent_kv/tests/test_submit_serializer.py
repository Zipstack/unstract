"""Submit-serializer rules, exercised mostly through the `table` extractor.

Both extractors are routed (`EXTRACTOR_ROUTES`), but the request-level rules --
file type, size, page cap, page range, timeout, the extractor-scoped wire
format -- are the same for either, so most cases here name `table` and drive
them through that one.

The `kv` cases that do exist carry
`@override_settings(AGENT_KV_KV_EXTRACTOR_ENABLED=True)`: routing `kv` is not
the same as accepting it, and the production default is off until a deployment
states that its fleet drains `celery_executor_agentic_kv`.

`KVOptionsSerializer` is additionally tested *directly*, which is how it was
covered while `kv` was unroutable and remains the cheaper way to exercise the
option grammar without building a whole submit.
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

from django.conf import settings  # noqa: E402
from django.core.files.uploadedfile import SimpleUploadedFile  # noqa: E402
from django.test import override_settings  # noqa: E402
from rest_framework import serializers  # noqa: E402

from agent_kv.constants import TABLE_EXTRACTOR_NAME, V1_EXTRACTOR_NAME  # noqa: E402
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
    # Production default. `kv` is routed but not accepted until a deployment
    # says its fleet drains the queue -- see `enabled_extractors()`.
    m.AGENT_KV_KV_EXTRACTOR_ENABLED = False


# ---------------------------------------------------------------------------
# The routing this deployment actually ships
# ---------------------------------------------------------------------------
@override_settings(AGENT_KV_KV_EXTRACTOR_ENABLED=True)
def test_a_kv_submit_is_accepted_through_the_same_endpoint():
    """One API, one selector: `extractors[].name` picks the engine.

    This is the whole of the feature. The payload differs from a `table` submit
    in three places -- the name, a schema-shaped `keys` instead of
    `{"target_table": ...}`, and KV's own options -- and in nothing else: same
    endpoint, same file part, same staging, same page cap, same adapters block.

    It replaces `test_a_kv_submit_is_refused_at_the_serializer`, which asserted
    the 400 that stood while the engine shipped on its own branch and nothing
    drained `celery_executor_agentic_kv`. That refusal was never the intended
    end state; it was load-bearing for exactly as long as the queue was
    undrained, and `test_queue_wiring_is_derived.py` now derives that
    precondition from `EXTRACTOR_ROUTES` on every run.
    """
    s = SubmitSerializer(
        data=_data(
            extractors=json.dumps(
                [
                    {
                        "name": "kv",
                        "keys": {"total": {"description": "Grand total"}},
                        "adapters": TABLE_ADAPTERS,
                        "options": {"qa": False},
                    }
                ]
            )
        )
    )
    assert s.is_valid(), _errs(s)
    entry = s.validated_data["extractors"][0]
    assert entry["name"] == "kv"
    assert entry["options"]["qa"] is False


@override_settings(AGENT_KV_KV_EXTRACTOR_ENABLED=True)
def test_a_kv_submit_without_adapters_is_refused_at_submit():
    """The KV executor requires all three roles
    (`agentic_kv.constants.ParamKeys.REQUIRED_ADAPTERS`) and fails the job
    naming whichever is missing. That failure costs a concurrency slot and the
    staging it already billed, so the same requirement is enforced here, before
    any of that -- the same bargain the table extractor already made.
    """
    s = SubmitSerializer(
        data=_data(
            extractors=json.dumps(
                [{"name": "kv", "keys": {"total": {"description": "Grand total"}}}]
            )
        )
    )
    assert not s.is_valid()
    errs = _errs(s)
    assert "llm" in errs and "x2text" in errs


def test_both_extractors_are_supported():
    from agent_kv.execution_serializers import SUPPORTED_EXTRACTORS

    assert set(SUPPORTED_EXTRACTORS) == {"kv", "table"}


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


def test_the_cap_counts_the_WHOLE_document_even_for_a_one_page_range():
    """A page range does not reduce what is OCR'd, so it must not reduce the cap.

    This test previously asserted the opposite, on the premise that "one page
    of a two-page document is one page of OCR". The engine disagrees: it
    renders every page (`convert_pdf_to_images(file_content, dir)`) and OCRs
    the whole file -- `X2Text.process` takes `input_file_path` and no range --
    then `load_pages(starting_page=, ending_page=)` filters which rendered
    pages the agents read. A range selects what is EXTRACTED, never what is
    scanned or billed.

    It also disagreed with the worker, which refuses on `pages_total`, so the
    caller got a 202, a slot and a staged upload before being failed anyway.
    Caught in review on #2317 / unstract-cloud#1828; the Greptile finding the
    old version cited had the same false premise.
    """
    with mock.patch("agent_kv.execution_serializers.settings") as m:
        _defaults(m)
        m.AGENT_KV_MAX_PAGES = 1
        s = SubmitSerializer(data=_data(page_start=1, page_end=1))

        assert not s.is_valid()
        assert "Document has 2 pages" in _errs(s)
        assert "does not reduce this" in _errs(s)


def test_an_open_ended_range_is_capped_at_the_last_page():
    """`page_end` past the end selects to the end, it does not inflate the count.

    `pages_selected` is still computed and still correct -- it is the honest
    count of what will be extracted, and the refusal message uses it. It is
    simply not what the cap compares against.
    """
    with mock.patch("agent_kv.execution_serializers.settings") as m:
        _defaults(m)
        m.AGENT_KV_MAX_PAGES = 2
        s = SubmitSerializer(data=_data(page_start=2, page_end=999))
        assert s.is_valid(), s.errors
        assert s.pages_selected == 1
        assert s.pages_total == 2


def test_the_submit_cap_and_the_worker_cap_compare_the_same_quantity():
    """The cross-repo half of the bug, pinned so the two cannot drift again.

    `dispatch.py` sends `pages_total` and `max_pages`; the cloud worker
    refuses when `pages_total > max_pages`. If this side ever caps something
    else, a submit it accepts is one the worker rejects -- after the 202,
    after the slot, after the upload.
    """
    with mock.patch("agent_kv.execution_serializers.settings") as m:
        _defaults(m)
        m.AGENT_KV_MAX_PAGES = 1
        s = SubmitSerializer(data=_data(page_start=1, page_end=2))

        assert not s.is_valid()
        # Same comparison the worker makes: measured document pages vs the cap.
        assert "Document has 2 pages" in _errs(s)


def test_page_start_past_the_end_of_the_document_is_rejected():
    """Otherwise the selection is empty and the job runs over nothing, billed."""
    s = SubmitSerializer(data=_data(page_start=5))
    assert not s.is_valid()
    assert "past the end" in _errs(s)


def test_extractors_not_json_rejected():
    s = SubmitSerializer(data=_data(extractors="{not json"))
    assert not s.is_valid()
    assert "extractors" in s.errors


#: Nesting depth that makes CPython's JSON scanner give up. NOT
#: `sys.getrecursionlimit()`: the C scanner keeps its own accounting and
#: swallows 2000 levels without complaint -- a first cut of the test below
#: used that and passed against the UNFIXED code, which is the whole failure
#: mode these tests exist to catch. 100k levels is 200 KB, comfortably inside
#: the 256 KiB `AGENT_KV_MAX_SCHEMA_BYTES` cap, and the test asserts both of
#: those facts rather than trusting this comment.
_JSON_OVERFLOW_DEPTH = 100_000


def test_deeply_nested_extractors_is_a_400_not_a_500():
    """`RecursionError` is a RuntimeError, so the ValueError/TypeError clause
    around `json.loads` never caught it and the request 500'd on an input the
    caller controls entirely. Reported by Greptile on PR #2317.
    """
    nested = "[" * _JSON_OVERFLOW_DEPTH + "]" * _JSON_OVERFLOW_DEPTH

    # The payload has to stay INSIDE the byte cap, or this proves only that
    # the cap works -- which it already did.
    assert len(nested.encode()) < settings.AGENT_KV_MAX_SCHEMA_BYTES
    # And it has to actually trip the decoder, or the test passes for the
    # wrong reason on a future interpreter that parses it happily.
    with pytest.raises(RecursionError):
        json.loads(nested)

    s = SubmitSerializer(data=_data(extractors=nested))

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
# Reached through a real submit now that `kv` is routable (see
# `test_a_kv_submit_is_accepted_through_the_same_endpoint`); these exercise the
# serializer directly because its rules are easier to state one at a time than
# through a multipart payload.
#
# This section was written while the class was DORMANT -- `kv` was unroutable,
# so nothing reached it through a submit -- on the reasoning that dormant and
# untested is how a one-line re-enable turns into a regression. That one line
# has now been added, and these tests are why it was one line.
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
# `kv` is the one extractor with no entry in `_KEYS_SERIALIZERS`, deliberately:
# its `keys` IS a compiled schema rather than a fixed field set, so it falls
# through to the compiler. That fallthrough is live -- a `kv` submit reaches it
# -- and it is also the contract for any future extractor added without a keys
# serializer.
#
# It used to be unreachable through a submit (`validate_name` refused `kv`
# before `_validated_keys` ran) and was tested by calling it directly. The
# direct calls are kept: they state one rule at a time.
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


# ---------------------------------------------------------------------------
# webhook_url: refuse at submit what the sink refuses at delivery.
# ---------------------------------------------------------------------------
#
# `URLField` alone accepts `http://`, `localhost` and private literals, and
# `send_webhook` is called without `allow_http`, so the sink allows https to
# public hosts only. The caller got a 202 and a webhook that never arrived —
# and on the cancel path the refusal looked like a delivery failure, so
# `agent_kv_cancelled` retried a URL that could never work until it poisoned.
# Reported by @athul-rs on #2317.


@pytest.mark.parametrize(
    "url",
    [
        "http://example.com/hook",  # scheme the sink will not dial
        "https://localhost/hook",
        "https://127.0.0.1/hook",
        "https://10.0.0.5/hook",
        "https://user:pw@example.com/hook",  # credentials in the URL
    ],
)
def test_a_webhook_url_the_sink_would_refuse_is_rejected_at_submit(url):
    s = SubmitSerializer(data=_data(webhook_url=url))

    assert not s.is_valid()
    assert "webhook_url" in s.errors


@pytest.mark.parametrize("url", ["https://example.com/hook", ""])
def test_a_deliverable_webhook_url_is_accepted(url):
    """Including the empty string: the field is optional and blank means
    "do not notify", which must not become a validation error.
    """
    s = SubmitSerializer(data=_data(webhook_url=url))

    assert s.is_valid(), s.errors


def test_the_submit_check_matches_what_the_sink_allows():
    """Guards the pair. The sink calls `send_webhook` with no `allow_http`, so
    it permits https only; if this side ever widened to http the caller would
    be back to a 202 and silence.
    """
    import inspect

    from agent_kv import execution_serializers

    source = inspect.getsource(
        execution_serializers.SubmitSerializer.validate_webhook_url
    )

    assert 'allowed_schemes=("https",)' in source
    # DNS stays off the request thread; `getaddrinfo` honours no timeout.
    assert "resolve=False" in source


@pytest.mark.parametrize(
    ("extractor", "keys"),
    [
        (V1_EXTRACTOR_NAME, {"total": {"description": "Grand total"}}),
        (TABLE_EXTRACTOR_NAME, {"target_table": "Line items"}),
    ],
)
@override_settings(AGENT_KV_KV_EXTRACTOR_ENABLED=True)
def test_an_unknown_adapter_role_is_refused_and_names_its_extractor(extractor, keys):
    """Pins the `extractor_name` indirection the adapters refactor introduced.

    The unknown-adapters message used to interpolate a hardcoded
    `TABLE_EXTRACTOR_NAME`; it now reads a base-class attribute that defaults
    to `""`. Nothing exercised that path for either subclass, so setting
    BOTH subclasses' `extractor_name` to `""` left the whole suite green and
    the API would have reported `unknown adapters for extractor '': [...]`.

    The refusal itself matters as much as the name: an adapter role the caller
    named and the engine will not use is a resource silently ignored behind a
    202 -- the same shape the entry-level unknown-key check exists to prevent.
    """
    adapters = dict(TABLE_ADAPTERS)
    adapters["embedding"] = "7f3c1a90-0000-4000-8000-000000000009"
    s = SubmitSerializer(
        data=_data(
            extractors=json.dumps(
                [{"name": extractor, "keys": keys, "adapters": adapters}]
            )
        )
    )
    assert not s.is_valid()
    msg = str(s.errors)
    assert "embedding" in msg, msg
    assert f"'{extractor}'" in msg, msg
