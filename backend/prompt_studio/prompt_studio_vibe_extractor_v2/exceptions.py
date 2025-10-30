"""Exceptions for Vibe Extractor."""


class VibeExtractorError(Exception):
    """Base exception for Vibe Extractor errors."""

    pass


class ProjectNotFoundError(VibeExtractorError):
    """Raised when a project is not found."""

    pass


class GenerationError(VibeExtractorError):
    """Raised when generation fails."""

    pass


class FileReadError(VibeExtractorError):
    """Raised when reading a generated file fails."""

    pass


class InvalidDocumentTypeError(VibeExtractorError):
    """Raised when document type is invalid."""

    pass
