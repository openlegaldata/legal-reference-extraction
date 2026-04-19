"""Short-form citation resolution (Stream I).

Post-pass that walks citations in document order and resolves:
- Short-form law refs: bare ``§ 5`` inherits book from prior full citation
- ``a.a.O.`` / ``ebenda`` / ``ebd.``: resolves to nearest prior citation
- ``vgl.`` connectors: emitted as CitationRelation, not a new citation

The resolver creates new frozen dataclass instances with ``resolves_to``
set, since citations are immutable.
"""

from __future__ import annotations

import re

from refex.citations import (
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


# --- Relation detection (I2) ---

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
