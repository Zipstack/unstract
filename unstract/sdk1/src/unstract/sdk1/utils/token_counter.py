from typing import Any

from llama_index.core.callbacks.schema import EventPayload
from llama_index.core.llms import ChatResponse, CompletionResponse


class Constants:
    DEFAULT_TOKEN_COUNT = 0


class TokenCounter:
    prompt_llm_token_count: int
    completion_llm_token_count: int
    total_llm_token_count: int = 0
    total_embedding_token_count: int = 0

    def __init__(self, input_tokens, output_tokens):
        self.prompt_llm_token_count = input_tokens
        self.completion_llm_token_count = output_tokens
        self.total_llm_token_count = (
            self.prompt_llm_token_count + self.completion_llm_token_count
        )

    # TODO: Add unit test cases for the following function
    #  for ease of manintenance
    @staticmethod
    def get_llm_token_counts(payload: dict[str, Any]):
        prompt_tokens = Constants.DEFAULT_TOKEN_COUNT
        completion_tokens = Constants.DEFAULT_TOKEN_COUNT
        if EventPayload.PROMPT in payload:
            response = payload.get(EventPayload.COMPLETION)
            (
                prompt_tokens,
                completion_tokens,
            ) = TokenCounter._get_tokens_from_response(response)
        elif EventPayload.MESSAGES in payload:
            response = payload.get(EventPayload.RESPONSE)
            if response:
                (
                    prompt_tokens,
                    completion_tokens,
                ) = TokenCounter._get_tokens_from_response(response)

        token_counter = TokenCounter(
            input_tokens=prompt_tokens,
            output_tokens=completion_tokens,
        )
        return token_counter

    @staticmethod
    def _get_tokens_from_response(
        response: CompletionResponse | ChatResponse | dict,
    ) -> tuple[int, int]:
        """Get the token counts from a raw response."""
        prompt_tokens, completion_tokens = 0, 0
        if isinstance(response, CompletionResponse) or isinstance(response, ChatResponse):
            raw_response = response.raw
            if not isinstance(raw_response, dict):
                raw_response = dict(raw_response)

            usage = raw_response.get("usage", None)
        if usage is None:
            if (
                hasattr(response, "additional_kwargs")
                and "prompt_tokens" in response.additional_kwargs
            ):
                usage = response.additional_kwargs
            elif hasattr(response, "raw"):
                completion_raw = response.raw
                if ("_raw_response" in completion_raw) and hasattr(
                    completion_raw["_raw_response"], "usage_metadata"
                ):
                    usage = completion_raw["_raw_response"].usage_metadata
                    prompt_tokens = usage.prompt_token_count
                    completion_tokens = usage.candidates_token_count
                    return prompt_tokens, completion_tokens
                elif "inputTextTokenCount" in completion_raw:
                    prompt_tokens = completion_raw["inputTextTokenCount"]
                    if "results" in completion_raw:
                        result_list: list = completion_raw["results"]
                        if len(result_list) > 0:
                            result: dict = result_list[0]
                            if "tokenCount" in result:
                                completion_tokens = result.get("tokenCount", 0)
                    return prompt_tokens, completion_tokens
                else:
                    usage = response.raw
            else:
                usage = response

        if not isinstance(usage, dict):
            usage = usage.model_dump()

        possible_input_keys = (
            "prompt_tokens",
            "input_tokens",
            "prompt_eval_count",
            "inputTokens",
        )
        possible_output_keys = (
            "completion_tokens",
            "output_tokens",
            "eval_count",
            "outputTokens",
        )

        prompt_tokens = 0
        for input_key in possible_input_keys:
            if input_key in usage:
                prompt_tokens = int(usage[input_key])
                break

        completion_tokens = 0
        for output_key in possible_output_keys:
            if output_key in usage:
                completion_tokens = int(usage[output_key])
                break

        return prompt_tokens, completion_tokens
