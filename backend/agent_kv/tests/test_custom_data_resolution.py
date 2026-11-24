"""`{{custom_data.*}}` substitution, which runs at submit rather than in the engine.

Pure functions over strings and dicts: no Django, no DB, no serializer. The
serializer-level and view-level behaviour is covered in
`test_submit_view.py`; what is pinned here is the substitution dialect itself,
because it has to stay identical to the workflow executor's
(`workers/executor/executors/variable_replacement.py`) or a caller has to learn
two of them.
"""

import pytest

from agent_kv.custom_data import MissingCustomDataKey, referenced_paths, resolve


class TestReferencedPaths:
    def test_finds_each_path_once_in_order(self):
        text = "{{custom_data.b}} then {{custom_data.a}} then {{custom_data.b}}"
        assert referenced_paths(text) == ["b", "a"]

    def test_dotted_paths_are_one_path(self):
        assert referenced_paths("{{custom_data.a.b.c}}") == ["a.b.c"]

    @pytest.mark.parametrize("text", ["", "no placeholders here", "{{other.thing}}"])
    def test_nothing_to_find(self, text):
        assert referenced_paths(text) == []

    def test_whitespace_inside_the_braces_is_tolerated(self):
        assert referenced_paths("{{ custom_data.a }}") == ["a"]


class TestResolve:
    def test_substitutes_a_flat_key(self):
        assert resolve("Vendor: {{custom_data.vendor}}", {"vendor": "Acme"}) == (
            "Vendor: Acme"
        )

    def test_substitutes_a_nested_path(self):
        data = {"buyer": {"address": {"city": "Chennai"}}}
        assert resolve("{{custom_data.buyer.address.city}}", data) == "Chennai"

    def test_substitutes_every_occurrence(self):
        out = resolve("{{custom_data.a}}/{{custom_data.a}}", {"a": "x"})
        assert out == "x/x"

    def test_leaves_unrelated_braces_alone(self):
        # A `keys` description legitimately contains JSON-ish prose.
        text = 'shaped like {"total": 1} and {{not_custom_data.x}}'
        assert resolve(text, {"x": "no"}) == text

    @pytest.mark.parametrize(
        ("value", "expected"),
        [
            (42, "42"),
            (1.5, "1.5"),
            # Lowercase, matching the JSON the caller wrote rather than
            # Python's `str(True)`.
            (True, "true"),
            (False, "false"),
            # An absent optional value reads as absent, not as the word "None".
            (None, ""),
        ],
    )
    def test_non_string_values_are_stringified_for_prompt_text(self, value, expected):
        assert resolve("[{{custom_data.v}}]", {"v": value}) == f"[{expected}]"

    def test_a_dict_value_is_stringified_rather_than_refused(self):
        # Pointing a placeholder at a subtree is odd but unambiguous, and
        # refusing it would be a second rule for a caller to learn.
        assert resolve("{{custom_data.a}}", {"a": {"b": 1}}) == "{'b': 1}"

    @pytest.mark.parametrize("text", ["", None])
    def test_empty_text_is_returned_unchanged(self, text):
        assert resolve(text, {"a": 1}) == text


class TestMissingKeys:
    def test_missing_flat_key_names_the_path_and_the_fix(self):
        with pytest.raises(MissingCustomDataKey) as e:
            resolve("{{custom_data.vendor}}", {"other": 1})
        assert e.value.path == "vendor"
        assert "{{custom_data.vendor}}" in str(e.value)
        assert "'custom_data' object of your request" in str(e.value)

    def test_missing_leaf_of_a_present_subtree(self):
        with pytest.raises(MissingCustomDataKey) as e:
            resolve("{{custom_data.a.b}}", {"a": {"c": 1}})
        assert e.value.path == "a.b"
        assert "key not found" in e.value.reason

    def test_descending_through_a_scalar_is_a_missing_key_not_a_500(self):
        # `{"a": 1}` with `{{custom_data.a.b}}`: `1["b"]` is a TypeError, and an
        # uncaught one here would be a 500 on input the caller controls.
        with pytest.raises(MissingCustomDataKey) as e:
            resolve("{{custom_data.a.b}}", {"a": 1})
        assert e.value.path == "a.b"

    @pytest.mark.parametrize("data", [None, {}])
    def test_no_custom_data_at_all_says_so_rather_than_blaming_the_key(self, data):
        # Two different mistakes with two different fixes: send the object, or
        # add a key to the object you already send.
        with pytest.raises(MissingCustomDataKey) as e:
            resolve("{{custom_data.vendor}}", data)
        assert "no custom_data was sent" in e.value.reason

    def test_the_first_missing_path_is_the_one_reported(self):
        # Deterministic, so the 400 does not change between identical requests.
        with pytest.raises(MissingCustomDataKey) as e:
            resolve("{{custom_data.a}} {{custom_data.b}}", {})
        assert e.value.path == "a"
