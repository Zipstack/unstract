"""Answer prompt service — prompt construction and LLM execution.

Ported from prompt-service/.../services/answer_prompt.py.
Flask dependencies (app.logger, PluginManager, APIError) replaced with
standard logging and executor exceptions.

Highlight/word-confidence support is available via the ``process_text``
callback parameter — callers pass the highlight-data plugin's ``run``
method when the plugin is installed.  Challenge and evaluation plugins
are integrated at the caller level (LegacyExecutor).
"""

import logging
import os
from typing import Any

from executor.executors.constants import PromptServiceConstants as PSKeys
from executor.executors.exceptions import LegacyExecutorError, RateLimitError

logger = logging.getLogger(__name__)


class AnswerPromptService:
    @staticmethod
    def extract_variable(
        structured_output: dict[str, Any],
        variable_names: list[Any],
        output: dict[str, Any],
        promptx: str,
    ) -> str:
        """Replace %variable_name% references in the prompt text."""
        for variable_name in variable_names:
            if promptx.find(f"%{variable_name}%") >= 0:
                if variable_name in structured_output:
                    promptx = promptx.replace(
                        f"%{variable_name}%",
                        str(structured_output[variable_name]),
                    )
                else:
                    raise ValueError(
                        f"Variable {variable_name} not found in structured output"
                    )

        if promptx != output[PSKeys.PROMPT]:
            logger.debug(
                "Prompt modified by variable replacement for: %s",
                output.get(PSKeys.NAME, ""),
            )
        return promptx

    @staticmethod
    def _llm_caches_prompts(llm: Any) -> bool:
        """Whether reordering into a cached prefix pays off for this LLM.

        True only when the LLM reports prompt caching is active for it — caching
        enabled (adapter flag / constructor arg / ``ENABLE_PROMPT_CACHING``
        master switch) AND a supported provider/model. LLM objects that don't
        expose the capability default to False, so their prompt order is left
        unchanged.
        """
        checker = getattr(llm, "is_prompt_caching_active", None)
        if not callable(checker):
            return False
        # Fail closed: if the probe raises, keep the original (context-last)
        # prompt order rather than risk a reorder for an LLM whose caching
        # support is unknown. Hence the deliberately broad excepts below.
        try:
            return bool(checker())
        except Exception:  # noqa: BLE001 - fail closed, see comment above
            provider = getattr(getattr(llm, "adapter", None), "get_provider", None)
            provider_name = None
            if callable(provider):
                try:
                    provider_name = provider()
                except Exception:  # noqa: BLE001 - provider is best-effort log context
                    provider_name = None
            logger.warning(
                "Failed to determine prompt-caching support for LLM "
                "(type=%s, provider=%s); using original prompt order",
                type(llm).__name__,
                provider_name,
                exc_info=True,
            )
            return False

    @staticmethod
    def construct_and_run_prompt(
        tool_settings: dict[str, Any],
        output: dict[str, Any],
        llm: Any,
        context: str,
        prompt: str,
        metadata: dict[str, Any],
        file_path: str = "",
        execution_source: str | None = "ide",
        process_text: Any = None,
    ) -> str:
        """Construct the full prompt and run LLM completion.

        Args:
            tool_settings: Global tool settings (preamble, postamble, etc.)
            output: The prompt definition dict.
            llm: LLM adapter instance.
            context: Retrieved context string.
            prompt: Key into ``output`` for the prompt text (usually "promptx").
            metadata: Metadata dict (updated in place with highlight info).
            file_path: Path to the extracted text file.
            execution_source: "ide" or "tool".
            process_text: Optional callback for text processing during
                completion (e.g. highlight-data plugin's ``run`` method).

        Returns:
            The LLM answer string.
        """
        platform_postamble = tool_settings.get(PSKeys.PLATFORM_POSTAMBLE, "")
        word_confidence_postamble = tool_settings.get(
            PSKeys.WORD_CONFIDENCE_POSTAMBLE, ""
        )
        summarize_as_source = tool_settings.get(PSKeys.SUMMARIZE_AS_SOURCE)
        enable_highlight = tool_settings.get(PSKeys.ENABLE_HIGHLIGHT, False)
        enable_word_confidence = tool_settings.get(PSKeys.ENABLE_WORD_CONFIDENCE, False)
        if not enable_highlight:
            enable_word_confidence = False
        prompt_type = output.get(PSKeys.TYPE, PSKeys.TEXT)
        if not enable_highlight or summarize_as_source:
            platform_postamble = ""
        if not enable_word_confidence or summarize_as_source:
            word_confidence_postamble = ""

        prompt_args = {
            "preamble": tool_settings.get(PSKeys.PREAMBLE, ""),
            "prompt": output[prompt],
            "postamble": tool_settings.get(PSKeys.POSTAMBLE, ""),
            "grammar_list": tool_settings.get(PSKeys.GRAMMAR, []),
            "context": context,
            "platform_postamble": platform_postamble,
            "word_confidence_postamble": word_confidence_postamble,
            "prompt_type": prompt_type,
        }
        cache_prefix: str | None = None
        # Only reorder into a cached prefix when this LLM actually caches
        # (caching enabled AND a supported provider/model). Reordering for an
        # unsupported provider would change the prompt structure — moving the
        # document context ahead of the instructions — with no caching benefit,
        # so those providers keep the original prompt order.
        if AnswerPromptService._llm_caches_prompts(llm):
            # Reorder so the reused document context becomes a cached prefix.
            # The text the model sees is ``cache_prefix + prompt_str``.
            cache_prefix, prompt_str = AnswerPromptService.construct_cached_prompt(
                **prompt_args
            )
            output[PSKeys.COMBINED_PROMPT] = cache_prefix + prompt_str
        else:
            prompt_str = AnswerPromptService.construct_prompt(**prompt_args)
            output[PSKeys.COMBINED_PROMPT] = prompt_str
        return AnswerPromptService.run_completion(
            llm=llm,
            prompt=prompt_str,
            cache_prefix=cache_prefix,
            metadata=metadata,
            prompt_key=output[PSKeys.NAME],
            prompt_type=prompt_type,
            enable_highlight=enable_highlight,
            enable_word_confidence=enable_word_confidence,
            file_path=file_path,
            execution_source=execution_source,
            process_text=process_text,
        )

    @staticmethod
    def _build_grammar_notes(grammar_list: list[dict[str, Any]]) -> str:
        """Build grammar synonym notes for prompt injection."""
        if not grammar_list:
            return ""
        notes = "\n"
        for grammar in grammar_list:
            word = grammar.get(PSKeys.WORD, "")
            synonyms = grammar.get(PSKeys.SYNONYMS, []) if word else []
            if synonyms and word:
                notes += (
                    f"\nNote: You can consider that the word '{word}' "
                    f"is the same as {', '.join(synonyms)} "
                    f"in both the question and the context."
                )
        return notes

    @staticmethod
    def _prepare_postambles(
        postamble: str,
        platform_postamble: str,
        word_confidence_postamble: str,
        prompt_type: str,
    ) -> tuple[str, str]:
        """Apply JSON + platform/word-confidence formatting to the postambles.

        Shared by :meth:`construct_prompt` and :meth:`construct_cached_prompt` so
        the cached and non-cached prompts stay byte-identical apart from the
        context/question ordering. Returns the ``(postamble, platform_postamble)``
        pair to interpolate.
        """
        if prompt_type == PSKeys.JSON:
            json_postamble = os.environ.get(
                PSKeys.JSON_POSTAMBLE, PSKeys.DEFAULT_JSON_POSTAMBLE
            )
            postamble += f"\n{json_postamble}"
        if platform_postamble:
            platform_postamble += "\n\n"
            if word_confidence_postamble:
                platform_postamble += f"{word_confidence_postamble}\n\n"
        return postamble, platform_postamble

    @staticmethod
    def construct_prompt(
        preamble: str,
        prompt: str,
        postamble: str,
        grammar_list: list[dict[str, Any]],
        context: str,
        platform_postamble: str,
        word_confidence_postamble: str,
        prompt_type: str = "text",
    ) -> str:
        """Build the full prompt string with preamble, grammar, postamble, context."""
        prompt = f"{preamble}\n\nQuestion or Instruction: {prompt}"
        prompt += AnswerPromptService._build_grammar_notes(grammar_list)
        postamble, platform_postamble = AnswerPromptService._prepare_postambles(
            postamble, platform_postamble, word_confidence_postamble, prompt_type
        )
        prompt += (
            f"\n\n{postamble}\n\nContext:\n---------------\n{context}\n"
            f"-----------------\n\n{platform_postamble}Answer:"
        )
        return prompt

    @staticmethod
    def construct_cached_prompt(
        preamble: str,
        prompt: str,
        postamble: str,
        grammar_list: list[dict[str, Any]],
        context: str,
        platform_postamble: str,
        word_confidence_postamble: str,
        prompt_type: str = "text",
    ) -> tuple[str, str]:
        """Build ``(cache_prefix, volatile)`` with the document context first.

        Same content as :meth:`construct_prompt`, but the reused ``context`` is
        moved to the front so it forms a cacheable prefix that repeats across
        every prompt run against the same document, while the per-prompt
        question is the volatile suffix. The model sees ``cache_prefix +
        volatile``. This reorders the prompt (context before question instead of
        after), which is why it is flag-gated and A/B-evaluated.
        """
        postamble, platform_postamble = AnswerPromptService._prepare_postambles(
            postamble, platform_postamble, word_confidence_postamble, prompt_type
        )
        cache_prefix = f"Context:\n---------------\n{context}\n-----------------\n\n"
        volatile = (
            f"{preamble}\n\nQuestion or Instruction: {prompt}"
            + AnswerPromptService._build_grammar_notes(grammar_list)
            + f"\n\n{postamble}\n\n{platform_postamble}Answer:"
        )
        return cache_prefix, volatile

    @staticmethod
    def run_completion(
        llm: Any,
        prompt: str,
        cache_prefix: str | None = None,
        metadata: dict[str, str] | None = None,
        prompt_key: str | None = None,
        prompt_type: str | None = "text",
        enable_highlight: bool = False,
        enable_word_confidence: bool = False,
        file_path: str = "",
        execution_source: str | None = None,
        process_text: Any = None,
    ) -> str:
        """Run LLM completion and extract the answer.

        Args:
            process_text: Optional callback for text processing during
                completion (e.g. highlight-data plugin's ``run`` method).
                When provided, the SDK passes LLM response text through
                this callback, enabling source attribution.
        """
        try:
            from unstract.sdk1.exceptions import RateLimitError as _sdk_rate_limit_error
            from unstract.sdk1.exceptions import SdkError as _sdk_error
        except ImportError:
            _sdk_rate_limit_error = Exception
            _sdk_error = Exception

        try:
            completion = llm.complete(
                prompt=prompt,
                cache_prefix=cache_prefix,
                process_text=process_text,
                extract_json=prompt_type.lower() != PSKeys.TEXT,
            )
            answer: str = completion[PSKeys.RESPONSE].text
            highlight_data = completion.get(PSKeys.HIGHLIGHT_DATA, [])
            confidence_data = completion.get(PSKeys.CONFIDENCE_DATA)
            word_confidence_data = completion.get(PSKeys.WORD_CONFIDENCE_DATA)
            line_numbers = completion.get(PSKeys.LINE_NUMBERS, [])
            whisper_hash = completion.get(PSKeys.WHISPER_HASH, "")
            if metadata is not None and prompt_key:
                metadata.setdefault(PSKeys.HIGHLIGHT_DATA, {})[prompt_key] = (
                    highlight_data
                )
                metadata.setdefault(PSKeys.LINE_NUMBERS, {})[prompt_key] = line_numbers
                metadata[PSKeys.WHISPER_HASH] = whisper_hash
                if confidence_data:
                    metadata.setdefault(PSKeys.CONFIDENCE_DATA, {})[prompt_key] = (
                        confidence_data
                    )
                if enable_word_confidence and word_confidence_data:
                    metadata.setdefault(PSKeys.WORD_CONFIDENCE_DATA, {})[prompt_key] = (
                        word_confidence_data
                    )
            return answer
        except _sdk_rate_limit_error as e:
            raise RateLimitError(f"Rate limit error. {str(e)}") from e
        except _sdk_error as e:
            logger.error("Error fetching response for prompt: %s", e)
            status_code = getattr(e, "status_code", None) or 500
            raise LegacyExecutorError(message=str(e), code=status_code) from e

    @staticmethod
    def _run_webhook_postprocess(
        parsed_data: Any,
        webhook_url: str | None,
        highlight_data: Any,
    ) -> tuple[Any, Any]:
        """Run webhook-based postprocessing; return (processed_data, updated_highlight)."""
        from executor.executors.postprocessor import postprocess_data

        if not webhook_url:
            logger.warning("Postprocessing webhook enabled but URL missing; skipping.")
            return parsed_data, None
        # No URL check here: _make_webhook_request applies the identical guard
        # at the sink. Duplicating it only bought a second blocking getaddrinfo
        # per prompt per document.
        try:
            return postprocess_data(
                parsed_data,
                webhook_enabled=True,
                webhook_url=webhook_url,
                highlight_data=highlight_data,
                timeout=60,
            )
        except Exception as e:
            logger.warning(
                "Postprocessing webhook failed: %s. Using unprocessed data.", e
            )
            return parsed_data, None

    @staticmethod
    def handle_json(
        answer: str,
        structured_output: dict[str, Any],
        output: dict[str, Any],
        llm: Any,
        enable_highlight: bool = False,
        enable_word_confidence: bool = False,
        execution_source: str = "ide",
        metadata: dict[str, Any] | None = None,
        file_path: str = "",
        log_events_id: str = "",
        tool_id: str = "",
        doc_name: str = "",
    ) -> None:
        """Handle JSON responses from the LLM."""
        from executor.executors.json_repair_helper import repair_json_with_best_structure

        prompt_key = output[PSKeys.NAME]
        if answer.lower() == "na":
            structured_output[prompt_key] = None
            return

        parsed_data = repair_json_with_best_structure(answer)
        if not isinstance(parsed_data, (dict, list)):
            logger.error("Error parsing response to JSON")
            structured_output[prompt_key] = {}
            return

        structured_output[prompt_key] = parsed_data
