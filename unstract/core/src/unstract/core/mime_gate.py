"""Shared rules for deciding whether a file may enter a workflow.

The backend and the workers both gate uploads and connector files on the same
question, and they have to answer it identically: a file one accepts and the
other rejects is a bug either way. The allow-list itself still lives as an enum
in each package, but the logic that interprets libmagic's answer lives here so
the two cannot drift.

The set mirrors LLMWhisperer's own gate (`Util.is_valid_file_type_from_path` in
unstract-llm-whisperer). Accepting what it cannot read only defers the failure
to extraction; rejecting what it can read loses a file that would have worked.
"""

import re
import zipfile

import magic

# libmagic yields these when it recognises a wrapper but not the content, so
# they are never a verdict on their own. `octet-stream` belongs here as much as
# the named wrappers: measured on libmagic 5.46, `from_buffer` never returns
# `application/zip` at any sample size - a zip container reads as octet-stream
# from a buffer, and only `from_file` names it.
INCONCLUSIVE_MIME_TYPES = frozenset(
    {"application/octet-stream", "application/zip", "application/x-ole-storage"}
)

# libmagic's PDF rule only matches at offset 0, but extractors tolerate leading
# bytes before the header, so a stream-wrapped PDF sniffs as octet-stream. Eight
# bytes of padding is enough to trigger it. LLMWhisperer scans this same window
# for the same reason.
PDF_HEADER_SCAN_BYTES = 1024

# `%PDF-` alone appears in plenty of content that is not a PDF; a real header
# carries a version, so require one before promoting anything on its strength.
PDF_HEADER_PATTERN = re.compile(rb"%PDF-\d\.\d")

# An ODF `mimetype` member holds one media type string and nothing else, so
# anything larger is not the thing we are looking for. Bounding the read keeps a
# hostile archive from turning a type check into a decompression bomb.
MIMETYPE_MEMBER_LIMIT = 256

# What a zip-based document keeps inside itself. libmagic's own msooxml rule
# looks for these; reading them back is how a repackaged .docx - whose first
# member is not [Content_Types].xml, so libmagic only ever calls it a zip - is
# recognised without taking on an ML classifier for the job.
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


def identify_zip_container(path: str, is_allowed) -> str | None:
    """Name the document inside a zip, or None if it is just a zip.

    Returns only types `is_allowed` already accepts, so this can widen what is
    recognised but never what is permitted.
    """
    try:
        with zipfile.ZipFile(path) as archive:
            names = archive.namelist()
            if "mimetype" in names:
                # ODF stores its type verbatim in a member of that name. Check the
                # declared size and read a bounded amount: this archive is an
                # unvalidated upload, and read() would otherwise decompress
                # whatever a zip bomb declares straight into memory, failing the
                # whole request before anything is dispatched.
                info = archive.getinfo("mimetype")
                if info.file_size <= MIMETYPE_MEMBER_LIMIT:
                    with archive.open("mimetype") as member:
                        raw = member.read(MIMETYPE_MEMBER_LIMIT)
                    declared = raw.decode("ascii", "ignore").strip()
                    if is_allowed(declared):
                        return declared
            if "[Content_Types].xml" in names:
                for prefix, mime_type in OOXML_DIRECTORY_TYPES:
                    if any(name.startswith(prefix) for name in names):
                        return mime_type
    except (zipfile.BadZipFile, OSError, KeyError, ValueError):
        return None
    return None


def resolve_inconclusive_mime_type(mime_type: str, head: bytes) -> str:
    """Give a wrapper-only classification a second chance from the leading bytes.

    LLMWhisperer resolves these with Magika and then a `%PDF-` scan; without
    Magika this covers the PDF case, which is the one that reaches us.

    Deliberately stricter than that scan in two ways, because this promotes a
    file *into* the allow-list: a recognised zip is left alone however its
    entries happen to read, and the marker is re-classified from its own offset
    rather than trusted as a substring, so a stray "%PDF-" sitting inside other
    content cannot smuggle a file through the gate.
    """
    if mime_type not in INCONCLUSIVE_MIME_TYPES:
        return mime_type
    if mime_type == "application/zip":
        return mime_type
    match = PDF_HEADER_PATTERN.search(head[:PDF_HEADER_SCAN_BYTES])
    if match is None:
        return mime_type
    # Re-classify from the header's own offset. libmagic's PDF rule is just the
    # magic bytes, so this alone would still accept a stray "%PDF-" - the version
    # pattern above is what makes the marker evidence rather than a coincidence.
    return magic.from_buffer(head[match.start() :], mime=True)
