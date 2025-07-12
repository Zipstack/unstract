import logging
import os
from importlib import import_module
from typing import Any

from unstract.sdk.adapters.constants import Common
from unstract.sdk.adapters.registry import AdapterRegistry
from unstract.sdk.adapters.vectordb.vectordb_adapter import VectorDBAdapter

logger = logging.getLogger(__name__)


class VectorDBRegistry(AdapterRegistry):
    @staticmethod
    def register_adapters(adapters: dict[str, Any]) -> None:
        current_directory = os.path.dirname(os.path.abspath(__file__))
        package = "unstract.sdk.adapters.vectordb"

        for adapter in os.listdir(current_directory):
            adapter_path = os.path.join(current_directory, adapter, Common.SRC_FOLDER)
            # Check if the item is a directory and not a
            # special directory like __pycache__
            if os.path.isdir(adapter_path) and not adapter.startswith("__"):
                VectorDBRegistry._build_adapter_list(adapter, package, adapters)
        if len(adapters) == 0:
            logger.warning("No vectorDB adapter found.")

    @staticmethod
    def _build_adapter_list(
        adapter: str, package: str, adapters: dict[str, Any]
    ) -> None:
        try:
            full_module_path = f"{package}.{adapter}.{Common.SRC_FOLDER}"
            module = import_module(full_module_path)
            metadata = getattr(module, Common.METADATA, {})
            if metadata.get("is_active", False):
                adapter_class: VectorDBAdapter = metadata[Common.ADAPTER]
                adapter_id = adapter_class.get_id()
                if not adapter_id or (adapter_id in adapters):
                    logger.warning(f"Duplicate Id : {adapter_id}")
                else:
                    adapters[adapter_id] = {
                        Common.MODULE: module,
                        Common.METADATA: metadata,
                    }
        except ModuleNotFoundError as exception:
            logger.warning(f"Unable to import vectorDB adapters : {exception}")
