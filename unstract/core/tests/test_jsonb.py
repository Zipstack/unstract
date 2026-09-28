"""Tests for the shared ``jsonb`` encoder.

The property under test is the one that cost UN-4126 an hour-long hang per
affected execution: whatever :func:`dumps_for_jsonb` returns must survive a
``%s::jsonb`` cast. These assert the encoder's half of that (the escapes are
gone from the emitted text); the DB half is asserted against a real Postgres in
``workers/tests/test_pg_result_backend.py``.
"""

import json
import math

import pytest

from unstract.core.jsonb import dumps_for_jsonb, sanitize_for_jsonb

# The two escapes Postgres refuses to convert to text.
NUL = "\x00"
LONE_SURROGATE = "\ud800"


class TestSanitizeForJsonb:
    def test_strips_nul_from_string(self):
        assert sanitize_for_jsonb(f"POZFBBOK{NUL}") == "POZFBBOK"

    def test_strips_lone_surrogate(self):
        assert sanitize_for_jsonb(f"a{LONE_SURROGATE}b") == "ab"

    def test_strips_lone_low_surrogate(self):
        assert sanitize_for_jsonb("a" + chr(0xDC00) + "b") == "ab"

    def test_preserves_a_valid_surrogate_pair(self):
        # A well-formed high+low pair IS storable: Postgres combines it into the
        # astral character it encodes (verified against a live server). A plain
        # [high-low] character class matches BOTH halves and would silently drop
        # an emoji from an extracted result.
        pair = chr(0xD83D) + chr(0xDE00)  # U+1F600 GRINNING FACE
        assert sanitize_for_jsonb(f"a{pair}b") == f"a{pair}b"

    def test_strips_only_the_unpaired_half(self):
        # Lone high followed by a valid pair: the loner goes, the pair stays.
        pair = chr(0xD83D) + chr(0xDE00)
        assert sanitize_for_jsonb(chr(0xD800) + pair) == pair

    def test_keeps_other_control_characters(self):
        # Only NUL and unpaired surrogates are rejected by jsonb; \x01 round-trips
        # fine and stripping it would silently alter data for no reason.
        assert sanitize_for_jsonb("a\x01b") == "a\x01b"

    def test_cleans_nested_values_and_keys(self):
        dirty = {f"k{NUL}": [{"inner": f"v{NUL}"}, (f"t{NUL}",)]}
        assert sanitize_for_jsonb(dirty) == {"k": [{"inner": "v"}, ["t"]]}

    def test_leaves_non_strings_untouched(self):
        value = {"n": 1, "f": 1.5, "b": True, "none": None}
        assert sanitize_for_jsonb(value) == value

    def test_does_not_mutate_input(self):
        original = {"a": [f"x{NUL}"]}
        sanitize_for_jsonb(original)
        assert original == {"a": [f"x{NUL}"]}

    def test_clean_payload_is_unchanged(self):
        value = {"output": {"invoice_number": "POZFBBOK", "amount": 42}}
        assert sanitize_for_jsonb(value) == value


class TestDumpsForJsonb:
    def test_emits_no_nul_escape(self):
        # The exact production payload shape from UN-4126.
        out = dumps_for_jsonb({"output": {"invoice_number": f"POZFBBOK{NUL}"}})
        assert "\\u0000" not in out
        assert json.loads(out) == {"output": {"invoice_number": "POZFBBOK"}}

    def test_emits_no_surrogate_escape(self):
        out = dumps_for_jsonb({"a": LONE_SURROGATE})
        assert "\\ud800" not in out.lower()

    def test_keeps_a_valid_pair_in_the_encoded_output(self):
        pair = chr(0xD83D) + chr(0xDE00)
        out = dumps_for_jsonb({"a": pair})
        # json.dumps emits the pair as two escapes; Postgres accepts and combines
        # them, so they must still be there.
        assert out.lower() == '{"a": "\\ud83d\\ude00"}'

    @pytest.mark.parametrize(
        "bad", [math.nan, math.inf, -math.inf], ids=["nan", "inf", "-inf"]
    )
    def test_rejects_non_finite_numbers(self, bad):
        # Not repairable: null/0 would corrupt a value rather than clean it, so
        # the writer is told instead of the database finding out.
        with pytest.raises(ValueError):
            dumps_for_jsonb({"confidence": bad})

    def test_default_hook_output_is_sanitised_too(self):
        # The pre-walk runs before json.dumps, so a string the hook manufactures
        # at encode time would otherwise never be inspected — and `str` on an
        # exception carrying document text is exactly how a NUL gets there.
        class Carrier:
            def __str__(self):
                return "extracted" + NUL + "text"

        out = dumps_for_jsonb({"e": Carrier()}, default=str)
        assert "\\u0000" not in out
        assert json.loads(out) == {"e": "extractedtext"}

    def test_circular_reference_raises_valueerror_not_recursionerror(self):
        # RecursionError subclasses RuntimeError, which every downstream
        # `except (TypeError, ValueError)` degradation seam would miss — turning
        # a bad payload back into the caller strand this module prevents.
        cycle: dict = {}
        cycle["self"] = cycle
        with pytest.raises(ValueError):
            dumps_for_jsonb(cycle)

    def test_excessive_nesting_raises_valueerror(self):
        deep: dict = {}
        cur = deep
        for _ in range(1500):
            cur["n"] = {}
            cur = cur["n"]
        with pytest.raises(ValueError):
            dumps_for_jsonb(deep)

    def test_default_hook_coerces_unserialisable(self):
        from uuid import UUID

        uid = UUID("00000000-0000-0000-0000-00000000dead")
        assert json.loads(dumps_for_jsonb({"id": uid}, default=str)) == {"id": str(uid)}

    def test_raises_without_default_for_unserialisable(self):
        with pytest.raises(TypeError):
            dumps_for_jsonb({"o": object()})

    def test_round_trips_a_clean_payload(self):
        value = {"success": True, "data": {"output": {"n": 1}}, "error": None}
        assert json.loads(dumps_for_jsonb(value)) == value
