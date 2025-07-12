from unstract.sdk.adapters import AdapterDict
from unstract.sdk.adapters.vectordb.register import VectorDBRegistry

adapters: AdapterDict = {}
VectorDBRegistry.register_adapters(adapters)
