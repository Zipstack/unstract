from enum import Enum


class AdapterTypes(Enum):
    UNKNOWN = "UNKNOWN"
    LLM = "LLM"
    EMBEDDING = "EMBEDDING"
    VECTOR_DB = "VECTOR_DB"
    OCR = "OCR"
    X2TEXT = "X2TEXT"
