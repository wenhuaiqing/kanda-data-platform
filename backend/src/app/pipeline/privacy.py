"""Free-text scanning and masking.

Visit notes are typed by support workers on a phone and may contain anything:
a family member's number, an NDIS number copied from a form, a client's full
name. They are masked before they leave the landing zone, so no governed
table, report, query or model ever receives what the masking catches.

Pattern masking is a floor, not a guarantee - it is named as a risk on the
Privacy page, with what would replace it (a classifier, and a review of
what it missed).
"""

from __future__ import annotations

import re

PHONE = re.compile(r"\(0\d\)\s?\d{4}\s?\d{4}|\b04\d{2}\s?\d{3}\s?\d{3}\b")
NDIS = re.compile(r"\b\d{9}\b")


def name_pattern(names: set[str]) -> re.Pattern | None:
    words = sorted({n for n in names if len(n) >= 3}, key=len, reverse=True)
    if not words:
        return None
    return re.compile(r"\b(" + "|".join(re.escape(w) for w in words) + r")\b", re.I)


def mask(text: str, names: re.Pattern | None) -> tuple[str, list[str]]:
    """Return the masked text and what was found (phone, ndis_number, name)."""
    if not text:
        return text, []
    found: list[str] = []
    out, n = PHONE.subn("[phone]", text)
    if n:
        found.append("phone")
    out, n = NDIS.subn("[ndis number]", out)
    if n:
        found.append("ndis_number")
    if names is not None:
        out, n = names.subn("[name]", out)
        if n:
            found.append("name")
    return out, found


def contains_pii(text: str, names: re.Pattern | None) -> bool:
    return bool(text) and bool(PHONE.search(text) or NDIS.search(text) or (names is not None and names.search(text)))
