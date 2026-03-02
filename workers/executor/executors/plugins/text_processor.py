"""Pure-function text utilities used by the highlight-data plugin."""


def add_hex_line_numbers(text: str) -> str:
    """Add hex line numbers to extracted text for coordinate tracking.

    Each line is prefixed with ``0x<hex>: `` where ``<hex>`` is the
    zero-based line index.  The hex width auto-adjusts to the total
    number of lines.

    Args:
        text: Multi-line string to number.

    Returns:
        The same text with hex line-number prefixes.
    """
    lines = text.split("\n")
    hex_width = max(len(hex(len(lines))) - 2, 1)
    return "\n".join(
        f"0x{i:0{hex_width}X}: {line}" for i, line in enumerate(lines)
    )
