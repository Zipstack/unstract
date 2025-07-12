import logging
from typing import Any

from singleton_decorator import singleton

from unstract.sdk1.adapters import AdapterDict
from unstract.sdk1.adapters.base import Adapter
from unstract.sdk1.adapters.constants import Common
from unstract.sdk1.adapters.embedding import adapters as embedding_adapters
from unstract.sdk1.adapters.llm import adapters as llm_adapters
from unstract.sdk1.adapters.ocr import adapters as ocr_adapters
from unstract.sdk1.adapters.vectordb import adapters as vectordb_adapters
from unstract.sdk1.adapters.x2text import adapters as x2text_adapters

logger = logging.getLogger(__name__)


# Declaring this class as a Singleton to avoid initialising
# adapters list everytime
@singleton
class Adapterkit:
    def __init__(self) -> None:
        self._adapters: AdapterDict = (
            embedding_adapters
            | llm_adapters
            | vectordb_adapters
            | x2text_adapters
            | ocr_adapters
        )

    @property
    def adapters(self) -> AdapterDict:
        return self._adapters

    def get_adapter_class_by_adapter_id(self, adapter_id: str) -> Adapter:
        if adapter_id in self._adapters:
            adapter_class: Adapter = self._adapters[adapter_id][Common.METADATA][
                Common.ADAPTER
            ]
            return adapter_class
        else:
            raise RuntimeError(f"Couldn't obtain adapter for {adapter_id}")

    def get_adapter_by_id(self, adapter_id: str, *args: Any, **kwargs: Any) -> Adapter:
        """Instantiates and returns a adapter.

        Args:
            adapter_id (str): Identifies adapter to create

        Raises:
            RuntimeError: If the ID is invalid/adapter is missing

        Returns:
            Adapter: Concrete impl of the `Adapter` base
        """
        adapter_class: Adapter = self.get_adapter_class_by_adapter_id(adapter_id)
        return adapter_class(*args, **kwargs)

    def get_adapters_list(self) -> list[dict[str, Any]]:
        adapters = []
        for adapter_id, adapter_registry_metadata in self._adapters.items():
            m: Adapter = adapter_registry_metadata[Common.METADATA][Common.ADAPTER]
            _id = m.get_id()
            name = m.get_name()
            adapter_type = m.get_adapter_type().name
            json_schema = m.get_json_schema()
            desc = m.get_description()
            icon = m.get_icon()
            adapters.append(
                {
                    "id": _id,
                    "name": name,
                    "class_name": m.__name__,
                    "description": desc,
                    "icon": icon,
                    "adapter_type": adapter_type,
                    "json_schema": json_schema,
                }
            )
        return adapters
