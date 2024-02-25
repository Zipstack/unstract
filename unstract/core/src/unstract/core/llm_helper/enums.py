from enum import Enum


class PromptContext:
    GENERATE_CRON_STRING = "GENERATE_CRON_STRING"


class LLMResult(Enum):
    OK = "OK"
    NOK = "NOK"
