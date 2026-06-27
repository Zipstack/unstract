"""Shared helpers for surfacing LLMWhisperer signature page highlights.

The workers executor and the prompt-service answer-prompt service both
need to post-process LLM answers against the signature metadata that
LLMWhisperer V2's ``document_insights`` mode produces. This module owns
the matching logic so both services stay in lock-step without copy-paste
drift.
"""

from __future__ import annotations

import re
from typing import Any

# Generic signature-related terms used as a fallback trigger when the
# LLM answer doesn't mention any specific signer name but does talk
# about signing in general (e.g. "Is this signed?" → "Yes, the document
# is signed."). Matched as case-insensitive substrings.
SIGNATURE_KEYWORDS: tuple[str, ...] = (
    "signature",
    "signed",
    "signatory",
    "signatories",
    "signing",
    "executed",
)


def _build_page_coords(
    signature_page_references: dict[str, Any],
) -> dict[str, list[int]]:
    """Pick the resolved coords array per signature page.

    Entries without a four-element ``coords`` list are skipped.
    """
    page_coords: dict[str, list[int]] = {}
    for page_str, ref in signature_page_references.items():
        if not isinstance(ref, dict):
            continue
        coords = ref.get("coords")
        if isinstance(coords, list) and len(coords) >= 4:
            page_coords[page_str] = list(coords[:4])
    return page_coords


def _any_signer_matches(signatures: list[Any], answer: str) -> bool:
    """Return True if any signer name in ``signatures`` appears in ``answer``.

    Each name is matched as a whole token/phrase (case-insensitive,
    word-boundary anchored) to avoid signer initials like ``"P S"``
    matching the gap between ``"Pradeep"`` and ``"Surukanti"`` inside
    ``"Pradeep Surukanti"``.
    """
    for sig in signatures:
        if not isinstance(sig, dict):
            continue
        name = (sig.get("name") or "").strip()
        if not name:
            continue
        pattern = re.compile(r"\b" + re.escape(name) + r"\b", re.IGNORECASE)
        if pattern.search(answer):
            return True
    return False


def _find_pages_matching_signers(
    answer: str,
    signature_metadata: dict[str, list[Any]],
    eligible_pages: set[str],
) -> list[str]:
    """Return the pages whose signer names appear in ``answer``."""
    return [
        page_str
        for page_str, signatures in signature_metadata.items()
        if page_str in eligible_pages
        and signatures
        and _any_signer_matches(signatures, answer)
    ]


def _dedupe_coords(
    matched_pages: list[str],
    page_coords: dict[str, list[int]],
) -> list[list[int]]:
    """Map matched pages to their coords, preserving order and dropping dups."""
    seen: set[tuple[int, ...]] = set()
    new_coords: list[list[int]] = []
    for page_str in matched_pages:
        coords = page_coords[page_str]
        key = tuple(coords)
        if key in seen:
            continue
        seen.add(key)
        new_coords.append(coords)
    return new_coords


def resolve_signature_highlight_coords(
    answer: str,
    signature_metadata: dict[str, list[Any]] | None,
    signature_page_references: dict[str, Any] | None,
) -> list[list[int]]:
    """Return the page coords that the LLM answer should highlight.

    Matching rules:

    - For each signer name in ``signature_metadata`` that appears as a
      whole word/phrase (case-insensitive) inside ``answer``, the
      corresponding page's coords are included.
    - When no signer name matches but the answer mentions a generic
      signature keyword (``signature``, ``signed``, ``signatory``,
      ``signing``, ``executed``), every signature page's coords are
      included as a fallback.
    - Returns an empty list when there's nothing to attach.

    Returned coords are de-duplicated by content while preserving order.
    """
    if not signature_page_references or not signature_metadata:
        return []
    if not isinstance(answer, str) or not answer.strip():
        return []

    page_coords = _build_page_coords(signature_page_references)
    if not page_coords:
        return []

    matched_pages = _find_pages_matching_signers(
        answer=answer,
        signature_metadata=signature_metadata,
        eligible_pages=set(page_coords.keys()),
    )

    if not matched_pages and any(kw in answer.lower() for kw in SIGNATURE_KEYWORDS):
        matched_pages = list(page_coords.keys())

    if not matched_pages:
        return []

    return _dedupe_coords(matched_pages, page_coords)


def format_signature_metadata_context(
    signature_metadata: dict[str, list[Any]],
) -> str:
    """Format ``signature_metadata`` as a human-readable LLM context block.

    Returns an empty string when no signatures are present. Page numbers
    are converted from 0-indexed to 1-indexed for display.
    """
    lines: list[str] = []
    for page_num, signatures in sorted(
        signature_metadata.items(), key=lambda x: int(x[0])
    ):
        if not signatures:
            continue
        for sig in signatures:
            name = sig.get("name", "Unknown")
            sig_type = sig.get("type", "signature")
            desc = sig.get("desc", "")
            page_display = int(page_num) + 1  # 0-indexed → 1-indexed
            entry = f"- Page {page_display}: {name} ({sig_type})"
            if desc:
                entry += f" — {desc}"
            lines.append(entry)
    if not lines:
        return ""
    header = (
        "\n\n[Document Signature Information]\n"
        "The following signatures were detected in this document. "
        "Use this information to answer any questions about signatories, "
        "signing parties, or document execution status.\n"
    )
    return header + "\n".join(lines)


def merge_into_highlight_data(
    metadata: dict[str, Any],
    prompt_key: str,
    new_coords: list[list[int]],
    highlight_data_key: str = "highlight_data",
) -> None:
    """Append signature coords to ``metadata[highlight_data_key][prompt_key]``.

    Skips duplicates against existing entries (e.g. those populated by
    the hex-comment highlight pipeline). Mutates ``metadata`` in place.
    """
    if not new_coords:
        return
    bucket = metadata.setdefault(highlight_data_key, {})
    existing = bucket.get(prompt_key)
    if not isinstance(existing, list):
        existing = []
    for coords in new_coords:
        if coords not in existing:
            existing.append(coords)
    bucket[prompt_key] = existing
