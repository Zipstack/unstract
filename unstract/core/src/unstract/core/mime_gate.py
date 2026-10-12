"""Shared rules for deciding whether a file may enter a workflow.

Lives here because the backend and the workers must answer the same question
identically. Keep in sync with LLMWhisperer's supported types.
"""

import re
import zipfile

import magic

# libmagic reports these when it recognises a wrapper but not its contents, so
# they are never a verdict on their own.
RECOGNISED_WRAPPERS = frozenset({"application/zip", "application/x-ole-storage"})
INCONCLUSIVE_MIME_TYPES = RECOGNISED_WRAPPERS | {"application/octet-stream"}

# libmagic matches the PDF header only at offset 0, while extractors tolerate
# bytes before it, so a wrapped PDF needs the header looked for.
PDF_HEADER_SCAN_BYTES = 1024

# `%PDF-` alone appears in plenty of content that is not a PDF; a real header
# carries a version, so require one before promoting anything on its strength.
PDF_HEADER_PATTERN = re.compile(rb"%PDF-\d\.\d")

# The member holds one media type string; bounding the read keeps a hostile
# archive from expanding through this check.
MIMETYPE_MEMBER_LIMIT = 256

# The member is archive-controlled, so it may identify which ODF document this
# is but never nominate some other format.
ODF_MIME_TYPES = frozenset(
    {
        "application/vnd.oasis.opendocument.text",
        "application/vnd.oasis.opendocument.spreadsheet",
        "application/vnd.oasis.opendocument.presentation",
    }
)

# Marker directories that identify a zip-based document when libmagic will only
# call it a zip.
OOXML_DIRECTORY_TYPES = (
    (
        "word/",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ),
    ("xl/", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"),
    (
        "ppt/",
        "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    ),
)

# A package declares its main part's content type, so requiring that declaration
# tells a real document from an archive that merely carries the right member
# names — which the extractor cannot open. Matched as bytes rather than parsed:
# this is an untrusted upload, and an XML parser is a larger attack surface than
# the check is worth.
OOXML_CONTENT_TYPES_LIMIT = 65536
OOXML_MAIN_PART_MARKER = b"main+xml"


def _identify_ooxml(archive: zipfile.ZipFile, names: "list[str]") -> str | None:
    """Name an OOXML package, or None if the archive only looks like one."""
    try:
        info = archive.getinfo("[Content_Types].xml")
        if info.file_size > OOXML_CONTENT_TYPES_LIMIT:
            return None
        with archive.open(info) as member:
            declared = member.read(OOXML_CONTENT_TYPES_LIMIT)
    except (KeyError, OSError, zipfile.BadZipFile, ValueError):
        return None

    # Member names say which format this claims to be; the declaration is what
    # makes the claim credible.
    if OOXML_MAIN_PART_MARKER not in declared:
        return None
    for prefix, mime_type in OOXML_DIRECTORY_TYPES:
        if any(name.startswith(prefix) for name in names):
            return mime_type
    return None


def identify_zip_container(path: str) -> str | None:
    """Name the document inside a zip, or None if it is just a zip.

    Only ever returns a constant from this module, never a string read out of
    the archive, so it widens what is recognised and not what is permitted.
    """
    try:
        with zipfile.ZipFile(path) as archive:
            names = archive.namelist()
            # ODF requires this member to be first and stored uncompressed, so
            # holding it to those conditions is what makes it evidence.
            info = archive.infolist()[0] if names else None
            if (
                info is not None
                and info.filename == "mimetype"
                and info.compress_type == zipfile.ZIP_STORED
                and info.file_size <= MIMETYPE_MEMBER_LIMIT
            ):
                with archive.open(info) as member:
                    raw = member.read(MIMETYPE_MEMBER_LIMIT)
                declared = raw.decode("ascii", "ignore").strip()
                if declared in ODF_MIME_TYPES:
                    return declared
            # Relationships and a declared main part, or the archive only looks
            # like a document and naming it one moves the failure to extraction.
            if {"[Content_Types].xml", "_rels/.rels"} <= set(names):
                return _identify_ooxml(archive, names)
    except (zipfile.BadZipFile, OSError, KeyError, ValueError):
        return None
    return None


def resolve_inconclusive_mime_type(mime_type: str, head: bytes) -> str:
    """Give a wrapper-only classification a second chance from the leading bytes.

    This promotes a file into the allow-list, so it stays narrow: a recognised
    zip is left alone, and the marker must look like a real header.
    """
    if mime_type not in INCONCLUSIVE_MIME_TYPES:
        return mime_type
    # A wrapper libmagic positively identified keeps its own answer; only bytes
    # it could not name at all are open to being read this way.
    if mime_type in RECOGNISED_WRAPPERS:
        return mime_type
    match = PDF_HEADER_PATTERN.search(head[:PDF_HEADER_SCAN_BYTES])
    if match is None:
        return mime_type
    # Classified from the header's own offset rather than trusted as a substring.
    return magic.from_buffer(head[match.start() :], mime=True)
