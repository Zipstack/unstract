from unstract.sdk1.adapters import AdapterDict
from unstract.sdk1.adapters.vectordb.register import VectorDBRegistry

adapters: AdapterDict = {}
VectorDBRegistry.register_adapters(adapters)
