from unstract.sdk.adapters import AdapterDict
from unstract.sdk.adapters.embedding.register import EmbeddingRegistry

adapters: AdapterDict = {}
EmbeddingRegistry.register_adapters(adapters)
