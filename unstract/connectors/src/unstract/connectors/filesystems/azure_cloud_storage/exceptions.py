import azure.core.exceptions as AzureException

from unstract.connectors.exceptions import AzureHttpError, ConnectorError


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
        return ConnectorError(error_message)
    elif isinstance(e, AzureException.ServiceRequestError):
        client_error = e.message if hasattr(e, "message") else str(e)
        error_message += (
            f"Failed to connect to Azure service. \n" f"Error: \n```\n{client_error}\n```"
        )
        return ConnectorError(error_message)
    elif isinstance(e, AzureException.HttpResponseError):
        client_error = e.message if hasattr(e, "message") else str(e)
        error_message += (
            f"Azure service returned an error response. \n"
            f"Error: \n```\n{client_error}\n```"
        )
        return AzureHttpError(error_message)
    else:
        error_message += (
            f"Unexpected error from Azure Cloud Storage. \n"
            f"Error: \n```\n{str(e)}\n```"
        )
        return ConnectorError(error_message)
