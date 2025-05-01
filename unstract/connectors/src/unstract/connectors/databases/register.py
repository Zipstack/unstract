import importlib
from typing import Dict, Any, Optional, List

from unstract.connectors.databases.allowed_modules import ALLOWED_MODULES


def get_database_connector(database_type: str) -> Optional[Any]:
    """
    Get a database connector based on the database type.
    
    Args:
        database_type: The type of database to connect to.
        
    Returns:
        A database connector instance or None if the database type is not supported.
    """
    if database_type not in ALLOWED_MODULES:
        raise ValueError(f"Unsupported database type: {database_type}")
    
    module_path = ALLOWED_MODULES[database_type]
    try:
        module = importlib.import_module(module_path)
        return module.get_connector()
    except (ImportError, AttributeError) as e:
        # Log the error
        print(f"Error loading database connector for {database_type}: {e}")
        return None


def list_supported_databases() -> List[str]:
    """
    List all supported database types.
    
    Returns:
        A list of supported database types.
    """
    return list(ALLOWED_MODULES.keys())
