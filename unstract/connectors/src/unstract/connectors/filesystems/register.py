import logging
import os
from importlib import import_module
from typing import Any

from unstract.connectors.constants import Common
from unstract.connectors.filesystems.unstract_file_system import UnstractFileSystem

logger = logging.getLogger(__name__)


def register_connectors(connectors: dict[str, Any]) -> None:
    current_directory = os.path.dirname(os.path.abspath(__file__))
    package = "unstract.connectors.filesystems"

    for connector in os.listdir(current_directory):
        connector_path = os.path.join(current_directory, connector)
        # Check if the item is a directory and not a special directory like __pycache__
        if os.path.isdir(connector_path) and not connector.startswith("__"):
            try:
                full_module_path = f"{package}.{connector}"
                module = import_module(full_module_path)
                metadata = getattr(module, Common.METADATA, {})
                if metadata.get("is_active", False):
                    connector_class: UnstractFileSystem = metadata[Common.CONNECTOR]
                    connector_id = connector_class.get_id()
                    if not connector_id or (connector_id in connectors):
                        logger.warning(f"Duplicate Id : {connector_id}")
                    else:
                        connectors[connector_id] = {
                            Common.MODULE: module,
                            Common.METADATA: metadata,
                        }
            except ModuleNotFoundError as exception:
                logger.error(
                    f"Error while importing connectors ===FS===== {connector} : {exception}",
                    exc_info=True,
                    stack_info=True,
                )

    if len(connectors) == 0:
        logger.warning("No connector found.")
