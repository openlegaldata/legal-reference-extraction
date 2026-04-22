"""Short-form citation resolution (Stream I).

Post-pass that walks citations in document order and resolves:
- Short-form law citations: bare ``§ 5`` inherits book from prior full citation
- ``a.a.O.`` / ``ebenda`` / ``ebd.``: resolves to nearest prior citation
- ``vgl.`` connectors: emitted as CitationRelation, not a new citation

The resolver creates new frozen dataclass instances with ``resolves_to``
set, since citations are immutable.
"""

from __future__ import annotations

import re

from refex.citations import (
    CaseCitation,
    Citation,
    CitationRelation,
    LawCitation,
    Span,
)


def resolve_short_forms(
    citations: list[Citation],
    text: str,
) -> tuple[list[Citation], list[CitationRelation]]:
    """Resolve short-form citations and detect inter-citation relations.

    Args:
        citations: Sorted by span.start.
        text: The document plain text (for scanning inter-citation text).

    Returns:
        Updated citation list and new relations.
    """
    resolved = _resolve_law_short_forms(citations)
    resolved = _resolve_case_short_forms(resolved)
    relations = _detect_relations(resolved, text)
    return resolved, relations


def _resolve_law_short_forms(citations: list[Citation]) -> list[Citation]:
    """Resolve short-form law citations by inheriting book from prior context."""
    result: list[Citation] = []
    last_law_book: str | None = None
    last_law_id: str | None = None

    for cit in citations:
        if isinstance(cit, LawCitation):
            if cit.book:
                # Full citation: update context
                last_law_book = cit.book
                last_law_id = cit.id
                result.append(cit)
            elif last_law_book and not cit.book:
                # Short-form: inherit book from prior context
                resolved = LawCitation(
                    span=cit.span,
                    id=cit.id,
                    kind="short",
                    confidence=cit.confidence,
                    source=cit.source,
                    unit=cit.unit,
                    delimiter=cit.delimiter,
                    book=last_law_book,
                    number=cit.number,
                    structure=cit.structure,
                    range_end=cit.range_end,
                    range_extensions=cit.range_extensions,
                    resolves_to=last_law_id,
                )
                result.append(resolved)
            else:
                result.append(cit)
        else:
            result.append(cit)

    return result


def _resolve_case_short_forms(citations: list[Citation]) -> list[Citation]:
    """Resolve case short-forms: reporter citations following a full case citation.

    A reporter citation like "BGHZ 154, 239" that follows a full case citation
    with a matching court is linked via ``resolves_to``.  The reporter citation
    is marked as ``kind="short"`` since it refers back to the same decision.
    """
    result: list[Citation] = []
    # Track the last full case citation (one with court + file_number)
    last_full_case_id: str | None = None
    last_full_case_court: str | None = None

    # Map reporter abbreviations to courts
    _REPORTER_COURT_MAP = {
        "BGHZ": "BGH",
        "BGHSt": "BGH",
        "BGHR": "BGH",
        "BVerfGE": "BVerfG",
        "BVerwGE": "BVerwG",
        "BAGE": "BAG",
        "BSGE": "BSG",
        "BFHE": "BFH",
        "BPatGE": "BPatG",
        "RGZ": "RG",
        "RGSt": "RG",
    }

    for cit in citations:
        if not isinstance(cit, CaseCitation):
            result.append(cit)
            continue

        if cit.court and cit.file_number and not cit.reporter:
            # Full case citation with court + file number
            last_full_case_id = cit.id
            last_full_case_court = cit.court
            result.append(cit)
        elif cit.reporter and not cit.court and last_full_case_id:
            # Reporter citation without explicit court — check if it matches prior court
            expected_court = _REPORTER_COURT_MAP.get(cit.reporter)
            if expected_court and last_full_case_court and expected_court in last_full_case_court:
                # Short-form: link to prior full citation
                resolved = CaseCitation(
                    span=cit.span,
                    id=cit.id,
                    kind="short",
                    confidence=cit.confidence,
                    source=cit.source,
                    court=expected_court,
                    file_number=cit.file_number,
                    date=cit.date,
                    ecli=cit.ecli,
                    decision_type=cit.decision_type,
                    reporter=cit.reporter,
                    reporter_volume=cit.reporter_volume,
                    reporter_page=cit.reporter_page,
                )
                result.append(resolved)
            else:
                result.append(cit)
        else:
            result.append(cit)

    return result


_RELATION_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("ivm", re.compile(r"i\.?\s*V\.?\s*m\.?|in\s+Verbindung\s+mit", re.IGNORECASE)),
    ("vgl", re.compile(r"vgl\.?")),
    ("aao", re.compile(r"a\.?\s*a\.?\s*O\.?")),
    ("ebenda", re.compile(r"ebd\.?|ebenda", re.IGNORECASE)),
    ("siehe", re.compile(r"siehe\s+dort")),
]


def _detect_relations(
    citations: list[Citation],
    text: str,
) -> list[CitationRelation]:
    """Detect relations from inter-citation text (i.V.m., vgl., etc.)."""
    relations: list[CitationRelation] = []

    for i in range(len(citations) - 1):
        curr = citations[i]
        nxt = citations[i + 1]

        gap_start = curr.span.end
        gap_end = nxt.span.start

        if gap_start >= gap_end:
            continue

        gap_text = text[gap_start:gap_end]

        for rel_type, pattern in _RELATION_PATTERNS:
            m = pattern.search(gap_text)
            if m:
                abs_start = gap_start + m.start()
                abs_end = gap_start + m.end()
                relations.append(
                    CitationRelation(
                        source_id=curr.id,
                        target_id=nxt.id,
                        relation=rel_type,
                        span=Span(start=abs_start, end=abs_end, text=text[abs_start:abs_end]),
                    )
                )
                break

    return relations
