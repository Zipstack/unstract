from __future__ import annotations

from typing import Any

import litellm
from pydantic import ValidationError

from unstract.sdk1.adapters.constants import Common
from unstract.sdk1.adapters.embedding1 import adapters
from unstract.sdk1.exceptions import SdkError


class Embedding:
    """Unified embedding interface powered by LiteLLM.
    Internally invokes Unstract embedding adapters.
    """

    _TEST_SNIPPET = "Hello, I am Unstract"

    def __init__(
        self,
        adapter_id: str,
        adapter_metadata: dict[str, Any],
        kwargs: dict[str, Any] = {},
    ) -> None:
        try:
            self.adapter = adapters[adapter_id][Common.MODULE]
        except KeyError:
            raise SdkError("Embedding adapter not supported: " + adapter_id)

        self._adapter_id = adapter_id
        if adapter_metadata:
            self._adapter_metadata = adapter_metadata
        else:
            self._adapter_metadata = adapters[adapter_id][Common.METADATA]

        self.kwargs: dict[str, Any] = kwargs

        try:
            self.kwargs.update(self.adapter.validate(adapter_metadata))
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
