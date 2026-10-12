"""Shared rules for deciding whether a file may enter a workflow.

Lives here because the backend and the workers must answer the same question
identically. Keep in sync with LLMWhisperer's supported types.
"""

import re
import xml.etree.ElementTree as ElementTree
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

# A package's declaration members are small; anything larger is not one.
PACKAGE_MEMBER_LIMIT = 65536

# Those members never carry a DTD, so refusing one keeps entity expansion away
# from the parser rather than trusting the parser to be safe about it.
DTD_MARKERS = (b"<!DOCTYPE", b"<!ENTITY")

# The content type a package declares for its main part, and what we report.
OOXML_MAIN_CONTENT_TYPES = {
    "application/vnd.openxmlformats-officedocument.wordprocessingml"
    ".document.main+xml": (
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    ),
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml": (
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    ),
    "application/vnd.openxmlformats-officedocument.presentationml"
    ".presentation.main+xml": (
        "application/vnd.openxmlformats-officedocument.presentationml.presentation"
    ),
}

ODF_MIME_TYPES = frozenset(
    {
        "application/vnd.oasis.opendocument.text",
        "application/vnd.oasis.opendocument.spreadsheet",
        "application/vnd.oasis.opendocument.presentation",
    }
)

OFFICE_DOCUMENT_RELATION = "/officeDocument"


def _local_name(tag: str) -> str:
    """A tag or attribute name without its namespace."""
    return tag.rsplit("}", 1)[-1]


def _attribute(element, name: str) -> str | None:
    """An attribute by local name, whatever prefix it carries."""
    for key, value in element.attrib.items():
        if _local_name(key) == name:
            return value.strip()
    return None


def _read_member(archive: zipfile.ZipFile, name: str) -> bytes | None:
    """A declaration member's bytes, bounded, or None if unusable."""
    try:
        info = archive.getinfo(name)
        if info.file_size > PACKAGE_MEMBER_LIMIT:
            return None
        with archive.open(info) as member:
            return member.read(PACKAGE_MEMBER_LIMIT)
    except (KeyError, OSError, zipfile.BadZipFile, ValueError):
        return None


def _parse_member(archive: zipfile.ZipFile, name: str):
    """Parse a declaration member, or None if it is unusable.

    Parsed rather than pattern-matched because the archive is untrusted: a
    comment, a namespace prefix or an escaped attribute each defeat matching on
    raw bytes, and each was a way past this check.
    """
    raw = _read_member(archive, name)
    if raw is None:
        return None
    upper = raw.upper()
    if any(marker in upper for marker in DTD_MARKERS):
        return None
    try:
        return ElementTree.fromstring(raw)
    except ElementTree.ParseError:
        return None


def _normalise_part(part: str | None) -> str | None:
    return part.lstrip("/") or None if part else None


def _identify_ooxml(archive: zipfile.ZipFile, names: "list[str]") -> str | None:
    """Name an OOXML package, or None if the archive only looks like one.

    The package must declare its main part, relate that same part from the root,
    and contain it. Any of those alone is satisfied by an archive the extractor
    cannot open.
    """
    content_types = _parse_member(archive, "[Content_Types].xml")
    relationships = _parse_member(archive, "_rels/.rels")
    if content_types is None or relationships is None:
        return None

    declared_part = declared_type = None
    for element in content_types.iter():
        if _local_name(element.tag) != "Override":
            continue
        content_type = _attribute(element, "ContentType") or ""
        mime_type = OOXML_MAIN_CONTENT_TYPES.get(content_type)
        if mime_type:
            declared_part = _normalise_part(_attribute(element, "PartName"))
            declared_type = mime_type
            break
    if not declared_part or declared_part not in names:
        return None

    for element in relationships.iter():
        if _local_name(element.tag) != "Relationship":
            continue
        relation = _attribute(element, "Type") or ""
        if not relation.rstrip("/").endswith(OFFICE_DOCUMENT_RELATION):
            continue
        if _normalise_part(_attribute(element, "Target")) == declared_part:
            return declared_type
    return None


def _identify_odf(archive: zipfile.ZipFile, declared: str) -> str | None:
    """Confirm the manifest agrees with what the mimetype member claims."""
    manifest = _parse_member(archive, "META-INF/manifest.xml")
    if manifest is None:
        return None
    for element in manifest.iter():
        if _local_name(element.tag) != "file-entry":
            continue
        if (
            _attribute(element, "full-path") == "/"
            and _attribute(element, "media-type") == declared
        ):
            return declared
    return None


def identify_zip_container(path: str) -> str | None:
    """Name the document inside a zip, or None if it is just a zip.

    Only ever returns a constant from this module, never a string read out of
    the archive, so it widens what is recognised and not what is permitted.
    """
    try:
        with zipfile.ZipFile(path) as archive:
            names = archive.namelist()
            # ODF requires this member to be first and stored uncompressed, and
            # its manifest to declare the same type for the package root.
            info = archive.infolist()[0] if names else None
            if (
                info is not None
                and info.filename == "mimetype"
                and info.compress_type == zipfile.ZIP_STORED
                and info.file_size <= PACKAGE_MEMBER_LIMIT
            ):
                raw = _read_member(archive, "mimetype") or b""
                declared = raw.decode("ascii", "ignore").strip()
                if declared in ODF_MIME_TYPES:
                    return _identify_odf(archive, declared)
            if {"[Content_Types].xml", "_rels/.rels"} <= set(names):
                return _identify_ooxml(archive, names)
    except (zipfile.BadZipFile, OSError, KeyError, ValueError):
        return None
    return None


def resolve_inconclusive_mime_type(mime_type: str, head: bytes) -> str:
    """Give a wrapper-only classification a second chance from the leading bytes.

    This promotes a file into the allow-list, so it stays narrow: a recognised
    wrapper keeps its own answer, and the marker must look like a real header.
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
