import logging
import os
from importlib import import_module
from typing import Any

from unstract.sdk1.adapters.constants import Common
from unstract.sdk1.adapters.ocr.ocr_adapter import OCRAdapter
from unstract.sdk1.adapters.registry import AdapterRegistry

logger = logging.getLogger(__name__)


class OCRRegistry(AdapterRegistry):
    @staticmethod
    def register_adapters(adapters: dict[str, Any]) -> None:
        current_directory = os.path.dirname(os.path.abspath(__file__))
        package = "unstract.sdk1.adapters.ocr"

        for adapter in os.listdir(current_directory):
            adapter_path = os.path.join(current_directory, adapter, Common.SRC_FOLDER)
            # Check if the item is a directory and not a
            # special directory like __pycache__
            if os.path.isdir(adapter_path) and not adapter.startswith("__"):
                OCRRegistry._build_adapter_list(adapter, package, adapters)
        if len(adapters) == 0:
            logger.warning("No ocr adapter found.")

    @staticmethod
    def _build_adapter_list(adapter: str, package: str, adapters: dict[str, Any]) -> None:
        try:
            full_module_path = f"{package}.{adapter}.{Common.SRC_FOLDER}"
            module = import_module(full_module_path)
            metadata = getattr(module, Common.METADATA, {})
            if metadata.get("is_active", False):
                adapter_class: OCRAdapter = metadata[Common.ADAPTER]
                adapter_id = adapter_class.get_id()
                if not adapter_id or (adapter_id in adapters):
                    logger.warning(f"Duplicate Id : {adapter_id}")
                else:
                    adapters[adapter_id] = {
                        Common.MODULE: module,
                        Common.METADATA: metadata,
                    }
        except ModuleNotFoundError as exception:
            logger.warning(f"Unable to import ocr adapters : {exception}")
