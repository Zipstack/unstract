"""Custom exceptions for the Look-Up system.

This module defines custom exceptions specific to the Look-Up functionality.
"""


class LookupError(Exception):
    """Base exception for Look-Up system errors."""

    pass


class ExtractionNotCompleteError(LookupError):
    """Raised when attempting to use reference data before extraction is complete.

    This exception is raised when trying to load reference data for a project
    where one or more data sources have not completed extraction processing.
    """

    def __init__(self, failed_files=None):
        """Initialize the exception.

        Args:
            failed_files: List of file names that failed or are pending extraction
        """
        self.failed_files = failed_files or []
        message = "Reference data extraction not complete"
        if failed_files:
            message += f" for files: {', '.join(failed_files)}"
        super().__init__(message)


class TemplateNotFoundError(LookupError):
    """Raised when a Look-Up project has no associated template.

    This exception is raised when attempting to execute a Look-Up
    that doesn't have a prompt template configured.
    """

    pass


class ParseError(LookupError):
    """Raised when LLM response cannot be parsed.

    This exception is raised when the LLM returns a response that
    cannot be parsed as valid JSON or doesn't match expected format.
    """

    pass


class DefaultProfileError(LookupError):
    """Raised when default profile is not found for a Look-Up project.

    This exception is raised when attempting to get the default profile
    for a Look-Up project that doesn't have one configured.
    """

    pass


class ContextWindowExceededError(LookupError):
    """Raised when prompt + reference data exceeds LLM context window.

    This exception is raised when the combined size of the prompt template,
    reference data, and extracted data exceeds the configured LLM's context
    window limit.
    """

    def __init__(self, token_count: int, context_limit: int, model: str):
        """Initialize the exception.

        Args:
            token_count: Number of tokens in the prompt
            context_limit: Maximum tokens allowed by the model
            model: Name of the LLM model
        """
        self.token_count = token_count
        self.context_limit = context_limit
        self.model = model
        message = (
            f"Context window exceeded: prompt requires {token_count:,} tokens "
            f"but {model} has a limit of {context_limit:,} tokens. "
            f"Reduce reference data size or use a model with larger context window."
        )
        super().__init__(message)


class RetrievalError(LookupError):
    """Raised when RAG retrieval fails.

    This exception is raised when the vector similarity search fails
    to retrieve context from indexed reference data.
    """

    pass
