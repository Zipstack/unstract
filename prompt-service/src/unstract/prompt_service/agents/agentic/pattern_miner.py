"""PatternMinerAgent - Mines extraction hints from schema, summaries, and sample texts."""

from typing import Any, AsyncGenerator, Sequence
from autogen_agentchat.agents import BaseChatAgent
from autogen_agentchat.base import Response
from autogen_agentchat.messages import (
    BaseAgentEvent,
    BaseChatMessage,
    TextMessage,
)
from autogen_core import CancellationToken
from autogen_core.model_context import UnboundedChatCompletionContext
from autogen_core.models import ChatCompletionClient, RequestUsage, UserMessage, AssistantMessage, SystemMessage


class PatternMinerAgent(BaseChatAgent):
    """Agent that mines concise, reusable extraction hints from documents."""

    def __init__(
        self,
        name: str = "PatternMinerAgent",
        model_client: ChatCompletionClient | None = None,
        system_message: str | None = None,
    ):
        description = "Mines field-specific anchors, patterns, and formatting hints from documents"
        super().__init__(name=name, description=description)
        self._model_client = model_client
        self._model_context = UnboundedChatCompletionContext()
        self._system_message = system_message or self._get_default_system_message()

    def _get_default_system_message(self) -> str:
        return """You are a pattern mining expert specializing in document data extraction.

Your task is to analyze document texts and summaries to extract concise, reusable extraction hints that will guide an LLM in extracting structured data.

Analyze the provided:
1. JSON Schema - to understand required fields and their types
2. Document Summaries - to understand field semantics and common patterns
3. Sample Raw Texts - to mine anchors, patterns, and formatting conventions

Output a JSON object with three sections:

1. **field_hints**: For each schema field, provide:
   - "anchors": Array of text markers that appear near this field (e.g., ["Account No", "A/c No", "Account Number"])
   - "pattern": Regex sketch if applicable (e.g., "\\d{10,18}" for account numbers)
   - "synonyms": Alternative names found in documents
   - "location_hints": Where in doc (e.g., "near header", "in table", "top-right corner")

2. **format_hints**: General formatting conventions found:
   - "currency_symbols": Array of currency symbols used (e.g., ["₹", "$", "USD"])
   - "decimal_sep": Decimal separator (e.g., "." or ",")
   - "thousand_sep": Thousand separator
   - "date_formats": Array of date formats (e.g., ["yyyy-MM-dd", "dd-MMM-yyyy"])
   - "units": Common units (e.g., ["kg", "lbs", "meters"])

3. **line_items**: If documents contain line items/tables:
   - "headers": Expected column headers (e.g., ["Date", "Description", "Amount", "Balance"])
   - "order_sensitive": Boolean - whether order matters
   - "typical_rows": Typical number of rows

Example output structure:
```json
{
  "field_hints": {
    "account_number": {
      "anchors": ["Account No", "A/c No", "Account Number"],
      "pattern": "\\\\d{10,18}",
      "synonyms": ["Acct No", "Account #"],
      "location_hints": "near top of document, usually right-aligned"
    },
    "statement_period": {
      "anchors": ["Period", "Statement Period", "Statement Date"],
      "date_formats": ["yyyy-MM-dd", "dd-MMM-yyyy"],
      "location_hints": "near header, often below account number"
    }
  },
  "format_hints": {
    "currency_symbols": ["₹", "$"],
    "decimal_sep": ".",
    "thousand_sep": ",",
    "date_formats": ["yyyy-MM-dd", "dd-MMM-yyyy", "MM/dd/yyyy"]
  },
  "line_items": {
    "headers": ["Date", "Description", "Debit", "Credit", "Balance"],
    "order_sensitive": true,
    "typical_rows": 15
  }
}
```

IMPORTANT:
- Output ONLY valid JSON, no additional prose or explanations
- Be concise - focus on high-signal patterns
- If a field doesn't have clear patterns, omit it from field_hints
- If no line items found, omit the "line_items" section
- Escape backslashes in regex patterns (use \\\\d not \\d)"""

    @property
    def produced_message_types(self) -> Sequence[type[BaseChatMessage]]:
        return (TextMessage,)

    async def on_messages(
        self, messages: Sequence[BaseChatMessage], cancellation_token: CancellationToken
    ) -> Response:
        """Process messages and return pattern mining results."""
        final_response = None
        async for message in self.on_messages_stream(messages, cancellation_token):
            if isinstance(message, Response):
                final_response = message

        if final_response is None:
            raise AssertionError("The stream should have returned the final result.")

        return final_response

    async def on_messages_stream(
        self,
        messages: Sequence[BaseChatMessage],
        cancellation_token: CancellationToken,
    ) -> AsyncGenerator[BaseAgentEvent | BaseChatMessage | Response, None]:
        """Stream processing of messages."""
        # Add messages to the model context
        for msg in messages:
            if hasattr(msg, "content") and isinstance(msg.content, str):
                await self._model_context.add_message(UserMessage(content=msg.content, source=msg.source))

        # Prepare the conversation history
        history = await self._model_context.get_messages()

        # Create the prompt with system message
        llm_messages = [SystemMessage(content=self._system_message)] + list(history)

        # Generate response using LLM with streaming
        if self._model_client is None:
            raise ValueError("Model client is required but not set")

        # Use streaming to avoid Anthropic's 10-minute non-streaming limit
        content_parts = []
        from autogen_core.models import CreateResult

        async for chunk in self._model_client.create_stream(llm_messages, cancellation_token=cancellation_token):
            # Streaming chunks can be strings OR CreateResult objects
            if isinstance(chunk, str):
                content_parts.append(chunk)
            elif isinstance(chunk, CreateResult):
                # Final chunk is a CreateResult object with complete content
                if isinstance(chunk.content, str):
                    content_parts.append(chunk.content)

        response_content = "".join(content_parts)

        if not isinstance(response_content, str):
            raise ValueError("Expected string response from model")

        # Create usage metadata (streaming doesn't provide detailed usage)
        usage = RequestUsage(
            prompt_tokens=0,  # Not available in streaming mode
            completion_tokens=0,
        )

        # Add response to model context
        await self._model_context.add_message(AssistantMessage(content=response_content, source=self.name))

        # Yield the final response
        yield Response(
            chat_message=TextMessage(content=response_content, source=self.name, models_usage=usage),
            inner_messages=[],
        )

    async def on_reset(self, cancellation_token: CancellationToken) -> None:
        """Reset the agent by clearing the model context."""
        await self._model_context.clear()
