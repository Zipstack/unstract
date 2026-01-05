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
