"""SQL identifier safety utilities for preventing SQL injection.

Provides validation and quoting for SQL identifiers (table names, column names,
schema names) across different database engines. Used by all database connectors
to ensure user-supplied identifiers cannot inject arbitrary SQL.

Defense-in-depth approach:
1. validate_identifier() - allowlist regex rejects SQL metacharacters
2. quote_identifier() - DB-specific quoting with proper escaping
3. safe_identifier() - validate + quote combined
"""

import re
from enum import Enum


class QuoteStyle(Enum):
    """Database-specific identifier quoting styles."""

    DOUBLE_QUOTE = "double"  # PostgreSQL, Redshift, Snowflake, Oracle
    BACKTICK = "backtick"  # MySQL, MariaDB, BigQuery
    SQUARE_BRACKET = "bracket"  # MSSQL


# Allowlist patterns for SQL identifiers.
# Permits: letters, digits, underscores, hyphens (common in table names).
# Intentionally excludes $ (Oracle/PG), # (MSSQL temp tables), and spaces
# to keep the strictest safe default. Extend if a deployment needs them.
_IDENTIFIER_PATTERN = re.compile(r"^[a-zA-Z_][a-zA-Z0-9_-]*$")


def validate_identifier(name: str, allow_dots: bool = False) -> str:
    """Validate a SQL identifier against an allowlist pattern.

    Args:
        name: The identifier to validate (table name, column name, schema name).
        allow_dots: If True, allows dot-separated qualified names
            (e.g., BigQuery's ``project.dataset.table``).

    Returns:
        The validated identifier string (unchanged).

    Raises:
        ValueError: If the identifier contains disallowed characters.
    """
    if not name or not name.strip():
        raise ValueError("SQL identifier cannot be empty")

    if allow_dots and "." in name:
        parts = name.split(".")
        for part in parts:
            validate_identifier(part, allow_dots=False)
        return name

    if not _IDENTIFIER_PATTERN.match(name):
        raise ValueError(
            f"Invalid SQL identifier: '{name}'. "
            "Only letters, digits, underscores, and hyphens are allowed. "
            "Must start with a letter or underscore."
        )
    return name


def quote_identifier(name: str, style: QuoteStyle) -> str:
    """Quote a single identifier using DB-specific quoting with escaping.

    Escapes any embedded quote characters to prevent breakout.

    Args:
        name: The identifier to quote.
        style: The quoting style for the target database.

    Returns:
        The quoted identifier string.
    """
    if style == QuoteStyle.DOUBLE_QUOTE:
        escaped = name.replace('"', '""')
        return f'"{escaped}"'
    elif style == QuoteStyle.BACKTICK:
        escaped = name.replace("`", "``")
        return f"`{escaped}`"
    elif style == QuoteStyle.SQUARE_BRACKET:
        escaped = name.replace("]", "]]")
        return f"[{escaped}]"
    else:
        raise ValueError(f"Unknown quote style: {style}")


def safe_identifier(name: str, style: QuoteStyle, allow_dots: bool = False) -> str:
    """Validate AND quote a SQL identifier.

    For dot-qualified names (e.g., ``schema.table``), splits on dots
    and validates+quotes each component separately.

    Args:
        name: The identifier to make safe.
        style: The quoting style for the target database.
        allow_dots: If True, handles dot-separated qualified names.

    Returns:
        The validated and quoted identifier string.

    Raises:
        ValueError: If any component fails validation.
    """
    if allow_dots and "." in name:
        parts = name.split(".")
        return ".".join(safe_identifier(part, style, allow_dots=False) for part in parts)
    validate_identifier(name)
    return quote_identifier(name, style)
