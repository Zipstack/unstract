import logging
from functools import wraps
from typing import Any

from api_v2.exceptions import Forbidden
from rest_framework.request import Request

logger = logging.getLogger(__name__)


class BaseAPIKeyValidator:
    @classmethod
    def validate_api_key(cls, func: Any) -> Any:
        """Decorator that validates the API key.

        Sample header:
            Authorization: Bearer 123e4567-e89b-12d3-a456-426614174001
        Args:
            func (Any): Function to wrap for validation
        """

        @wraps(func)
        def wrapper(self: Any, request: Request, *args: Any, **kwargs: Any) -> Any:
            """Wrapper to validate the inputs and key.

            Args:
                request (Request): Request context

            Raises:
                Forbidden: _description_
                APINotFound: _description_

            Returns:
                Any: _description_
            """
            authorization_header = request.headers.get("Authorization")
            api_key = None
            if authorization_header and authorization_header.startswith("Bearer "):
                api_key = authorization_header.split(" ")[1]
            if not api_key:
                raise Forbidden("Missing api key")
            cls.validate_parameters(request, **kwargs)
            return cls.validate_and_process(
                self, request, func, *args, **kwargs, api_key=api_key
            )

        return wrapper

    @staticmethod
    def validate_parameters(request: Request, **kwargs: Any) -> None:
        """Validate specific parameters required by subclasses."""
        pass

    @staticmethod
    def validate_and_process(
        self: Any, request: Request, func: Any, api_key: str, *args: Any, **kwargs: Any
    ) -> Any:
        """Process and validate API key with specific logic required by
        subclasses."""
        pass
