"""Contract tests for utils.pagination.OptionalPagination.

The four listing endpoints it backs (workflows, prompt studio, adapters,
connectors) are shared with dropdown/selector consumers that expect a bare
array. The opt-in behaviour below is what keeps those consumers regression-free:
no page/page_size param -> paginate_queryset returns None -> DRF serialises the
bare list; only an explicit opt-in gets the {count, next, previous, results}
envelope.

Deliberately DB-free and Django-settings-free (a hand-rolled request stub, no
APIRequestFactory) so it runs in the rig's unit tier.
"""

from __future__ import annotations

from utils.pagination import OptionalPagination

QUERYSET = list(range(1, 101))  # 100 sliceable items stand in for a queryset


class _Req:
    """Minimal stand-in exposing the surface DRF pagination touches."""

    def __init__(self, params: dict[str, str]):
        self.query_params = params

    def build_absolute_uri(self) -> str:
        return "https://testserver/things/"


class TestOptionalPagination:
    def test_no_params_returns_none(self):
        """No opt-in -> None, so callers keep their bare-array response."""
        assert OptionalPagination().paginate_queryset(QUERYSET, _Req({})) is None

    def test_unrelated_params_do_not_trigger_pagination(self):
        req = _Req({"adapter_type": "LLM", "search": "foo"})
        assert OptionalPagination().paginate_queryset(QUERYSET, req) is None

    def test_blank_params_do_not_trigger_pagination(self):
        """Empty ?page= / ?page_size= keep the bare-array response."""
        req = _Req({"page": "", "page_size": ""})
        assert OptionalPagination().paginate_queryset(QUERYSET, req) is None

    def test_page_param_opts_in(self):
        paginator = OptionalPagination()
        page = paginator.paginate_queryset(QUERYSET, _Req({"page": "1"}))
        assert page == list(range(1, 51))  # default page_size == 50
        assert paginator.page.paginator.count == 100

    def test_page_size_param_alone_opts_in(self):
        page = OptionalPagination().paginate_queryset(QUERYSET, _Req({"page_size": "10"}))
        assert page == list(range(1, 11))

    def test_page_size_capped_at_max(self):
        page = OptionalPagination().paginate_queryset(
            QUERYSET, _Req({"page_size": "100000"})
        )
        # max_page_size (1000) caps the request; all 100 rows fit in one page
        assert page == QUERYSET
