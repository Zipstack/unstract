"""Dataclasses for the key-value extractor.

ExecutionResult is intentionally NOT defined here — code execution reuses the
imported src/core code_executor's result type (see spec §4, §10).
"""
from dataclasses import dataclass, field
from typing import List


@dataclass
class KeySpec:
    """One compiled leaf key from the user's nested key schema."""
    path: str                                    # dotted path, e.g. "vendor.address.city"
    effective_description: str                   # breadcrumb + leaf description
    format: str = "string"                       # kind: string|number|date|currency|enum|regex|<freetext>
    enum_values: List[str] = field(default_factory=list)   # set when format == "enum"
    regex_pattern: str = ""                                 # set when format == "regex"
    required: bool = False
    aliases: List[str] = field(default_factory=list)
    multivalued: bool = False                    # value is a comma-separated string


@dataclass
class ArraySpec:
    """One compiled FLAT-array node (P8a). `path` = dotted array location (e.g. 'line_items',
    'invoice.lines'). `item_specs` = the declared columns as row-LOCAL scalar KeySpecs (their
    `path` is the bare column name). `key_column` (optional) is a column used for row identity in
    scoring; '' = positional. Nested arrays inside an item are P8b and rejected at compile."""
    path: str
    description: str = ""
    item_specs: List[KeySpec] = field(default_factory=list)
    key_column: str = ""
    required: bool = False
