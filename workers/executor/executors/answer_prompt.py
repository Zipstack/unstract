"""Answer prompt service — prompt construction and LLM execution.

Ported from prompt-service/.../services/answer_prompt.py.
Flask dependencies (app.logger, PluginManager, APIError) replaced with
standard logging and executor exceptions.

Highlight/word-confidence support is available via the ``process_text``
callback parameter — callers pass the highlight-data plugin's ``run``
method when the plugin is installed.  Challenge and evaluation plugins
are integrated at the caller level (LegacyExecutor).
"""

import ipaddress
import logging
import os
import socket
from typing import Any
from urllib.parse import urlparse

from executor.executors.constants import PromptServiceConstants as PSKeys
from executor.executors.exceptions import LegacyExecutorError, RateLimitError
from unstract.sdk1.constants import (
    ExtractionInputs,
    VisionMode,
    derive_vision_mode,
)
from unstract.sdk1.rasteriser import RenderSettings, rasterise_pages
from unstract.sdk1.vision import build_vision_messages

logger = logging.getLogger(__name__)


def _resolve_host_addresses(host: str) -> set[str]:
    """Resolve a hostname or IP string to a set of IP address strings."""
    try:
        ipaddress.ip_address(host)
        return {host}
    except ValueError:
        pass
    try:
        return {
            sockaddr[0]
            for _family, _type, _proto, _canonname, sockaddr in socket.getaddrinfo(
                host, None, type=socket.SOCK_STREAM
            )
        }
    except Exception:
        return set()


def _is_safe_public_url(url: str) -> bool:
    """Validate webhook URL for SSRF protection.

    Only allows HTTPS and blocks private/loopback/internal addresses.
    """
    try:
        p = urlparse(url)
        if p.scheme not in ("https",):
            return False
        host = p.hostname or ""
        if host in ("localhost",):
            return False

        addrs = _resolve_host_addresses(host)
        if not addrs:
            return False

        for addr in addrs:
            try:
                ip = ipaddress.ip_address(addr)
            except ValueError:
                return False
            if (
                ip.is_private
                or ip.is_loopback
                or ip.is_link_local
                or ip.is_reserved
                or ip.is_multicast
            ):
                return False
        return True
    except Exception:
        return False


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
        source_file_path: str = "",
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
            source_file_path: Path to the original source file (PDF) for
                vision mode rasterisation. Empty string disables vision.

        Returns:
            The LLM answer string.
        """
        # Derive vision mode from per-prompt fields
        extraction_inputs = output.get(
            PSKeys.EXTRACTION_INPUTS, ExtractionInputs.TEXT
        )
        source_of_truth = output.get(PSKeys.SOURCE_OF_TRUTH, "text")
        vision_mode = derive_vision_mode(extraction_inputs, source_of_truth)

        platform_postamble = tool_settings.get(PSKeys.PLATFORM_POSTAMBLE, "")
        word_confidence_postamble = tool_settings.get(
            PSKeys.WORD_CONFIDENCE_POSTAMBLE, ""
        )
        summarize_as_source = tool_settings.get(PSKeys.SUMMARIZE_AS_SOURCE)
        enable_highlight = tool_settings.get(PSKeys.ENABLE_HIGHLIGHT, False)
        enable_word_confidence = tool_settings.get(PSKeys.ENABLE_WORD_CONFIDENCE, False)
        if not enable_highlight:
            enable_word_confidence = False

        # Vision mode: suppress highlights and postambles (no OCR line
        # metadata to ground against)
        if vision_mode != VisionMode.TEXT_ONLY:
            platform_postamble = ""
            word_confidence_postamble = ""
            enable_highlight = False
            enable_word_confidence = False
            process_text = None

        prompt_type = output.get(PSKeys.TYPE, PSKeys.TEXT)
        if not enable_highlight or summarize_as_source:
            platform_postamble = ""
        if not enable_word_confidence or summarize_as_source:
            word_confidence_postamble = ""

        prompt = AnswerPromptService.construct_prompt(
            preamble=tool_settings.get(PSKeys.PREAMBLE, ""),
            prompt=output[prompt],
            postamble=tool_settings.get(PSKeys.POSTAMBLE, ""),
            grammar_list=tool_settings.get(PSKeys.GRAMMAR, []),
            context=context,
            platform_postamble=platform_postamble,
            word_confidence_postamble=word_confidence_postamble,
            prompt_type=prompt_type,
        )
        output[PSKeys.COMBINED_PROMPT] = prompt

        if vision_mode != VisionMode.TEXT_ONLY:
            return AnswerPromptService.run_vision_completion(
                llm=llm,
                text_prompt=prompt,
                text_context=context,
                source_file_path=source_file_path,
                vision_mode=vision_mode,
                metadata=metadata,
                prompt_key=output[PSKeys.NAME],
                prompt_type=prompt_type,
                preamble=tool_settings.get(PSKeys.PREAMBLE, ""),
                execution_source=execution_source or "ide",
            )

        return AnswerPromptService.run_completion(
            llm=llm,
            prompt=prompt,
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
        if prompt_type == PSKeys.JSON:
            json_postamble = os.environ.get(
                PSKeys.JSON_POSTAMBLE, PSKeys.DEFAULT_JSON_POSTAMBLE
            )
            postamble += f"\n{json_postamble}"
        if platform_postamble:
            platform_postamble += "\n\n"
            if word_confidence_postamble:
                platform_postamble += f"{word_confidence_postamble}\n\n"
        prompt += (
            f"\n\n{postamble}\n\nContext:\n---------------\n{context}\n"
            f"-----------------\n\n{platform_postamble}Answer:"
        )
        return prompt

    @staticmethod
    def run_completion(
        llm: Any,
        prompt: str,
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
    def run_vision_completion(
        llm: Any,
        text_prompt: str,
        text_context: str,
        source_file_path: str,
        vision_mode: str,
        metadata: dict[str, Any],
        prompt_key: str,
        prompt_type: str = "text",
        preamble: str = "",
        execution_source: str = "ide",
    ) -> str:
        """Run VLM completion with page images and optional text context.

        Reads the source file, rasterises pages, builds multimodal messages,
        and calls ``llm.complete_vision()``.

        Args:
            llm: LLM adapter instance.
            text_prompt: The constructed prompt string (preamble + question +
                postamble + context).
            text_context: Retrieved text context (may be empty for image-only).
            source_file_path: Path to the original source file (PDF) in
                file storage, for rasterisation.
            vision_mode: One of VisionMode.SPATIAL_HELPER or
                VisionMode.SOURCE_OF_TRUTH.
            metadata: Metadata dict (updated in place).
            prompt_key: The prompt name for metadata keying.
            prompt_type: "text" or "json" — controls extract_json.
            preamble: The preamble text used as system prompt for the VLM.
            execution_source: "ide" or "tool" — determines storage backend.
        """
        try:
            from unstract.sdk1.exceptions import RateLimitError as _sdk_rate_limit_error
            from unstract.sdk1.exceptions import SdkError as _sdk_error
        except ImportError:
            _sdk_rate_limit_error = Exception
            _sdk_error = Exception

        if not source_file_path:
            raise LegacyExecutorError(
                message=(
                    f"Vision mode '{vision_mode}' requires a source file path "
                    f"for rasterisation, but none was provided for prompt "
                    f"'{prompt_key}'."
                ),
                code=400,
            )

        try:
            # Read source file bytes from file storage
            from executor.executors.file_utils import FileUtils

            fs = FileUtils.get_fs_instance(
                execution_source=execution_source
            )
            file_bytes: bytes = fs.read(path=source_file_path, mode="rb")

            # Rasterise pages
            settings = RenderSettings()
            page_images = rasterise_pages(
                file_bytes=file_bytes,
                settings=settings,
            )
            if not page_images:
                raise LegacyExecutorError(
                    message=(
                        f"No pages could be rasterised from '{source_file_path}' "
                        f"for prompt '{prompt_key}'."
                    ),
                    code=500,
                )

            logger.info(
                "Vision mode=%s: rasterised %d pages for prompt=%s",
                vision_mode,
                len(page_images),
                prompt_key,
            )

            # Map VisionMode constants to build_vision_messages mode strings
            mode_str = (
                "spatial_helper"
                if vision_mode == VisionMode.SPATIAL_HELPER
                else "source_of_truth"
            )

            # Build multimodal messages
            messages = build_vision_messages(
                system_prompt=preamble,
                text_context=text_context if text_context.strip() else None,
                page_images=page_images,
                prompt=text_prompt,
                mode=mode_str,
            )

            # Call VLM completion
            completion = llm.complete_vision(
                messages=messages,
                extract_json=prompt_type.lower() != PSKeys.TEXT,
            )

            answer: str = completion[PSKeys.RESPONSE].text
            return answer

        except _sdk_rate_limit_error as e:
            raise RateLimitError(f"Rate limit error. {str(e)}") from e
        except (LegacyExecutorError, RateLimitError):
            raise
        except _sdk_error as e:
            logger.error(
                "Error during vision completion for prompt %s: %s",
                prompt_key,
                e,
            )
            status_code = getattr(e, "status_code", None) or 500
            raise LegacyExecutorError(message=str(e), code=status_code) from e
        except Exception as e:
            logger.error(
                "Unexpected error during vision completion for prompt %s: %s",
                prompt_key,
                e,
            )
            raise LegacyExecutorError(
                message=f"Vision completion failed: {e}", code=500
            ) from e

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
        if not _is_safe_public_url(webhook_url):
            logger.warning("Postprocessing webhook URL is not allowed; skipping.")
            return parsed_data, None
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
