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

# A package declares its main part and relates it from the root. Requiring the
# two to agree, and to name a member that exists, is what separates a document
# from an archive wearing its member names. Read as bytes with bounded reads
# rather than parsed: the input is an untrusted upload, and an XML parser is far
# more attack surface than this needs.
OOXML_MEMBER_LIMIT = 65536

# The content type a package declares for its main part, and the type we report.
OOXML_MAIN_CONTENT_TYPES = {
    b"application/vnd.openxmlformats-officedocument.wordprocessingml"
    b".document.main+xml": (
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    ),
    b"application/vnd.openxmlformats-officedocument.spreadsheetml" b".sheet.main+xml": (
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    ),
    b"application/vnd.openxmlformats-officedocument.presentationml"
    b".presentation.main+xml": (
        "application/vnd.openxmlformats-officedocument.presentationml.presentation"
    ),
}

_OVERRIDE_TAG = re.compile(rb"<Override\b[^>]*>", re.IGNORECASE)
_RELATIONSHIP_TAG = re.compile(rb"<Relationship\b[^>]*>", re.IGNORECASE)
_OFFICE_DOCUMENT_REL = b"/officeDocument"


def _attribute(tag: bytes, name: bytes) -> bytes | None:
    """One attribute off an XML start tag, quoted either way, any order."""
    match = re.search(
        rb"\b" + re.escape(name) + rb"\s*=\s*[\"']([^\"']*)[\"']",
        tag,
        re.IGNORECASE,
    )
    return match.group(1).strip() if match else None


def _read_member(archive: zipfile.ZipFile, name: str) -> bytes | None:
    """A member's bytes, bounded, or None if it is absent or oversized."""
    try:
        info = archive.getinfo(name)
        if info.file_size > OOXML_MEMBER_LIMIT:
            return None
        with archive.open(info) as member:
            return member.read(OOXML_MEMBER_LIMIT)
    except (KeyError, OSError, zipfile.BadZipFile, ValueError):
        return None


def _normalise_part(part: bytes | None) -> str | None:
    return part.lstrip(b"/").decode("utf-8", "ignore") or None if part else None


def _identify_ooxml(archive: zipfile.ZipFile, names: "list[str]") -> str | None:
    """Name an OOXML package, or None if the archive only looks like one."""
    content_types = _read_member(archive, "[Content_Types].xml")
    rels = _read_member(archive, "_rels/.rels")
    if content_types is None or rels is None:
        return None

    declared_part = declared_type = None
    for tag in _OVERRIDE_TAG.findall(content_types):
        mime_type = OOXML_MAIN_CONTENT_TYPES.get(_attribute(tag, b"ContentType") or b"")
        if mime_type:
            declared_part = _normalise_part(_attribute(tag, b"PartName"))
            declared_type = mime_type
            break
    if not declared_part:
        return None

    for tag in _RELATIONSHIP_TAG.findall(rels):
        relation = _attribute(tag, b"Type") or b""
        if not relation.rstrip(b"/").endswith(_OFFICE_DOCUMENT_REL):
            continue
        # The relationship must point at the part the package declared, and that
        # part must actually be in the archive.
        if _normalise_part(_attribute(tag, b"Target")) == declared_part:
            return declared_type if declared_part in names else None
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
