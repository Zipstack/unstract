from __future__ import annotations

from typing import Any

import litellm
from pydantic import ValidationError

from unstract.sdk1.adapters.constants import Common
from unstract.sdk1.adapters.embedding1 import adapters
from unstract.sdk1.exceptions import SdkError
from unstract.sdk1.platform import PlatformHelper
from unstract.sdk1.tool.base import BaseTool


class Embedding:
    """Unified embedding interface powered by LiteLLM.
    Internally invokes Unstract embedding adapters.
    """

    _TEST_SNIPPET = "Hello, I am Unstract"

    def __init__(
        self,
        adapter_id: str,
        adapter_metadata: dict[str, Any],
        adapter_instance_id: str = "",
        tool: BaseTool = None,
        kwargs: dict[str, Any] = {},
    ) -> None:
        embedding_config = None

        try:
            if adapter_instance_id:
                if not tool:
                    raise SdkError("Broken LLM adapter tool binding: " + adapter_instance_id)

                embedding_config = PlatformHelper.get_adapter_config(tool, adapter_instance_id)

                self._adapter_id = embedding_config[Common.ADAPTER_ID]
            else:
                self._adapter_id = adapter_id

            if embedding_config:
                self._adapter_metadata = embedding_config[Common.ADAPTER_METADATA]
            elif adapter_metadata:
                self._adapter_metadata = adapter_metadata
            else:
                self._adapter_metadata = adapters[self._adapter_id][Common.METADATA]

            self.adapter = adapters[self._adapter_id][Common.MODULE]
        except KeyError:
            raise SdkError("Embedding adapter not supported: " + self._adapter_id)

        self.kwargs: dict[str, Any] = kwargs
        try:
            self.kwargs.update(self.adapter.validate(self._adapter_metadata))
        except ValidationError as e:
            raise SdkError("Invalid embedding adapter metadata: " + str(e))

        self.length = len(self.get_query_embedding(self._TEST_SNIPPET))

    def get_query_embedding(self, query: str) -> list[float]:
        """Return embedding vector for query string."""
        kwargs = self.kwargs.copy()
        model = kwargs.pop("model")
        del kwargs["temperature"]

        resp = litellm.embedding(model=model, input=[query], **kwargs)

        return resp["data"][0]["embedding"]

    def test_connection(self) -> bool:
        """Test connection to the embedding provider."""
        return self.length > 0

