import logging

import azure.core.exceptions as AzureException

from unstract.connectors.exceptions import AzureHttpError, ConnectorError

logger = logging.getLogger(__name__)


def parse_azure_error(e: Exception) -> ConnectorError:
    """Parses the exception from Azure Cloud Storage.

    Helps parse the Azure Cloud Storage error and wraps it with our
    custom exception object to contain a user friendly message.

    Args:
        e (Exception): Error from Azure Cloud Storage

    Returns:
        ConnectorError: Unstract's ConnectorError object
    """
    if isinstance(e, ConnectorError):
        return e

    error_message = "Error from Azure Cloud Storage while testing connection. "

    if isinstance(e, AzureException.ClientAuthenticationError):
        client_error = e.message if hasattr(e, "message") else str(e)
        error_message += (
            f"Authentication failed. Please check your connection credentials. \n"
            f"Error: \n```\n{client_error}\n```"
        )
        logger.error("Azure authentication error: %s", error_message)
        return ConnectorError(error_message, treat_as_user_message=True)
    elif isinstance(e, AzureException.ServiceRequestError):
        client_error = e.message if hasattr(e, "message") else str(e)
        error_message += (
            f"Failed to connect to Azure service. \n" f"Error: \n```\n{client_error}\n```"
        )
        logger.error("Azure service request error: %s", error_message)
        return ConnectorError(error_message, treat_as_user_message=True)
    elif isinstance(e, AzureException.HttpResponseError):
        client_error = e.message if hasattr(e, "message") else str(e)
        error_message += (
            f"Azure service returned an error response. \n"
            f"Error: \n```\n{client_error}\n```"
        )
        logger.error("Azure HTTP response error: %s", error_message)
        return AzureHttpError(error_message, treat_as_user_message=True)
    else:
        error_message += (
            f"Unexpected error from Azure Cloud Storage. \n"
            f"Error: \n```\n{str(e)}\n```"
        )
        logger.error("Unexpected Azure error: %s", error_message)
        return ConnectorError(error_message, treat_as_user_message=True)
