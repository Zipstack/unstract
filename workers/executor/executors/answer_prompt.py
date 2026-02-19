"""Answer prompt service — prompt construction and LLM execution.

Ported from prompt-service/.../services/answer_prompt.py.
Flask dependencies (app.logger, PluginManager, APIError) replaced with
standard logging and executor exceptions.

Plugin-dependent features (highlight, challenge, table-extraction,
line-item-extraction) are omitted — they require a plugin loading
mechanism that will be added in a later phase.
"""

import ipaddress
import logging
import os
import socket
from typing import Any
from urllib.parse import urlparse

from executor.executors.constants import PromptServiceConstants as PSKeys
from executor.executors.exceptions import LegacyExecutorError, RateLimitError

logger = logging.getLogger(__name__)


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

        addrs: set[str] = set()
        try:
            ipaddress.ip_address(host)
            addrs.add(host)
        except ValueError:
            try:
                for _family, _type, _proto, _canonname, sockaddr in socket.getaddrinfo(
                    host, None, type=socket.SOCK_STREAM
                ):
                    addrs.add(sockaddr[0])
            except Exception:
                return False

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
            logger.info("Prompt after variable replacement: %s", promptx)
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
        )

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
        if grammar_list is not None and len(grammar_list) > 0:
            prompt += "\n"
            for grammar in grammar_list:
                word = ""
                synonyms = []
                if PSKeys.WORD in grammar:
                    word = grammar[PSKeys.WORD]
                    if PSKeys.SYNONYMS in grammar:
                        synonyms = grammar[PSKeys.SYNONYMS]
                if len(synonyms) > 0 and word != "":
                    prompt += (
                        f"\nNote: You can consider that the word '{word}' "
                        f"is the same as {', '.join(synonyms)} "
                        f"in both the question and the context."
                    )
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
    ) -> str:
        """Run LLM completion and extract the answer.

        Highlight/word-confidence plugin support is not available in the
        executor worker yet — those features are skipped here.
        """
        try:
            from unstract.sdk1.exceptions import RateLimitError as SdkRateLimitError
            from unstract.sdk1.exceptions import SdkError
        except ImportError:
            SdkRateLimitError = Exception
            SdkError = Exception

        try:
            completion = llm.complete(
                prompt=prompt,
                process_text=None,
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
        except SdkRateLimitError as e:
            raise RateLimitError(f"Rate limit error. {str(e)}") from e
        except SdkError as e:
            logger.error("Error fetching response for prompt: %s", e)
            status_code = getattr(e, "status_code", None) or 500
            raise LegacyExecutorError(message=str(e), code=status_code) from e

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
        from executor.executors.postprocessor import postprocess_data

        prompt_key = output[PSKeys.NAME]
        if answer.lower() == "na":
            structured_output[prompt_key] = None
        else:
            parsed_data = repair_json_with_best_structure(answer)

            if isinstance(parsed_data, str):
                logger.error("Error parsing response to JSON")
                structured_output[prompt_key] = {}
            else:
                webhook_enabled = output.get(PSKeys.ENABLE_POSTPROCESSING_WEBHOOK, False)
                webhook_url = output.get(PSKeys.POSTPROCESSING_WEBHOOK_URL)

                highlight_data = None
                if enable_highlight and metadata and PSKeys.HIGHLIGHT_DATA in metadata:
                    highlight_data = metadata[PSKeys.HIGHLIGHT_DATA].get(prompt_key)

                processed_data = parsed_data
                updated_highlight_data = None

                if webhook_enabled:
                    if not webhook_url:
                        logger.warning(
                            "Postprocessing webhook enabled but URL missing; skipping."
                        )
                    elif not _is_safe_public_url(webhook_url):
                        logger.warning(
                            "Postprocessing webhook URL is not allowed; skipping."
                        )
                    else:
                        try:
                            processed_data, updated_highlight_data = postprocess_data(
                                parsed_data,
                                webhook_enabled=True,
                                webhook_url=webhook_url,
                                highlight_data=highlight_data,
                                timeout=60,
                            )
                        except Exception as e:
                            logger.warning(
                                "Postprocessing webhook failed: %s. "
                                "Using unprocessed data.",
                                e,
                            )

                structured_output[prompt_key] = processed_data

                if (
                    enable_highlight
                    and metadata
                    and updated_highlight_data is not None
                ):
                    metadata.setdefault(PSKeys.HIGHLIGHT_DATA, {})[prompt_key] = (
                        updated_highlight_data
                    )
