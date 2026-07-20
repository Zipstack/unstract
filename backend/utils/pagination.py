from rest_framework.pagination import PageNumberPagination

from utils.constants import Pagination


class CustomPagination(PageNumberPagination):
    page_size = Pagination.PAGE_SIZE
    page_size_query_param = Pagination.PAGE_SIZE_QUERY_PARAM
    max_page_size = Pagination.MAX_PAGE_SIZE


class OptionalPagination(CustomPagination):
    """Paginate only when the caller opts in via ?page / ?page_size.

    These list endpoints are shared: besides the listing page they feed
    dropdowns/selectors that expect a bare array. Returning None keeps that
    response untouched for callers that don't ask for a page, while the
    listing page opts in and gets the {count, next, previous, results} envelope.
    """

    def paginate_queryset(self, queryset, request, view=None):
        params = request.query_params
        if (
            self.page_query_param not in params
            and self.page_size_query_param not in params
        ):
            return None
        return super().paginate_queryset(queryset, request, view=view)
