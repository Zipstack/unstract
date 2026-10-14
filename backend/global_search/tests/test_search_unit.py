"""DB-free tests: parameters, envelope shape, registry and in-memory ranking.

Providers are faked so the envelope is exercised without the ORM.
"""

import json
from pathlib import Path
from unittest.mock import patch

import jsonschema
import pytest
from account_v2.models import User

from global_search.constants import MatchTier
from global_search.providers import SearchHit, SearchProvider
from global_search.ranking import match_tier, rank_items
from global_search.registry import get_providers, register_provider, unregister_provider
from global_search.tests.base import search

SCHEMA = json.loads(
    (Path(__file__).parents[1] / "contract" / "search-response.schema.json").read_text()
)


class FakeProvider(SearchProvider):
    def __init__(self, type_key: str, order: int, names: list[str]):
        self.type_key = type_key
        self.label = type_key.title()
        self.order = order
        self.names = names

    def search(self, user, query, limit):
        ranked = rank_items(self.names, query, names=lambda n: [n], sort_key=lambda n: n)
        return [
            SearchHit(id=name, name=name, match=tier, context=None, route_params={"id": name})
            for name, tier in ranked[: limit + 1]
        ]


@pytest.fixture
def user() -> User:
    # Unsaved: IsAuthenticated only reads ``is_authenticated``.
    return User(username="u@example.com", email="u@example.com")


@pytest.fixture
def providers():
    fakes = [
        FakeProvider("beta", 20, ["alpha one", "alpha two", "one alpha"]),
        FakeProvider("alpha", 10, ["alpha"]),
        FakeProvider("empty", 30, ["nothing"]),
    ]
    with patch("global_search.views.get_providers", return_value=sorted(fakes, key=lambda p: p.order)):
        yield fakes


def test_groups_in_rail_order_with_empty_groups_omitted(user, providers):
    data = search(user, q="alpha").data
    jsonschema.validate(data, SCHEMA)
    assert data["query"] == "alpha"
    assert [g["type"] for g in data["groups"]] == ["alpha", "beta"]
    beta = data["groups"][1]
    assert [r["name"] for r in beta["results"]] == ["alpha one", "alpha two", "one alpha"]
    assert [r["match"] for r in beta["results"]] == ["name_prefix", "name_prefix", "name"]
    assert beta["results"][0]["route"] == {"key": "beta.detail", "params": {"id": "alpha one"}}


def test_a_failing_provider_drops_only_its_own_group(user, providers, caplog):
    class Broken(FakeProvider):
        def search(self, user, query, limit):
            raise RuntimeError("boom")

    with patch(
        "global_search.views.get_providers",
        return_value=[providers[1], Broken("broken", 15, []), providers[0]],
    ):
        response = search(user, q="alpha")
    assert response.status_code == 200
    assert [g["type"] for g in response.data["groups"]] == ["alpha", "beta"]
    assert "Global search provider 'broken' failed" in caplog.text


def test_limit_and_has_more(user, providers):
    beta = search(user, q="alpha", types="beta", limit=2).data["groups"][0]
    assert len(beta["results"]) == 2
    assert beta["has_more"] is True
    assert search(user, q="alpha", types="beta", limit=3).data["groups"][0]["has_more"] is False


def test_types_filter_ignores_unknown_keys(user, providers):
    data = search(user, q="alpha", types=" alpha , agentic_project,,").data
    assert [g["type"] for g in data["groups"]] == ["alpha"]


@pytest.mark.parametrize("q", ["", "a", "  a  ", "   "])
def test_short_query_returns_no_groups(user, providers, q):
    response = search(user, q=q)
    assert response.status_code == 200
    assert response.data == {"query": q.strip(), "groups": []}


def test_missing_query_returns_no_groups(user, providers):
    response = search(user)
    assert response.status_code == 200
    assert response.data["groups"] == []


@pytest.mark.parametrize(
    "params",
    [{"limit": 0}, {"limit": 21}, {"limit": "x"}, {"q": "a" * 101}],
)
def test_invalid_parameters_are_400(user, providers, params):
    response = search(user, **{"q": "alpha", **params})
    assert response.status_code == 400


def test_query_at_max_length_is_accepted(user, providers):
    assert search(user, q="a" * 100).status_code == 200


def test_anonymous_is_rejected():
    from django.contrib.auth.models import AnonymousUser

    assert search(AnonymousUser(), q="alpha").status_code in (401, 403)


class TestRegistry:
    def test_sorted_by_order_and_duplicate_class_is_idempotent(self):
        first, second = FakeProvider("zz_b", 999_002, []), FakeProvider("zz_a", 999_001, [])
        try:
            register_provider(first)
            register_provider(second)
            register_provider(FakeProvider("zz_a", 999_001, []))
            keys = [p.type_key for p in get_providers()]
            assert keys[-2:] == ["zz_a", "zz_b"]
        finally:
            unregister_provider("zz_a")
            unregister_provider("zz_b")

    @pytest.mark.parametrize("bad_key", ["agenticProject", "1abc", "a-b", "", "a.b"])
    def test_type_key_must_match_the_schema_pattern(self, bad_key):
        with pytest.raises(ValueError):
            register_provider(FakeProvider(bad_key, 1, []))
        assert bad_key not in [p.type_key for p in get_providers()]

    def test_conflicting_class_for_a_key_raises(self):
        class Other(FakeProvider):
            pass

        register_provider(FakeProvider("zz_c", 999_003, []))
        try:
            with pytest.raises(ValueError):
                register_provider(Other("zz_c", 1, []))
        finally:
            unregister_provider("zz_c")


@pytest.mark.parametrize(
    ("names", "description", "expected"),
    [
        (["Invoice parser"], None, MatchTier.NAME_PREFIX),
        (["My invoices"], None, MatchTier.NAME),
        (["other", "INVOICE api"], None, MatchTier.NAME_PREFIX),
        (["x"], "invoice first", MatchTier.DESCRIPTION_PREFIX),
        (["x"], "about Invoices", MatchTier.DESCRIPTION),
        (["x", None], None, None),
    ],
)
def test_match_tier(names, description, expected):
    assert match_tier("invoice", names, description) == expected


def test_rank_items_orders_by_tier_then_sort_key():
    items = [("b", "zz invoice"), ("a", "invoice"), ("c", "invoice")]
    ranked = rank_items(items, "inv", names=lambda i: [i[1]], sort_key=lambda i: i[0])
    assert [i[0] for i, _ in ranked] == ["a", "c", "b"]
