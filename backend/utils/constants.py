class Account:
    CREATED_BY = "created_by"
    MODIFIED_BY = "modified_by"


class Common:
    METADATA = "metadata"
    MODULE = "module"
    CONNECTOR = "connector"


class Pagination:
    """Constants for Pagination.

    Attributes:
        PAGE_SIZE (int): The default number of items per page.
        PAGE_SIZE_QUERY_PARAM (str): The name of the query parameter used to
            specify page size in requests. Ex: ?page=2&<PAGE_SIZE_QUERY_PARAM>=3
        MAX_PAGE_SIZE (int): The maximum allowed number of items per page.
    """

    PAGE_SIZE = 20
    PAGE_SIZE_QUERY_PARAM = "page_size"
    MAX_PAGE_SIZE = 1000
