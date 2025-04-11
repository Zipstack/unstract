from rest_framework.pagination import PageNumberPagination

from utils.constants import Pagination


class CustomPagination(PageNumberPagination):
    page_size = Pagination.PAGE_SIZE
    page_size_query_param = Pagination.PAGE_SIZE_QUERY_PARAM
    max_page_size = Pagination.MAX_PAGE_SIZE
