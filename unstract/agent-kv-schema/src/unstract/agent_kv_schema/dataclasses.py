"""Dataclasses for the key-value extractor.

ExecutionResult is intentionally NOT defined here — code execution reuses the
imported src/core code_executor's result type (see spec §4, §10).
"""

from dataclasses import dataclass, field

# Both specs are FROZEN. They are compile output: produced once by
# `kv_schema._walk` and then read by the prompt generator, the QA pass and the
# constraint evaluator. Nothing assigns to a field (the one derived variant,
# `normalizers`' scalar view of a multivalued leaf, already goes through
# `dataclasses.replace`), so freezing costs nothing and makes a stray mutation
# in a later stage a loud AttributeError instead of a spec that disagrees with
# the schema the caller submitted.


@dataclass(frozen=True)
class KeySpec:
    """One compiled leaf key from the user's nested key schema."""

    path: str  # dotted path, e.g. "vendor.address.city"
    effective_description: str  # breadcrumb + leaf description
    format: str = "string"  # kind: string|number|date|currency|enum|regex|<freetext>
    enum_values: list[str] = field(default_factory=list)  # set when format == "enum"
    regex_pattern: str = ""  # set when format == "regex"
    required: bool = False
    aliases: list[str] = field(default_factory=list)
    multivalued: bool = False  # value is a comma-separated string


@dataclass(frozen=True)
class ArraySpec:
    """One compiled FLAT-array node (P8a). `path` = dotted array location (e.g. 'line_items',
    'invoice.lines'). `item_specs` = the declared columns as row-LOCAL scalar KeySpecs (their
    `path` is the bare column name). `key_column` (optional) is a column used for row identity in
    scoring; '' = positional. Nested arrays inside an item are P8b and rejected at compile.
    """

    path: str
    description: str = ""
    item_specs: list[KeySpec] = field(default_factory=list)
    key_column: str = ""
    required: bool = False
    #: Collapse rows identical in EVERY extracted cell? Declared per array as
    #: `"_dedup": false`.
    #:
    #: Defaults True, which is the pre-existing behaviour and is wanted for the
    #: corpus the extractor was built against: layout-preserving OCR repeats a
    #: label once per replicate column, producing rows identical in every cell.
    #:
    #: But it is NOT lossless, and the docstring that claimed it was has been
    #: corrected. A document that genuinely contains two identical line items
    #: comes back with one, so the row count and any calculation summing or
    #: counting the rows are wrong -- and the codegen path consumes exactly
    #: these rows. Being unable to tell two real records from one OCR artefact
    #: is a reason not to guess, so a schema author who knows their documents
    #: can say so. Default left at True rather than flipped: changing it would
    #: trade a known-wrong case for an untested one on the corpus this was
    #: built for.
    dedup_rows: bool = True
