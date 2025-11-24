"""CriticDryRunnerAgent - Tests draft prompts and suggests revisions."""

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


class CriticDryRunnerAgent(BaseChatAgent):
    """Agent that tests draft prompts and suggests minimal, high-impact revisions."""

    def __init__(
        self,
        name: str = "CriticDryRunnerAgent",
        model_client: ChatCompletionClient | None = None,
        system_message: str | None = None,
    ):
        description = "Tests draft prompts against sample documents and suggests revisions"
        super().__init__(name=name, description=description)
        self._model_client = model_client
        self._model_context = UnboundedChatCompletionContext()
        self._system_message = system_message or self._get_default_system_message()

    def _get_default_system_message(self) -> str:
        return """You are a prompt quality critic specializing in data extraction prompts.

Your task is to test a draft extraction prompt against a sample document and identify issues that need to be fixed.

You will be provided with:
1. Draft Prompt - the extraction prompt to test
2. JSON Schema - the expected output structure
3. Sample Document Text - a short representative document

**Your Testing Process:**

1. **Simulate Extraction:**
   - Mentally simulate using the draft prompt on the sample document
   - Identify what the LLM would likely extract
   - Check if the extraction would produce valid JSON
   - Verify the output shape matches the schema

2. **Check for Issues:**
   - **JSON Validity**: Would the output parse as valid JSON?
   - **Schema Conformance**: Do all fields match the schema structure?
   - **Null Policy**: Are missing fields set to `null` as required?
   - **Array Order**: Are arrays in document order?
   - **Clarity**: Are field instructions clear and unambiguous?
   - **Completeness**: Are all schema fields covered?
   - **Precision**: Are there overly broad regex or vague instructions?

3. **Suggest Minimal Revisions:**
   - Focus on HIGH-IMPACT issues that would cause failures
   - Be surgical - suggest specific additions/changes, not rewrites
   - Limit to 3-5 revisions maximum
   - Prioritize: JSON validity > Schema conformance > Clarity > Optimization

Output a JSON object with this structure:

```json
{
  "test_passed": false,
  "issues_found": [
    {
      "severity": "high",
      "category": "schema_conformance",
      "description": "Field 'statement_period' is an object with 'start' and 'end', but guidance doesn't specify this nesting"
    },
    {
      "severity": "medium",
      "category": "clarity",
      "description": "Date format ambiguous - should explicitly state 'yyyy-MM-dd' for 'statement_period.start'"
    }
  ],
  "revisions": [
    {
      "location": "Per-Field Guidance section, 'statement_period' field",
      "current": "statement_period: Date found near 'Period'",
      "revised": "statement_period.start / statement_period.end: Dates found near 'Period' or 'Statement Period'. Extract as ISO format yyyy-MM-dd. Set to null if not found.",
      "rationale": "Clarifies nesting, format, and null handling"
    },
    {
      "location": "Formatting Rules section, rule 3",
      "current": "Use null for missing or unavailable fields",
      "revised": "Use null for missing or unavailable fields. Do NOT use empty strings or omit fields.",
      "rationale": "Prevents common mistake of using empty strings instead of null"
    }
  ],
  "final_prompt_text": "<The complete revised prompt with all changes applied>",
  "confidence": "high"
}
```

**Important Guidelines:**

1. If the prompt would work correctly on the sample (produces valid JSON matching schema), set `test_passed: true` and minimize revisions
2. Focus on PREVENTING common LLM mistakes:
   - Outputting prose instead of pure JSON
   - Using empty strings instead of null
   - Wrong nesting level for fields
   - Inconsistent date/number formats
   - Inferring values not present in document
3. Don't over-optimize - save field-targeted tuning for later
4. Be specific in revisions - show exact before/after text
5. Always include `final_prompt_text` with all revisions applied

Output ONLY valid JSON, no additional prose or commentary."""

    @property
    def produced_message_types(self) -> Sequence[type[BaseChatMessage]]:
        return (TextMessage,)

    async def on_messages(
        self, messages: Sequence[BaseChatMessage], cancellation_token: CancellationToken
    ) -> Response:
        """Process messages and return critique with revisions."""
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
