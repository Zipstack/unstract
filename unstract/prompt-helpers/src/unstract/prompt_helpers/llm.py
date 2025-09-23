"""LLM interaction helper functions.

This module provides helper functions for interacting with Large Language Models
through the Unstract SDK, replacing the Flask-based Prompt Studio service logic
with decoupled, reusable functions.
"""

import logging
import time
from typing import Any, Dict, List, Optional, Union

import structlog
from unstract.sdk1.llm import LLM

from .models import (
    LLMConfig,
    LLMProcessingResult,
    ProcessingStatus,
    WorkflowContext,
)

logger = structlog.get_logger(__name__)


class LLMHelper:
    """Helper class for LLM interactions.
    
    This class provides high-level methods for interacting with LLMs
    through the Unstract SDK, handling common patterns like prompt
    processing, conversation management, and result validation.
    """
    
    def __init__(
        self,
        adapter_instance_id: str,
        config: Optional[LLMConfig] = None,
        **kwargs
    ):
        """Initialize LLM helper.
        
        Args:
            adapter_instance_id: ID of the LLM adapter instance
            config: Optional LLM configuration
            **kwargs: Additional configuration parameters
        """
        self.adapter_instance_id = adapter_instance_id
        self.config = config or LLMConfig(
            adapter_instance_id=adapter_instance_id,
            **kwargs
        )
        self._llm_instance: Optional[LLM] = None
        self._logger = logger.bind(adapter_id=adapter_instance_id)
    
    @property
    def llm(self) -> LLM:
        """Get or create LLM instance."""
        if self._llm_instance is None:
            self._llm_instance = LLM(
                adapter_instance_id=self.adapter_instance_id
            )
        return self._llm_instance
    
    def process_prompt(
        self,
        prompt: str,
        context: Optional[Dict[str, Any]] = None,
        workflow_context: Optional[WorkflowContext] = None,
        **override_config
    ) -> LLMProcessingResult:
        """Process a prompt through the LLM.
        
        Args:
            prompt: The prompt text to process
            context: Optional context variables for prompt formatting
            workflow_context: Optional workflow context
            **override_config: Configuration overrides
            
        Returns:
            LLMProcessingResult with response and metadata
        """
        start_time = time.time()
        result = LLMProcessingResult(
            prompt=prompt,
            status=ProcessingStatus.PROCESSING
        )
        
        try:
            # Format prompt with context if provided
            formatted_prompt = self._format_prompt(prompt, context)
            
            # Apply configuration overrides
            llm_config = self._get_effective_config(**override_config)
            
            # Process through LLM
            self._logger.info("Processing LLM prompt", 
                            prompt_length=len(formatted_prompt))
            
            response = self.llm.invoke(
                prompt=formatted_prompt,
                temperature=llm_config.temperature,
                max_tokens=llm_config.max_tokens,
                top_p=llm_config.top_p,
                frequency_penalty=llm_config.frequency_penalty,
                presence_penalty=llm_config.presence_penalty,
                stop=llm_config.stop_sequences or None,
            )
            
            # Process response
            processing_time = int((time.time() - start_time) * 1000)
            
            result.response = response.content
            result.model_used = response.model_name if hasattr(response, 'model_name') else None
            result.tokens_used = response.token_usage.total_tokens if hasattr(response, 'token_usage') else None
            result.prompt_tokens = response.token_usage.prompt_tokens if hasattr(response, 'token_usage') else None
            result.completion_tokens = response.token_usage.completion_tokens if hasattr(response, 'token_usage') else None
            result.temperature = llm_config.temperature
            result.max_tokens = llm_config.max_tokens
            result.mark_completed(processing_time)
            
            self._logger.info("LLM processing completed",
                            response_length=len(response.content),
                            processing_time_ms=processing_time,
                            tokens_used=result.tokens_used)
            
            return result
            
        except Exception as e:
            processing_time = int((time.time() - start_time) * 1000)
            error_message = f"LLM processing failed: {e}"
            result.mark_failed(error_message)
            result.processing_time_ms = processing_time
            
            self._logger.error("LLM processing failed",
                             error=str(e),
                             processing_time_ms=processing_time)
            
            return result
    
    def process_conversation(
        self,
        messages: List[Dict[str, str]],
        system_prompt: Optional[str] = None,
        **override_config
    ) -> LLMProcessingResult:
        """Process a conversation with multiple messages.
        
        Args:
            messages: List of message dicts with 'role' and 'content'
            system_prompt: Optional system prompt
            **override_config: Configuration overrides
            
        Returns:
            LLMProcessingResult with response
        """
        # Convert conversation to single prompt format
        conversation_prompt = self._format_conversation(messages, system_prompt)
        
        return self.process_prompt(
            conversation_prompt,
            workflow_context=None,
            **override_config
        )
    
    def validate_response(
        self,
        response: str,
        validation_prompt: str,
        expected_format: Optional[str] = None,
        **override_config
    ) -> LLMProcessingResult:
        """Validate a response using another LLM call.
        
        Args:
            response: Response to validate
            validation_prompt: Prompt for validation
            expected_format: Expected format description
            **override_config: Configuration overrides
            
        Returns:
            LLMProcessingResult with validation result
        """
        validation_context = {
            "response": response,
            "expected_format": expected_format or "any valid response"
        }
        
        return self.process_prompt(
            validation_prompt,
            context=validation_context,
            **override_config
        )
    
    def generate_summary(
        self,
        text: str,
        summary_type: str = "concise",
        max_length: Optional[int] = None,
        **override_config
    ) -> LLMProcessingResult:
        """Generate a summary of the given text.
        
        Args:
            text: Text to summarize
            summary_type: Type of summary (concise, detailed, bullet_points)
            max_length: Maximum length of summary
            **override_config: Configuration overrides
            
        Returns:
            LLMProcessingResult with summary
        """
        summary_prompts = {
            "concise": "Provide a concise summary of the following text:\n\n{text}",
            "detailed": "Provide a detailed summary of the following text, covering all key points:\n\n{text}",
            "bullet_points": "Summarize the following text as bullet points:\n\n{text}"
        }
        
        prompt = summary_prompts.get(summary_type, summary_prompts["concise"])
        context = {"text": text}
        
        if max_length:
            prompt += f"\n\nKeep the summary under {max_length} words."
        
        return self.process_prompt(prompt, context=context, **override_config)
    
    def extract_structured_data(
        self,
        text: str,
        extraction_schema: Dict[str, Any],
        output_format: str = "json",
        **override_config
    ) -> LLMProcessingResult:
        """Extract structured data from text.
        
        Args:
            text: Source text for extraction
            extraction_schema: Schema describing what to extract
            output_format: Output format (json, yaml, xml)
            **override_config: Configuration overrides
            
        Returns:
            LLMProcessingResult with structured data
        """
        schema_description = self._format_extraction_schema(extraction_schema)
        
        prompt = f"""Extract the following information from the text below and format as {output_format.upper()}:

Schema:
{schema_description}

Text:
{text}

Extracted {output_format.upper()}:"""
        
        return self.process_prompt(prompt, **override_config)
    
    def get_model_info(self) -> Dict[str, Any]:
        """Get information about the LLM model.
        
        Returns:
            Dictionary with model information
        """
        try:
            # This would need to be implemented in the SDK
            # For now, return basic info
            return {
                "adapter_instance_id": self.adapter_instance_id,
                "config": self.config.dict(),
                "status": "active"
            }
        except Exception as e:
            self._logger.warning("Failed to get model info", error=str(e))
            return {"error": str(e)}
    
    def _format_prompt(
        self,
        prompt: str,
        context: Optional[Dict[str, Any]] = None
    ) -> str:
        """Format prompt with context variables.
        
        Args:
            prompt: Template prompt with placeholders
            context: Context variables for formatting
            
        Returns:
            Formatted prompt string
        """
        if not context:
            return prompt
        
        try:
            return prompt.format(**context)
        except KeyError as e:
            self._logger.warning("Missing context variable", variable=str(e))
            return prompt
        except Exception as e:
            self._logger.error("Prompt formatting failed", error=str(e))
            return prompt
    
    def _format_conversation(
        self,
        messages: List[Dict[str, str]],
        system_prompt: Optional[str] = None
    ) -> str:
        """Format conversation messages into a single prompt.
        
        Args:
            messages: List of message dictionaries
            system_prompt: Optional system prompt
            
        Returns:
            Formatted conversation prompt
        """
        formatted_parts = []
        
        if system_prompt:
            formatted_parts.append(f"System: {system_prompt}")
        
        for message in messages:
            role = message.get("role", "user")
            content = message.get("content", "")
            formatted_parts.append(f"{role.title()}: {content}")
        
        return "\n\n".join(formatted_parts)
    
    def _format_extraction_schema(self, schema: Dict[str, Any]) -> str:
        """Format extraction schema for prompt.
        
        Args:
            schema: Schema dictionary
            
        Returns:
            Formatted schema description
        """
        schema_lines = []
        
        for field, description in schema.items():
            if isinstance(description, dict):
                field_type = description.get("type", "string")
                field_desc = description.get("description", "")
                required = description.get("required", False)
                req_str = " (required)" if required else " (optional)"
                schema_lines.append(f"- {field} ({field_type}){req_str}: {field_desc}")
            else:
                schema_lines.append(f"- {field}: {description}")
        
        return "\n".join(schema_lines)
    
    def _get_effective_config(self, **overrides) -> LLMConfig:
        """Get effective configuration with overrides applied.
        
        Args:
            **overrides: Configuration overrides
            
        Returns:
            LLMConfig with overrides applied
        """
        config_dict = self.config.dict()
        config_dict.update(overrides)
        return LLMConfig(**config_dict)


# Convenience functions for common LLM operations
def process_prompt_simple(
    adapter_instance_id: str,
    prompt: str,
    context: Optional[Dict[str, Any]] = None,
    **config_kwargs
) -> LLMProcessingResult:
    """Simple prompt processing function.
    
    Args:
        adapter_instance_id: LLM adapter instance ID
        prompt: Prompt to process
        context: Optional context for prompt formatting
        **config_kwargs: LLM configuration parameters
        
    Returns:
        LLMProcessingResult
    """
    helper = LLMHelper(adapter_instance_id, **config_kwargs)
    return helper.process_prompt(prompt, context)


def extract_data_simple(
    adapter_instance_id: str,
    text: str,
    extraction_fields: List[str],
    **config_kwargs
) -> LLMProcessingResult:
    """Simple data extraction function.
    
    Args:
        adapter_instance_id: LLM adapter instance ID
        text: Text to extract from
        extraction_fields: List of fields to extract
        **config_kwargs: LLM configuration parameters
        
    Returns:
        LLMProcessingResult
    """
    schema = {field: f"Extract {field} from the text" for field in extraction_fields}
    
    helper = LLMHelper(adapter_instance_id, **config_kwargs)
    return helper.extract_structured_data(text, schema)


def summarize_simple(
    adapter_instance_id: str,
    text: str,
    summary_type: str = "concise",
    **config_kwargs
) -> LLMProcessingResult:
    """Simple text summarization function.
    
    Args:
        adapter_instance_id: LLM adapter instance ID
        text: Text to summarize
        summary_type: Type of summary
        **config_kwargs: LLM configuration parameters
        
    Returns:
        LLMProcessingResult
    """
    helper = LLMHelper(adapter_instance_id, **config_kwargs)
    return helper.generate_summary(text, summary_type)