import json
import logging
import traceback
from typing import Any, Dict, List, Optional, Union

from django.conf import settings
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import render
from django.template.loader import render_to_string
from rest_framework import status
from rest_framework.response import Response

from backend.utils.constants import INTERNAL_SERVER_ERROR_MESSAGE

logger = logging.getLogger(__name__)


class ExceptionMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        return response

    def process_exception(
        self, request: HttpRequest, exception: Exception
    ) -> Optional[Union[HttpResponse, Response]]:
        """
        Process exceptions raised during request processing.

        Args:
            request: The HTTP request object.
            exception: The exception that was raised.

        Returns:
            An HTTP response object or None.
        """
        logger.error(
            f"Exception occurred: {str(exception)}\n"
            f"Traceback: {traceback.format_exc()}"
        )

        # Handle different types of exceptions
        if isinstance(exception, ValueError):
            return self._handle_value_error(request, exception)
        elif isinstance(exception, KeyError):
            return self._handle_key_error(request, exception)
        elif isinstance(exception, json.JSONDecodeError):
            return self._handle_json_decode_error(request, exception)
        else:
            return self._handle_generic_exception(request, exception)

    def _handle_value_error(
        self, request: HttpRequest, exception: ValueError
    ) -> Union[HttpResponse, Response]:
        """
        Handle ValueError exceptions.

        Args:
            request: The HTTP request object.
            exception: The ValueError exception.

        Returns:
            An HTTP response object.
        """
        error_data = {"error": str(exception)}
        return JsonResponse(error_data, status=status.HTTP_400_BAD_REQUEST)

    def _handle_key_error(
        self, request: HttpRequest, exception: KeyError
    ) -> Union[HttpResponse, Response]:
        """
        Handle KeyError exceptions.

        Args:
            request: The HTTP request object.
            exception: The KeyError exception.

        Returns:
            An HTTP response object.
        """
        error_data = {"error": f"Missing required field: {str(exception)}"}
        return JsonResponse(error_data, status=status.HTTP_400_BAD_REQUEST)

    def _handle_json_decode_error(
        self, request: HttpRequest, exception: json.JSONDecodeError
    ) -> Union[HttpResponse, Response]:
        """
        Handle JSONDecodeError exceptions.

        Args:
            request: The HTTP request object.
            exception: The JSONDecodeError exception.

        Returns:
            An HTTP response object.
        """
        error_data = {"error": "Invalid JSON format"}
        return JsonResponse(error_data, status=status.HTTP_400_BAD_REQUEST)

    def _handle_generic_exception(
        self, request: HttpRequest, exception: Exception
    ) -> Union[HttpResponse, Response]:
        """
        Handle generic exceptions.

        Args:
            request: The HTTP request object.
            exception: The exception that was raised.

        Returns:
            An HTTP response object.
        """
        if settings.DEBUG:
            # In debug mode, return detailed error information
            error_data = {
                "error": str(exception),
                "traceback": traceback.format_exc(),
            }
            return JsonResponse(
                error_data, status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
        else:
            # In production, use a template to render the error page
            context = {"error_message": INTERNAL_SERVER_ERROR_MESSAGE}
            return render(
                request,
                "error.html",
                context,
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
