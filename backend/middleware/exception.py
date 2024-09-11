import json
import logging
import traceback
from typing import Any, Optional

from django.conf import settings
from django.http import HttpRequest, HttpResponse
from drf_standardized_errors.handler import exception_handler
from rest_framework.request import Request
from rest_framework.response import Response

logger = logging.getLogger(__name__)


# Set via settings.REST_FRAMEWORK.EXCEPTION_HANDLER.
def drf_logging_exc_handler(exc: Exception, context: Any) -> Optional[Response]:
    """Custom exception handler for DRF.

    DRF's exception handler takes care of Http404, PermissionDenied and
    APIExceptions by default. This function helps log the traceback for
    all types of exception and then handles it with DRF or Django

    Args:
        exc (Exception): Implementation of Exception raised
        context (dict[str, Any]): Dictionary containing additional
            metadata on the request itself

    Returns:
        Optional[Response]: Returns either a Response if handled, \
            if None it will be
            handled by another method in the middleware
    """
    request = context.get("request")
    response: Optional[Response] = exception_handler(exc=exc, context=context)
    ExceptionLoggingMiddleware.format_exc_and_log(
        request=request, response=response, exception=exc
    )
    return response


class ExceptionLoggingMiddleware:
    """Custom middleware to log unhandled errors.

    DRF middleware handles most exception types, Django takes care of
    handling the rest.
    """

    def __init__(self, get_response: Any) -> None:
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        response = self.get_response(request)
        return response

    def process_exception(
        self, request: HttpRequest, exception: Exception
    ) -> Optional[HttpResponse]:
        """Django hook to handle exceptions by a middleware.

        Args:
            request (HttpRequest): Request that was made
            exception (Exception): Exception that was raised

        Returns:
            Optional[HttpResponse]: Returns either a HttpResponse if handled
                If None it will be handled by another method in the middleware
        """
        # Handle only when running in production, for debug mode
        # Django takes care of displaying a detailed HTML page.
        if not settings.DEBUG and exception:
            logger.error(f"Unhandled exception by DRF for {request}, logging error...")
            ExceptionLoggingMiddleware.format_exc_and_log(
                request=request, exception=exception
            )
            detail = {"detail": "Error processing the request."}
            return HttpResponse(json.dumps(detail), status=500)
        return None

    @staticmethod
    def format_exc_and_log(
        request: Request, exception: Exception, response: Optional[Response] = None
    ) -> None:
        """Format the exception to be logged and logs it.

        Args:
            request (HttpRequest): Request to get API endpoint hit
            exception (Exception): Exception that was raised to be logged
        """
        status_code = 500
        if response:
            status_code = response.status_code
        if status_code >= 500:
            message = "{method} {url} {status}\n\n{error}\n\n````{tb}````".format(
                method=request.method,
                url=request.build_absolute_uri(),
                status=status_code,
                error=repr(exception),
                tb=traceback.format_exc(),
            )
        else:
            message = "{method} {url} {status} {error}".format(
                method=request.method,
                url=request.build_absolute_uri(),
                status=status_code,
                error=repr(exception),
            )
        logger.error(message)
