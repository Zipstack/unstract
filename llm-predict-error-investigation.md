# Investigation: `'LLM' object has no attribute 'predict'`

## Error Context

```
ERROR: unstract.prompt_service.core.retrievers.keyword_table:
  'LLM' object has no attribute 'predict'

Traceback:
  File "prompt_service/core/retrievers/keyword_table.py", line 48, in retrieve
    keyword_index = KeywordTableIndex(...)
  File "llama_index/core/indices/keyword_table/base.py", line 92, in __init__
    super().__init__(...)
  File "llama_index/core/indices/base.py", line 79, in __init__
    index_struct = self.build_index_from_nodes(...)
  File "llama_index/core/indices/keyword_table/base.py", line 182, in _build_index_from_nodes
    response = self._llm.predict(...)
```

## Root Cause

**Class type mismatch** between Unstract's SDK1 `LLM` and llama-index's `LLM`.

The prompt-service retrievers pass `unstract.sdk1.llm.LLM` (a plain Python class wrapping LiteLLM) to llama-index components that expect `llama_index.core.llms.llm.LLM` (a Pydantic model with `predict()`, `chat()`, `complete()`, etc.).

This is **NOT** a llama-index bug, **NOT** provider-specific, and **NOT** a version issue.

## How We Got Here: SDK Migration

### Old SDK (`unstract-sdk`) - Worked Correctly

```python
# unstract-sdk/src/unstract/sdk/llm.py
from llama_index.core.llms import LLM as LlamaIndexLLM

class LLM:
    def __init__(self, ...):
        self._llm_instance: LlamaIndexLLM = None  # Real llama-index LLM
        self._initialise()

    def _initialise(self):
        self._llm_instance = self._get_llm(self._adapter_instance_id)

    def _get_llm(self, adapter_instance_id) -> LlamaIndexLLM:
        # Returns actual llama-index LLM from adapters via get_llm_instance()
        llm_instance = self._llm_adapter_class.get_llm_instance()
        return llm_instance
```

The old SDK obtained a real `llama_index.core.llms.LLM` instance from adapters. This instance had `predict()`, `chat()`, `complete()` through llama-index's class hierarchy:

```
BaseLLM -> LLM (has predict()) -> CustomLLM/FunctionCallingLLM -> Provider
```

### New SDK1 (`unstract-sdk1`) - Breaks llama-index Integration

```python
# unstract/sdk1/src/unstract/sdk1/llm.py
import litellm

class LLM:  # Plain Python class, NOT llama-index's LLM
    def complete(self, prompt, **kwargs):
        response = litellm.completion(messages=messages, **completion_kwargs)
        return {"response": response_object, ...}

    def stream_complete(self, prompt, **kwargs):
        for chunk in litellm.completion(messages=messages, stream=True, ...):
            yield stream_response

    async def acomplete(self, prompt, **kwargs):
        response = await litellm.acompletion(messages=messages, ...)
        return {"response": response_object}
```

SDK1's `LLM` calls `litellm.completion()` directly. It has **no inheritance** from any llama-index class, and therefore **no** `predict()`, `chat()`, or other llama-index LLM methods.

## Where It Breaks

### keyword_table.py (Confirmed)

```python
# prompt-service/src/unstract/prompt_service/core/retrievers/keyword_table.py:48-52
keyword_index = KeywordTableIndex(
    nodes=[node.node for node in all_nodes],
    show_progress=True,
    llm=self.llm,  # unstract.sdk1.llm.LLM, NOT llama_index.core.llms.llm.LLM
)
```

llama-index's `KeywordTableIndex` stores this as `self._llm` and then calls:

```python
# llama_index/core/indices/keyword_table/base.py:239
response = self._llm.predict(self.keyword_extract_template, text=text)
```

Since `unstract.sdk1.llm.LLM` has no `predict()` method -> **AttributeError**.

### The Two LLM Classes Side-by-Side

| Aspect | `llama_index.core.llms.llm.LLM` | `unstract.sdk1.llm.LLM` |
|--------|----------------------------------|--------------------------|
| Base class | `BaseLLM` (Pydantic model) | Plain Python `object` |
| `predict()` | Yes (line 589 of llm.py) | **No** |
| `chat()` | Yes (abstract, implemented by providers) | **No** |
| `complete()` | Yes (abstract, implemented by providers) | Yes, but different signature (returns dict, not `CompletionResponse`) |
| `stream_complete()` | Yes | Yes, but different signature |
| Used by | llama-index components internally | Unstract prompt-service for direct LLM calls |

## All Affected Retrievers

The base retriever stores the SDK1 LLM:

```python
# prompt-service/src/unstract/prompt_service/core/retrievers/base_retriever.py
from unstract.sdk1.llm import LLM

class BaseRetriever:
    def __init__(self, ..., llm: LLM | None = None):
        self.llm = llm if llm else None
```

All retrievers that pass `self.llm` to llama-index components are affected:

| Retriever | Passes SDK1 LLM to | Status |
|-----------|-------------------|--------|
| `KeywordTableRetriever` | `KeywordTableIndex(llm=self.llm)` | **Confirmed broken** (`'LLM' object has no attribute 'predict'`) |
| `SubquestionRetriever` | `as_query_engine(llm=self.llm)`, `SubQuestionQueryEngine.from_defaults(llm=self.llm)` | **Broken** (unexpected error, needs further investigation) |
| `FusionRetriever` | `QueryFusionRetriever(llm=self.llm)` | **Broken** (unexpected error, needs further investigation) |
| `RouterRetriever` | `LLMSingleSelector.from_defaults(llm=self.llm)`, `RouterQueryEngine.from_defaults(llm=self.llm)`, `as_query_engine(llm=self.llm)` | **Broken** (unexpected error, needs further investigation) |
| `SimpleRetriever` | Does NOT pass LLM to llama-index | **Works fine** |
| `AutomergingRetriever` | - | **Works fine** |
| `RecursiveRetrieval` | - | **Works fine** |

## Online Research: llama-index GitHub Issues

The `predict` method has existed on `llama_index.core.llms.llm.LLM` since v0.10.x. We are on v0.13.2. Related GitHub issues confirm the pattern:

| Issue | Error | Root Cause |
|-------|-------|-----------|
| [#7093](https://github.com/run-llama/llama_index/issues/7093) | `HuggingFaceLLM has no attribute predict` | Wrong parameter name (`llm_predictor=` instead of `llm=`) |
| [#13958](https://github.com/run-llama/llama_index/issues/13958) | `AzureOpenAIMultiModal has no attribute predict` | MultiModal classes don't inherit from `LLM` |
| [#8906](https://github.com/run-llama/llama_index/issues/8906) | `AttributeError in LiteLLM` | Version compatibility issue between litellm and llama-index |

All confirm: the error occurs when a non-`llama_index.core.llms.llm.LLM` object is passed where llama-index expects one.

## Proposed Fix Options

### Option 1: Bridge Adapter (Recommended)

Create a class extending `llama_index.core.llms.CustomLLM` that delegates to SDK1's `LLM.complete()` internally. This makes it compatible with all llama-index components.

```python
from llama_index.core.llms import CustomLLM, CompletionResponse, LLMMetadata

class SDK1LLMBridge(CustomLLM):
    """Bridge between unstract.sdk1.llm.LLM and llama-index's LLM interface."""

    def __init__(self, sdk1_llm):
        super().__init__()
        self._sdk1_llm = sdk1_llm

    @property
    def metadata(self) -> LLMMetadata:
        return LLMMetadata(model_name=self._sdk1_llm.get_model_name())

    def complete(self, prompt, **kwargs) -> CompletionResponse:
        result = self._sdk1_llm.complete(prompt, **kwargs)
        return CompletionResponse(text=result["response"].text)

    def stream_complete(self, prompt, **kwargs):
        for chunk in self._sdk1_llm.stream_complete(prompt, **kwargs):
            yield CompletionResponse(text=chunk.text, delta=chunk.delta)
```

Then in retrievers, wrap before passing to llama-index:

```python
from .llm_bridge import SDK1LLMBridge

llama_llm = SDK1LLMBridge(self.llm)
keyword_index = KeywordTableIndex(nodes=..., llm=llama_llm)
```

### Option 2: Use `llama-index-llms-litellm`

Since SDK1 already has the LiteLLM model name and credentials, construct the official llama-index `LiteLLM` instance from those params:

```python
from llama_index.llms.litellm import LiteLLM

llama_llm = LiteLLM(model=self.llm.get_model_name(), **self.llm.kwargs)
keyword_index = KeywordTableIndex(nodes=..., llm=llama_llm)
```

Requires adding `llama-index-llms-litellm` as a dependency.

### Option 3: Quick Fix for KeywordTable Only

Use `SimpleKeywordTableIndex` instead of `KeywordTableIndex`. The "simple" variant uses regex-based keyword extraction and does NOT call `predict()`.

```python
from llama_index.core.indices.keyword_table import SimpleKeywordTableIndex

keyword_index = SimpleKeywordTableIndex(
    nodes=[node.node for node in all_nodes],
    show_progress=True,
    # No llm parameter needed
)
```

**Limitation**: This only fixes `KeywordTableRetriever`. The other broken retrievers still need a solution.

## Recommendation

**Option 1 (Bridge Adapter)** is recommended because:
- Fixes all affected retrievers with a single adapter class
- No new dependencies needed
- Keeps SDK1's LiteLLM-based architecture intact
- Can be applied at the `BaseRetriever` level so all retrievers benefit

The bridge could be created once in the base retriever or in a shared utility, so each retriever doesn't need to worry about the conversion.
