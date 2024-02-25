from dataclasses import dataclass

from unstract.core.llm_helper.enums import LLMResult


@dataclass
class LLMResponse:
    output: str
    cost_type: str
    result: LLMResult = LLMResult.OK
    cost: float = 0
    time_taken: float = 0
