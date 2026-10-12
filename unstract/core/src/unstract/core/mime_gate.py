"""Shared rules for deciding whether a file may enter a workflow.

Lives here because the backend and the workers must answer the same question
identically. Keep in sync with LLMWhisperer's supported types.
"""

import re
import zipfile

import magic

# libmagic reports these when it recognises a wrapper but not its contents, so
# they are never a verdict on their own.
INCONCLUSIVE_MIME_TYPES = frozenset(
    {"application/octet-stream", "application/zip", "application/x-ole-storage"}
)

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
            # A real package carries its relationships too. Without them the
            # archive is not loadable, so naming it an Office document here only
            # moves the failure to extraction.
            if {"[Content_Types].xml", "_rels/.rels"} <= set(names):
                for prefix, mime_type in OOXML_DIRECTORY_TYPES:
                    if any(name.startswith(prefix) for name in names):
                        return mime_type
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
    if mime_type == "application/zip":
        return mime_type
    match = PDF_HEADER_PATTERN.search(head[:PDF_HEADER_SCAN_BYTES])
    if match is None:
        return mime_type
    # Classified from the header's own offset rather than trusted as a substring.
    return magic.from_buffer(head[match.start() :], mime=True)
