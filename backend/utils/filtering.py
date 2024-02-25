from rest_framework.request import Request


class FilterHelper:
    @staticmethod
    def build_filter_args(request: Request, *params: str) -> dict[str, str]:
        """Builds a dict of filter to pass to the QueryManager from the
        request.

        Args:
            request (Request): Request to obtain query from

        Returns:
            dict[str, str]: Filter dict to pass to request
        """
        filter_args: dict[str, str] = {}
        for queryParam in params:
            paramValue = request.query_params.get(queryParam)
            if paramValue is not None:
                filter_args[queryParam] = paramValue
        return filter_args
