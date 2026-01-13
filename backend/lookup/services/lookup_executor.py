"""Look-Up Executor implementation for single Look-Up execution.

This module provides functionality to execute a single Look-Up project
against input data, including variable resolution, LLM calling, and
response caching.
"""

import json
import logging
import time
import uuid
from typing import Any, Protocol

from lookup.exceptions import (
    ContextWindowExceededError,
    ExtractionNotCompleteError,
    ParseError,
    TemplateNotFoundError,
)
from lookup.models import LookupProject
from lookup.services.audit_logger import AuditLogger

logger = logging.getLogger(__name__)


class LLMClient(Protocol):
    """Protocol for LLM client abstraction."""

    def generate(self, prompt: str, config: dict[str, Any]) -> str:
        """Generate LLM response for the prompt."""
        ...


class LookUpExecutor:
    """Executes a single Look-Up project against input data.

    This class handles the complete execution flow of a Look-Up:
    loading reference data, resolving variables in the prompt template,
    calling the LLM, caching responses, and parsing the results.
    """

    def __init__(
        self,
        variable_resolver,  # Class, not instance
        cache_manager,
        reference_loader,
        llm_client: LLMClient,
    ):
        """Initialize the Look-Up executor.

        Args:
            variable_resolver: VariableResolver class (not instance)
            cache_manager: LLMResponseCache instance
            reference_loader: ReferenceDataLoader instance
            llm_client: LLM provider client implementing LLMClient protocol
        """
        self.variable_resolver_class = variable_resolver
        self.cache = cache_manager
        self.ref_loader = reference_loader
        self.llm_client = llm_client

    def execute(
        self,
        lookup_project: LookupProject,
        input_data: dict[str, Any],
        execution_id: str | None = None,
        prompt_studio_project_id: str | None = None,
    ) -> dict[str, Any]:
        """Execute single Look-Up.

        Performs the complete Look-Up execution including variable resolution,
        LLM calling with caching, and response parsing.

        Args:
            lookup_project: The Look-Up project to execute
            input_data: Input data containing variables to resolve
            execution_id: Optional UUID to group related executions for audit
            prompt_studio_project_id: Optional PS project ID for audit tracking

        Returns:
            Dictionary containing:
                - status: 'success' or 'failed'
                - project_id: UUID of the project
                - project_name: Name of the project
                - data: Enrichment data (if success)
                - confidence: Confidence score 0.0-1.0 (if available)
                - cached: Whether response was from cache
                - execution_time_ms: Time taken in milliseconds
                - error: Error message (if failed)

        Example:
            >>> executor = LookUpExecutor(...)
            >>> result = executor.execute(project, {"vendor": "Slack"})
            >>> if result["status"] == "success":
            ...     print(result["data"])
            {'canonical_vendor': 'Slack Technologies', 'confidence': 0.92}
        """
        start_time = time.time()

        # Initialize audit tracking variables
        exec_id = execution_id or str(uuid.uuid4())
        resolved_prompt = None
        llm_response = None
        llm_time_ms = None
        reference_data_version = 1
        llm_provider = "unknown"
        llm_model = "unknown"
        _cached = False  # noqa F841

        try:
            # Step 1: Load reference data
            try:
                reference_data_dict = self.ref_loader.load_latest_for_project(
                    lookup_project.id
                )
                reference_data = reference_data_dict["content"]
                reference_data_version = reference_data_dict.get("version", 1)
            except ExtractionNotCompleteError as e:
                result = self._failed_result(
                    lookup_project,
                    f"Reference data extraction not complete: {str(e)}",
                    start_time,
                )
                self._log_audit(
                    exec_id,
                    lookup_project,
                    prompt_studio_project_id,
                    input_data,
                    reference_data_version,
                    llm_provider,
                    llm_model,
                    resolved_prompt,
                    llm_response,
                    None,
                    "failed",
                    None,
                    result["execution_time_ms"],
                    None,
                    False,
                    result["error"],
                )
                return result
            except Exception as e:
                result = self._failed_result(
                    lookup_project, f"Failed to load reference data: {str(e)}", start_time
                )
                self._log_audit(
                    exec_id,
                    lookup_project,
                    prompt_studio_project_id,
                    input_data,
                    reference_data_version,
                    llm_provider,
                    llm_model,
                    resolved_prompt,
                    llm_response,
                    None,
                    "failed",
                    None,
                    result["execution_time_ms"],
                    None,
                    False,
                    result["error"],
                )
                return result

            # Step 2: Load prompt template
            try:
                template = lookup_project.template
                if not template:
                    raise TemplateNotFoundError("No template configured")
                template_text = template.template_text

                # Extract LLM info from template config if available
                if template.llm_config:
                    llm_provider = template.llm_config.get("provider", "unknown")
                    llm_model = template.llm_config.get("model", "unknown")
            except (AttributeError, TemplateNotFoundError) as e:
                result = self._failed_result(
                    lookup_project, f"Missing prompt template: {str(e)}", start_time
                )
                self._log_audit(
                    exec_id,
                    lookup_project,
                    prompt_studio_project_id,
                    input_data,
                    reference_data_version,
                    llm_provider,
                    llm_model,
                    resolved_prompt,
                    llm_response,
                    None,
                    "failed",
                    None,
                    result["execution_time_ms"],
                    None,
                    False,
                    result["error"],
                )
                return result

            # Step 3: Resolve variables
            logger.info(f"Input data received: {input_data}")
            logger.info(f"Reference data length: {len(reference_data)} chars")
            logger.info(f"Template text: {template_text[:200]}...")
            resolver = self.variable_resolver_class(input_data, reference_data)
            resolved_prompt = resolver.resolve(template_text)
            logger.info(f"Resolved prompt: {resolved_prompt[:500]}...")

            # Step 4: Check cache (if caching is enabled)
            cache_key = None
            cached_response = None
            if self.cache:
                cache_key = self.cache.generate_cache_key(resolved_prompt, reference_data)
                cached_response = self.cache.get(cache_key)

                if cached_response:
                    # Cache hit - parse and return
                    enrichment_data, confidence = self._parse_llm_response(
                        cached_response
                    )
                    result = self._success_result(
                        lookup_project,
                        enrichment_data,
                        confidence,
                        cached=True,
                        execution_time_ms=0,  # No execution time for cached response
                    )
                    self._log_audit(
                        exec_id,
                        lookup_project,
                        prompt_studio_project_id,
                        input_data,
                        reference_data_version,
                        llm_provider,
                        llm_model,
                        resolved_prompt,
                        cached_response,
                        enrichment_data,
                        "success",
                        confidence,
                        0,
                        None,
                        True,
                        None,
                    )
                    return result

            # Step 5: Call LLM (cache miss or caching disabled)
            try:
                llm_start = time.time()
                llm_response = self.llm_client.generate(
                    resolved_prompt, lookup_project.llm_config or {}
                )
                llm_time_ms = int((time.time() - llm_start) * 1000)

                # Store in cache (if caching is enabled)
                if self.cache and cache_key:
                    self.cache.set(cache_key, llm_response)

            except ContextWindowExceededError as e:
                # Context window exceeded - provide clear actionable error
                error_msg = (
                    f"Context window exceeded: prompt requires {e.token_count:,} "
                    f"tokens but {e.model} limit is {e.context_limit:,} tokens. "
                    f"Reduce reference data size or use a model with larger "
                    f"context window."
                )
                result = self._failed_result(lookup_project, error_msg, start_time)
                self._log_audit(
                    exec_id,
                    lookup_project,
                    prompt_studio_project_id,
                    input_data,
                    reference_data_version,
                    llm_provider,
                    llm_model,
                    resolved_prompt,
                    None,
                    None,
                    "failed",
                    None,
                    result["execution_time_ms"],
                    None,
                    False,
                    error_msg,
                )
                return result
            except TimeoutError as e:
                result = self._failed_result(
                    lookup_project, f"LLM request timed out: {str(e)}", start_time
                )
                self._log_audit(
                    exec_id,
                    lookup_project,
                    prompt_studio_project_id,
                    input_data,
                    reference_data_version,
                    llm_provider,
                    llm_model,
                    resolved_prompt,
                    None,
                    None,
                    "failed",
                    None,
                    result["execution_time_ms"],
                    llm_time_ms,
                    False,
                    result["error"],
                )
                return result
            except Exception as e:
                result = self._failed_result(
                    lookup_project, f"LLM request failed: {str(e)}", start_time
                )
                self._log_audit(
                    exec_id,
                    lookup_project,
                    prompt_studio_project_id,
                    input_data,
                    reference_data_version,
                    llm_provider,
                    llm_model,
                    resolved_prompt,
                    None,
                    None,
                    "failed",
                    None,
                    result["execution_time_ms"],
                    llm_time_ms,
                    False,
                    result["error"],
                )
                return result

            # Step 6: Parse response
            try:
                enrichment_data, confidence = self._parse_llm_response(llm_response)
            except ParseError as e:
                result = self._failed_result(
                    lookup_project, f"Failed to parse LLM response: {str(e)}", start_time
                )
                self._log_audit(
                    exec_id,
                    lookup_project,
                    prompt_studio_project_id,
                    input_data,
                    reference_data_version,
                    llm_provider,
                    llm_model,
                    resolved_prompt,
                    llm_response,
                    None,
                    "failed",
                    None,
                    result["execution_time_ms"],
                    llm_time_ms,
                    False,
                    result["error"],
                )
                return result

            # Step 7: Return result and log success
            result = self._success_result(
                lookup_project,
                enrichment_data,
                confidence,
                cached=False,
                execution_time_ms=llm_time_ms,
            )
            self._log_audit(
                exec_id,
                lookup_project,
                prompt_studio_project_id,
                input_data,
                reference_data_version,
                llm_provider,
                llm_model,
                resolved_prompt,
                llm_response,
                enrichment_data,
                "success",
                confidence,
                llm_time_ms,
                llm_time_ms,
                False,
                None,
            )
            return result

        except Exception as e:
            # Catch-all for unexpected errors
            logger.exception(f"Unexpected error executing Look-Up {lookup_project.id}")
            result = self._failed_result(
                lookup_project, f"Unexpected error: {str(e)}", start_time
            )
            self._log_audit(
                exec_id,
                lookup_project,
                prompt_studio_project_id,
                input_data,
                reference_data_version,
                llm_provider,
                llm_model,
                resolved_prompt,
                llm_response,
                None,
                "failed",
                None,
                result["execution_time_ms"],
                llm_time_ms,
                False,
                result["error"],
            )
            return result

    def _log_audit(
        self,
        execution_id: str,
        lookup_project: LookupProject,
        prompt_studio_project_id: str | None,
        input_data: dict[str, Any],
        reference_data_version: int,
        llm_provider: str,
        llm_model: str,
        llm_prompt: str | None,
        llm_response: str | None,
        enriched_output: dict[str, Any] | None,
        status: str,
        confidence_score: float | None,
        execution_time_ms: int | None,
        llm_call_time_ms: int | None,
        llm_response_cached: bool,
        error_message: str | None,
    ) -> None:
        """Log execution to audit table.

        This method wraps AuditLogger to capture all execution details
        for the Execution History tab.
        """
        try:
            audit_logger = AuditLogger()
            audit_logger.log_execution(
                execution_id=execution_id,
                lookup_project_id=lookup_project.id,
                prompt_studio_project_id=(
                    uuid.UUID(prompt_studio_project_id)
                    if prompt_studio_project_id
                    else None
                ),
                input_data=input_data,
                reference_data_version=reference_data_version,
                llm_provider=llm_provider,
                llm_model=llm_model,
                llm_prompt=llm_prompt or "",
                llm_response=llm_response,
                enriched_output=enriched_output,
                status=status,
                confidence_score=confidence_score,
                execution_time_ms=execution_time_ms,
                llm_call_time_ms=llm_call_time_ms,
                llm_response_cached=llm_response_cached,
                error_message=error_message,
            )
            logger.debug(
                f"Audit logged for Look-Up {lookup_project.name} "
                f"(execution_id={execution_id}, status={status})"
            )
        except Exception as e:
            # Don't fail the execution if audit logging fails
            logger.warning(f"Failed to log audit for Look-Up execution: {e}")

    def _parse_llm_response(self, response_text: str) -> tuple[dict, float | None]:
        """Parse LLM response to extract enrichment data.

        Attempts to parse the LLM response as JSON and extract
        enrichment fields and optional confidence score.

        Args:
            response_text: Raw text response from the LLM

        Returns:
            Tuple of (enrichment_data, confidence)
            - enrichment_data: Dictionary of extracted fields
            - confidence: Optional confidence score (0.0-1.0)

        Raises:
            ParseError: If response cannot be parsed as valid JSON

        Example:
            >>> response = '{"vendor": "Slack", "confidence": 0.92}'
            >>> data, conf = executor._parse_llm_response(response)
            >>> print(data)
            {'vendor': 'Slack'}
            >>> print(conf)
            0.92
        """
        try:
            # Try direct JSON parse
            parsed = json.loads(response_text)

            if not isinstance(parsed, dict):
                raise ParseError(f"Expected JSON object, got {type(parsed).__name__}")

            # Extract confidence if present
            confidence = None
            if "confidence" in parsed:
                confidence = parsed.pop("confidence")

                # Validate confidence is a number between 0 and 1
                if isinstance(confidence, (int, float)):
                    confidence = float(confidence)
                    if not 0.0 <= confidence <= 1.0:
                        logger.warning(
                            f"Confidence {confidence} outside valid range [0.0, 1.0]"
                        )
                        confidence = max(0.0, min(1.0, confidence))  # Clamp to range
                else:
                    logger.warning(f"Invalid confidence type: {type(confidence)}")
                    confidence = None

            # Remaining fields are the enrichment data
            enrichment_data = parsed

            return enrichment_data, confidence

        except json.JSONDecodeError as e:
            logger.warning(f"Failed to parse LLM response as JSON: {e}")
            raise ParseError(f"Invalid JSON response: {str(e)}")
        except Exception as e:
            logger.warning(f"Unexpected error parsing LLM response: {e}")
            raise ParseError(f"Parse error: {str(e)}")

    def _success_result(
        self,
        project: LookupProject,
        data: dict[str, Any],
        confidence: float | None,
        cached: bool,
        execution_time_ms: int,
    ) -> dict[str, Any]:
        """Build success result dictionary."""
        return {
            "status": "success",
            "project_id": str(project.id),  # Convert UUID to string for JSON
            "project_name": project.name,
            "data": data,
            "confidence": confidence,
            "cached": cached,
            "execution_time_ms": execution_time_ms,
        }

    def _failed_result(
        self, project: LookupProject, error: str, start_time: float
    ) -> dict[str, Any]:
        """Build failed result dictionary."""
        execution_time_ms = int((time.time() - start_time) * 1000)
        return {
            "status": "failed",
            "project_id": str(project.id),  # Convert UUID to string for JSON
            "project_name": project.name,
            "error": error,
            "execution_time_ms": execution_time_ms,
            "cached": False,
        }
