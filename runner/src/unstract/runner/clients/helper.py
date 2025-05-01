import importlib
import logging
from typing import Any, Dict, List, Optional, Tuple, Union

from unstract.runner.clients.base import BaseClient
from unstract.runner.clients.exceptions import ClientError

logger = logging.getLogger(__name__)

# Define a whitelist of allowed modules to import
ALLOWED_CLIENT_MODULES = {
    "unstract.runner.clients.local",
    "unstract.runner.clients.remote",
    # Add other legitimate modules here as needed
}

def get_client(client_type: str, **kwargs) -> BaseClient:
    """
    Get a client of the specified type.

    Args:
        client_type: The type of client to get.
        **kwargs: Additional arguments to pass to the client constructor.

    Returns:
        A client of the specified type.

    Raises:
        ClientError: If the client type is not supported.
    """
    try:
        # Construct the full module path
        module_path = f"unstract.runner.clients.{client_type}"
        
        # Check if the module is in the whitelist
        if module_path not in ALLOWED_CLIENT_MODULES:
            raise ClientError(f"Client type '{client_type}' is not allowed")
            
        # Import the module
        module = importlib.import_module(module_path)
        
        # Get the client class
        client_class = getattr(module, f"{client_type.capitalize()}Client")
        
        # Create and return the client
        return client_class(**kwargs)
    except (ImportError, AttributeError) as e:
        logger.error(f"Failed to import client: {e}")
        raise ClientError(f"Client type '{client_type}' is not supported") from e
