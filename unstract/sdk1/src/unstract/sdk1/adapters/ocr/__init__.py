from unstract.sdk1.adapters import AdapterDict
from unstract.sdk1.adapters.ocr.register import OCRRegistry

adapters: AdapterDict = {}
OCRRegistry.register_adapters(adapters)
