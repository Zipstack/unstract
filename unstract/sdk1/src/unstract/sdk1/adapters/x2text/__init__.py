from unstract.sdk1.adapters import AdapterDict
from unstract.sdk1.adapters.x2text.register import X2TextRegistry

adapters: AdapterDict = {}
X2TextRegistry.register_adapters(adapters)
