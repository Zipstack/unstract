"""The submit-time contract for `custom_data` and the highlight options.

Serializer-level, so no DB: these are the refusals a caller sees before
anything is staged, slotted or billed, which is the whole point of putting them
at submit rather than in an engine.

The substitution dialect itself is pinned in `test_custom_data_resolution.py`;
what is pinned here is that the serializer applies it, and refuses what it
should.
"""

import json
import os

import django
import pytest
from django.apps import apps

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "backend.settings.test")
# Guarded exactly as the sibling test modules guard it: the whole backend tree
# collects in one pytest session, so whichever module imports first does the
# setup and the rest must not redo it.
if not apps.ready:
    django.setup()

from django.test import override_settings  # noqa: E402

from agent_kv import execution_serializers as es  # noqa: E402
from agent_kv.constants import LLM_WHISPERER_ADAPTER_ID  # noqa: E402

_ADAPTERS = {
    "llm": "123e4567-e89b-12d3-a456-426614174001",
    "lite_llm": "123e4567-e89b-12d3-a456-426614174002",
    "x2text": "123e4567-e89b-12d3-a456-426614174003",
}


def _options(name, **over):
    ser = es.KVOptionsSerializer if name == "kv" else es.TableOptionsSerializer
    return ser(data=over)


class TestCustomDataValidation:
    """`custom_data` was accepted as ANY JSON and then ignored entirely."""

    def _submit(self, value):
        # Only the one field: `validate_custom_data` is a field validator and
        # runs without the rest of the payload being valid.
        return es.SubmitSerializer().validate_custom_data(value)

    def test_an_object_passes(self):
        assert self._submit({"vendor": "Acme"}) == {"vendor": "Acme"}

    def test_null_passes_and_means_absent(self):
        assert self._submit(None) is None

    @pytest.mark.parametrize(
        "value",
        [["a"], "a string", 42, 1.5, True],
        ids=["list", "str", "int", "float", "bool"],
    )
    def test_non_objects_are_refused(self, value):
        # `JSONField` accepted every one of these before, and a dotted-path
        # lookup against them can never succeed.
        with pytest.raises(Exception) as e:
            self._submit(value)
        assert "must be a JSON object" in str(e.value)

    @override_settings(AGENT_KV_MAX_CUSTOM_DATA_BYTES=100)
    def test_over_the_cap_is_refused_and_names_both_numbers(self):
        big = {"k": "x" * 200}
        with pytest.raises(Exception) as e:
            self._submit(big)
        msg = str(e.value)
        assert str(len(json.dumps(big).encode())) in msg
        assert "100" in msg

    @override_settings(AGENT_KV_MAX_CUSTOM_DATA_BYTES=100)
    def test_exactly_at_the_cap_passes(self):
        # An off-by-one here refuses a payload the documented limit allows.
        value = {"k": "x" * (100 - len(json.dumps({"k": ""}).encode()))}
        assert len(json.dumps(value).encode()) == 100
        assert self._submit(value) == value


class TestHighlightOptions:
    @override_settings(AGENT_KV_HIGHLIGHT_ENABLED=True)
    def test_kv_accepts_the_pair(self):
        ser = _options("kv", enable_highlight=True, enable_word_confidence=True)
        assert ser.is_valid(), ser.errors

    @pytest.mark.parametrize("name", ["kv", "table"])
    @override_settings(AGENT_KV_HIGHLIGHT_ENABLED=True)
    def test_both_extractors_accept_highlight(self, name):
        ser = _options(name, enable_highlight=True)
        assert ser.is_valid(), ser.errors

    @pytest.mark.parametrize("name", ["kv", "table"])
    def test_highlight_defaults_off_for_both(self, name):
        ser = _options(name)
        assert ser.is_valid(), ser.errors
        assert ser.validated_data["enable_highlight"] is False

    def test_kv_word_confidence_defaults_off(self):
        ser = _options("kv")
        assert ser.is_valid(), ser.errors
        assert ser.validated_data["enable_word_confidence"] is False

    @override_settings(AGENT_KV_HIGHLIGHT_ENABLED=True)
    def test_kv_word_confidence_alone_is_refused(self):
        # Prompt Studio forces it off silently; an API field set on purpose
        # gets told instead.
        ser = _options("kv", enable_word_confidence=True)
        assert not ser.is_valid()
        assert "enable_highlight" in str(ser.errors)


class TestWordConfidenceIsKvOnly:
    """`table` refuses the option rather than accepting and ignoring it.

    Per-word confidence arrives from the OCR as one list per line of the
    extracted text, so attaching it to a value needs that value's line
    numbers. `kv` has them on `KeyResult`; table rows do not, and the engine
    keeps row line ranges private to `_build_highlight_data`. Accepting the
    flag would return a result with no confidence in it and nothing saying why.
    """

    @override_settings(AGENT_KV_HIGHLIGHT_ENABLED=True)
    def test_table_refuses_it_even_alongside_highlight(self):
        ser = _options("table", enable_highlight=True, enable_word_confidence=True)
        assert not ser.is_valid()
        assert "not supported by the 'table' extractor" in str(ser.errors)

    @override_settings(AGENT_KV_HIGHLIGHT_ENABLED=True)
    def test_the_error_names_the_field_and_points_at_kv(self):
        # Not the generic "unknown options" message: the field is real and
        # documented, so a caller who aimed it at the wrong extractor needs to
        # be told that, not that it does not exist.
        ser = _options("table", enable_word_confidence=True)
        assert not ser.is_valid()
        errors = str(ser.errors)
        assert "enable_word_confidence" in errors
        assert "'kv'" in errors
        assert "unknown options" not in errors

    def test_table_never_reports_a_word_confidence_value(self):
        # The field is gone from the serializer, so it cannot reach
        # `executor_params` and be read by an engine that has no use for it.
        ser = _options("table")
        assert ser.is_valid(), ser.errors
        assert "enable_word_confidence" not in ser.validated_data

    @pytest.mark.parametrize("name", ["kv", "table"])
    @override_settings(AGENT_KV_HIGHLIGHT_ENABLED=False)
    def test_refused_when_the_deployment_has_it_off(self, name):
        ser = _options(name, enable_highlight=True)
        assert not ser.is_valid()
        assert "not available on this deployment" in str(ser.errors)

    @pytest.mark.parametrize("name", ["kv", "table"])
    @override_settings(AGENT_KV_HIGHLIGHT_ENABLED=False)
    def test_off_by_default_is_not_refused_when_the_flag_is_off(self, name):
        # The flag gates ASKING for it, not the field's existence: a caller who
        # sends neither option must not be refused by a deployment that has the
        # feature disabled.
        ser = _options(name)
        assert ser.is_valid(), ser.errors

    @pytest.mark.parametrize("name", ["kv", "table"])
    def test_a_misspelt_option_is_still_refused(self, name):
        # The unknown-field rule must survive the new fields being added.
        ser = _options(name, enable_highlights=True)
        assert not ser.is_valid()
        assert "unknown options" in str(ser.errors)


class TestSubstitutionIsApplied:
    """That the serializer runs the resolver, and turns a miss into a 400."""

    def _entry(self, **over):
        entry = {
            "name": "kv",
            "keys": {"total": {"description": "the {{custom_data.kind}} total"}},
            "options": {"key_notes": "from {{custom_data.vendor}}"},
            "adapters": dict(_ADAPTERS),
        }
        entry.update(over)
        return entry

    def test_resolution_is_skipped_entirely_when_nothing_references_custom_data(self):
        """The gate the serializer uses before walking anything.

        A submit with no placeholders must not pay for a recursive walk of its
        schema, and -- more importantly -- must not be refused for having sent
        no `custom_data`. Without this gate, every request with instruction
        text and no custom data would hit the "no custom_data was sent" branch.
        """
        from agent_kv import custom_data as cd

        plain = self._entry(
            keys={"total": {"description": "the total"}},
            options={"key_notes": "no placeholders here"},
        )
        assert cd.entry_references(plain) == []
        # And resolving it anyway is a no-op rather than an error, which is
        # what makes the gate an optimisation and not a correctness crutch.
        assert cd.resolve_entry(plain, None) == plain

    def test_every_referenced_path_is_found_across_options_and_schema(self):
        from agent_kv import custom_data as cd

        assert sorted(cd.entry_references(self._entry())) == ["kind", "vendor"]

    def test_a_missing_key_is_reported_against_custom_data(self):
        from agent_kv import custom_data as cd

        entry = self._entry()

        with pytest.raises(cd.MissingCustomDataKey) as e:
            cd.resolve_entry(entry, {"vendor": "Acme"})
        assert e.value.path == "kind"


class TestWhispererGateConstant:
    def test_the_whisperer_id_matches_the_sdk(self):
        """The literal in `constants.py` against the SDK's own `get_id()`.

        The constant is a literal so a request path does not import the SDK
        adapter registry. This is what stops that literal drifting: if the
        adapter's id ever changes, the gate would silently refuse every
        LLMWhisperer adapter and highlight would be unreachable.
        """
        from unstract.sdk1.adapters.x2text.llm_whisperer_v2.src.llm_whisperer_v2 import (
            LLMWhispererV2,
        )

        assert LLM_WHISPERER_ADAPTER_ID == LLMWhispererV2.get_id()
