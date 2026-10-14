"""DB-free tests: parameters, envelope shape, failure handling, registry and
in-memory ranking, with faked providers.
"""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import jsonschema
import pytest
from account_v2.models import User
from utils.user_context import UserContext
from django.db import OperationalError

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


@pytest.fixture(autouse=True)
def no_organization_context():
    """A 5xx makes Django's error reporter import the URLconf. If an earlier
    test on the same worker left an organisation in UserContext, the
    org-scoped managers behind class-level querysets (e.g.
    ``pipeline_v2.views``) would look it up during that import -- a DB query
    these tests must not make.
    """
    previous = UserContext.get_organization_identifier()
    UserContext.set_organization_identifier(None)
    yield
    UserContext.set_organization_identifier(previous)


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
        response = search(user, allow_failures=True, q="alpha")
    assert response.status_code == 200
    assert [g["type"] for g in response.data["groups"]] == ["alpha", "beta"]
    assert response.data["failed_types"] == ["broken"]
    jsonschema.validate(response.data, SCHEMA)
    assert "Global search provider 'broken' failed" in caplog.text


def _assert_error(response, status: int, code: str) -> None:
    assert response.status_code == status
    assert [e["code"] for e in response.data["errors"]] == [code]


class _Broken(FakeProvider):
    def search(self, user, query, limit):
        raise RuntimeError("boom")


class _DbError(FakeProvider):
    def search(self, user, query, limit):
        raise OperationalError("canceling statement due to statement timeout")


def _connection(*, usable: bool = True, needs_rollback: bool = False) -> MagicMock:
    """The view's DB connection, in autocommit (the default) with a chosen
    health, so the escalation rules run without a real failure."""
    conn = MagicMock(in_atomic_block=False, needs_rollback=needs_rollback)
    conn.is_usable.return_value = usable
    return conn


def _run(user, providers_list, conn=None, **params):
    with (
        patch("global_search.views.connection", conn or _connection()),
        patch("global_search.views.get_providers", return_value=providers_list),
    ):
        return search(user, allow_failures=True, **{"q": "alpha", **params})


def test_every_type_failing_with_a_bug_is_a_500(user):
    response = _run(user, [_Broken("a", 1, []), _Broken("b", 2, [])])
    _assert_error(response, 500, "search_failed")


def test_every_type_failing_on_the_database_is_a_retryable_503(user):
    response = _run(user, [_DbError("a", 1, []), _DbError("b", 2, [])])
    _assert_error(response, 503, "search_unavailable")


def test_a_failure_that_breaks_the_transaction_fails_the_request(user, providers):
    # A failed savepoint rollback leaves needs_rollback set; later types
    # would all fail, so the error must surface rather than be logged per type.
    conn = _connection(needs_rollback=True)
    response = _run(user, [_Broken("a", 1, []), providers[0]], conn)
    _assert_error(response, 503, "search_unavailable")


def test_a_lost_connection_fails_the_request_even_if_others_answered(
    user, providers, caplog
):
    # In autocommit nothing marks the connection broken; is_usable() does.
    conn = _connection(usable=False)
    response = _run(user, [providers[1], _DbError("lost", 15, [])], conn)
    _assert_error(response, 503, "search_unavailable")
    # The 503 itself names no type; the log must.
    assert "Global search provider 'lost' failed" in caplog.text


def test_a_failed_connect_fails_the_request_without_probing_it(user, providers):
    # Connecting failed, so no connection is open: every later type would
    # dial the dead database too. is_usable() needs an open connection.
    conn = _connection()
    conn.connection = None
    response = _run(user, [_DbError("down", 5, []), providers[1]], conn)
    _assert_error(response, 503, "search_unavailable")
    conn.is_usable.assert_not_called()


def test_a_bug_alongside_database_errors_is_a_500(user):
    # Only an all-retryable failure is worth retrying.
    response = _run(user, [_DbError("a", 1, []), _Broken("b", 2, [])])
    _assert_error(response, 500, "search_failed")


def test_a_db_error_on_a_healthy_connection_drops_only_its_type(user, providers):
    # A statement timeout, lock timeout or deadlock leaves the connection
    # usable: the other types still answer.
    response = _run(user, [providers[1], _DbError("slow", 15, [])])
    assert response.status_code == 200
    assert [g["type"] for g in response.data["groups"]] == ["alpha"]
    assert response.data["failed_types"] == ["slow"]


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
    assert response.data == {"query": q.strip(), "groups": [], "failed_types": []}


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


def test_a_hit_must_carry_a_route_id():
    with pytest.raises(ValueError):
        SearchHit(id="x", name="x", match=MatchTier.NAME, route_params={})
