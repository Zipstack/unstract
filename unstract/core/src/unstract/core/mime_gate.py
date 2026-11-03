"""Shared rules for deciding whether a file may enter a workflow.

Lives here because the backend and the workers must answer the same question
identically. A file LLMWhisperer would accept must not be rejected here, so
`classify_file_path` copies its gate (`Util.is_valid_file_type_from_path` in
unstract-llm-whisperer) step by step; change both together.
"""

import shutil
import tempfile
import xml.etree.ElementTree as ElementTree
import zipfile
from collections.abc import Iterator
from contextlib import contextmanager
from functools import partial
from itertools import chain
from typing import BinaryIO

import magic

# libmagic reports these when a prefix is not enough to name the file, so a
# prefix answer of one of them is never a verdict.
INCONCLUSIVE_MIME_TYPES = frozenset(
    {"application/zip", "application/x-ole-storage", "application/octet-stream"}
)

# LLMWhisperer asks Magika about these two. Magika is not a dependency here, so
# the zip reader below stands in for it; LLMWhisperer can still name some files
# this cannot, but never the other way round.
SECOND_OPINION_MIME_TYPES = frozenset({"application/octet-stream", "application/zip"})

# LLMWhisperer's last resort for stream-wrapped PDFs, copied as is: any `%PDF-`
# in the first 1024 bytes makes the file a PDF.
PDF_MARKER = b"%PDF-"
PDF_MARKER_SCAN_BYTES = 1024
PDF_MIME_TYPE = "application/pdf"

# A package's declaration members are small; anything larger is not one.
PACKAGE_MEMBER_LIMIT = 65536

# Those members never carry a DTD, so refusing one keeps entity expansion away
# from the parser rather than trusting the parser to be safe about it.
DTD_MARKERS = ("<!DOCTYPE", "<!ENTITY")

# The parser detects the document's encoding, so the check has to look past the
# raw bytes: a DTD written in UTF-16 is invisible to an ASCII search but is
# still expanded once parsing starts.
DTD_SEARCH_ENCODINGS = (
    "utf-8",
    "utf-16",
    "utf-16-be",
    "utf-16-le",
    "utf-32-be",
    "utf-32-le",
)

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


def _declares_dtd(raw: bytes) -> bool:
    """Whether these bytes carry a DTD under any encoding the parser accepts."""
    for encoding in DTD_SEARCH_ENCODINGS:
        text = raw.decode(encoding, "ignore").upper()
        if any(marker in text for marker in DTD_MARKERS):
            return True
    return False


def _parse_member(archive: zipfile.ZipFile, name: str):
    """Parse a declaration member, or None if it is unusable.

    Parsed rather than pattern-matched because the archive is untrusted: a
    comment, a namespace prefix or an escaped attribute each defeat matching on
    raw bytes, and each was a way past this check.
    """
    raw = _read_member(archive, name)
    if raw is None or _declares_dtd(raw):
        return None
    try:
        return ElementTree.fromstring(raw)
    except ElementTree.ParseError:
        return None


def _normalise_part(part: str | None) -> str | None:
    return part.lstrip("/") or None if part else None


def _declared_main_part(content_types) -> "tuple[str, str] | None":
    """The part a package declares as its main one, and the type that implies."""
    for element in content_types.iter():
        if _local_name(element.tag) != "Override":
            continue
        mime_type = OOXML_MAIN_CONTENT_TYPES.get(_attribute(element, "ContentType") or "")
        if not mime_type:
            continue
        part = _normalise_part(_attribute(element, "PartName"))
        return (part, mime_type) if part else None
    return None


def _relates_main_part(relationships, part: str) -> bool:
    """Whether the package root relates `part` as its office document."""
    for element in relationships.iter():
        if _local_name(element.tag) != "Relationship":
            continue
        relation = _attribute(element, "Type") or ""
        if not relation.rstrip("/").endswith(OFFICE_DOCUMENT_RELATION):
            continue
        if _normalise_part(_attribute(element, "Target")) == part:
            return True
    return False


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

    declared = _declared_main_part(content_types)
    if declared is None:
        return None
    part, mime_type = declared
    if part not in names:
        return None
    return mime_type if _relates_main_part(relationships, part) else None


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


def classify_file_path(path: str) -> str:
    """Classify a file the way LLMWhisperer's upload gate does."""
    mime_type = magic.from_file(path, mime=True)
    if mime_type in SECOND_OPINION_MIME_TYPES:
        mime_type = identify_zip_container(path) or mime_type
    if mime_type in SECOND_OPINION_MIME_TYPES:
        with open(path, "rb") as file:
            if PDF_MARKER in file.read(PDF_MARKER_SCAN_BYTES):
                return PDF_MIME_TYPE
    return mime_type


@contextmanager
def classify_stream(
    stream: BinaryIO, chunk_size: int
) -> Iterator[tuple[str | None, Iterator[bytes]]]:
    """Classify a stream, then hand back its bytes to be copied.

    The first chunk decides when libmagic can name it. Otherwise the stream is
    spilled to a local file and classified whole, because libmagic resolves
    zip and OLE2 containers from the end of the file and names a zip container
    only from a path. An empty stream yields no type.
    """
    head = stream.read(chunk_size)
    if not head:
        yield None, iter(())
        return

    mime_type = magic.from_buffer(head, mime=True)
    if mime_type not in INCONCLUSIVE_MIME_TYPES:
        yield mime_type, chain([head], iter(partial(stream.read, chunk_size), b""))
        return

    with tempfile.NamedTemporaryFile(suffix=".sniff") as spill:
        spill.write(head)
        shutil.copyfileobj(stream, spill, chunk_size)
        spill.flush()
        mime_type = classify_file_path(spill.name)
        spill.seek(0)
        yield mime_type, iter(partial(spill.read, chunk_size), b"")
