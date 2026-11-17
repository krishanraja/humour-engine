"""Text identity, offsets and span resolution.

Offsets are half-open Unicode code-point offsets (Python str indices). Clients that
work in UTF-16 code units convert at the interface boundary with the helpers below.
"""

from __future__ import annotations

import hashlib
import json
import unicodedata


def sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def input_revision(payload: object) -> str:
    """Stable revision of the analysed material and context."""
    blob = json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str)
    return "rev_" + sha(blob)[:20]


def normalise_for_identity(text: str) -> str:
    """Normalisation for duplicate detection only. Never used as analysis input."""
    t = unicodedata.normalize("NFKC", text)
    t = t.replace("’", "'").replace("‘", "'").replace("“", '"').replace("”", '"')
    t = " ".join(t.split())
    t = t.strip(" \"'")
    return t.lower()


def canonical_text_id(text: str) -> str:
    return "txt_" + sha(normalise_for_identity(text))[:16]


def utf16_to_codepoint(text: str, utf16_offset: int) -> int:
    units = 0
    for i, ch in enumerate(text):
        if units >= utf16_offset:
            if units != utf16_offset:
                raise ValueError("UTF-16 offset falls inside a surrogate pair")
            return i
        units += 2 if ord(ch) > 0xFFFF else 1
    if units == utf16_offset:
        return len(text)
    raise ValueError("UTF-16 offset beyond end of text")


def codepoint_to_utf16(text: str, cp_offset: int) -> int:
    if not 0 <= cp_offset <= len(text):
        raise ValueError("code-point offset out of range")
    return sum(2 if ord(ch) > 0xFFFF else 1 for ch in text[:cp_offset])


def find_all(text: str, quote: str) -> list[int]:
    out, i = [], text.find(quote)
    while i != -1 and quote:
        out.append(i)
        i = text.find(quote, i + 1)
    return out


class SpanError(ValueError):
    pass


def resolve_span(text: str, quote: str, start: int | None = None, occurrence: int | None = None) -> tuple[int, int, str]:
    """Locate an exact quote in the original text. Returns (start, end, note).

    The quote must match the original text exactly (no normalisation). A supplied
    start must point at the quote. Ambiguous repeats without a start or occurrence
    resolve to the first occurrence and say so.
    """
    if not quote or not quote.strip():
        raise SpanError("empty quote")
    if start is not None:
        if start < 0 or start + len(quote) > len(text) or text[start : start + len(quote)] != quote:
            raise SpanError(f"quote does not occur at offset {start}")
        return start, start + len(quote), ""
    hits = find_all(text, quote)
    if not hits:
        raise SpanError("quote not found verbatim in segment")
    if occurrence is not None:
        if not 0 <= occurrence < len(hits):
            raise SpanError("occurrence index out of range")
        return hits[occurrence], hits[occurrence] + len(quote), ""
    note = "" if len(hits) == 1 else f"quote occurs {len(hits)} times; first occurrence used"
    return hits[0], hits[0] + len(quote), note
