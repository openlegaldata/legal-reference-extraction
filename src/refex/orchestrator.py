"""Extraction orchestrator (C4) — merges results from multiple engines.

This is the new top-level API.  It replaces the old ``RefExtractor``
for consumers who want typed ``Citation`` objects.  The old
``RefExtractor`` is preserved for backward compatibility and delegates
internally to this orchestrator via an adapter (C5/C6).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from refex.citations import (
    Citation,
    CitationRelation,
    ExtractionResult,
)
from refex.document import Document, make_document
from refex.engines.regex import RegexCaseExtractor, RegexLawExtractor
from refex.protocols import Extractor
from refex.resolver import resolve_short_forms

logger = logging.getLogger(__name__)


@dataclass
class CitationExtractor:
    """Orchestrator that runs multiple extraction engines and merges results.

    Usage::

        extractor = CitationExtractor()  # uses default regex engines
        result = extractor.extract("Gemäß § 433 BGB ...")
        for cit in result.citations:
            print(cit.type, cit.span.text)
    """

    engines: list[Extractor] = field(
        default_factory=lambda: [
            RegexLawExtractor(),
            RegexCaseExtractor(),
        ]
    )

    def extract(self, content: str | Document, **kwargs) -> ExtractionResult:
        """Extract citations from text or a Document.

        Args:
            content: Plain text string, or a ``Document`` object.
                     Strings are auto-wrapped via ``make_document()``.
            **kwargs: Passed to ``make_document()`` when *content* is a string
                      (e.g. ``format="html"``, ``source_profile="oldp-html"``).
        """
        if isinstance(content, str):
            doc = make_document(content, **kwargs)
        else:
            doc = content

        text = doc.text

        all_citations: list[Citation] = []
        all_relations: list[CitationRelation] = []

        for engine in self.engines:
            citations, relations = engine.extract(text)
            all_citations.extend(citations)
            all_relations.extend(relations)

        merged = _resolve_overlaps(all_citations)

        # Post-pass: resolve short-form citations and detect relations
        resolved, new_relations = resolve_short_forms(merged, text)
        all_relations.extend(new_relations)

        return ExtractionResult(citations=resolved, relations=all_relations)


def _resolve_overlaps(citations: list[Citation]) -> list[Citation]:
    """Remove *proper* overlapping citations, keeping the higher-confidence one.

    Two citations with **identical** spans are treated as co-located rather
    than overlapping: enumeration markers like "§§ 500a, 500b BGB" emit one
    LawCitation per section, all sharing the same marker span, and both
    must survive. Only spans that partially overlap (different start/end)
    trigger dedupe; in that case higher ``confidence`` wins, ties broken
    by longer span, then by first occurrence.
    """
    if not citations:
        return []

    # Sort by start, then by length descending
    sorted_cits = sorted(citations, key=lambda c: (c.span.start, -(c.span.end - c.span.start)))

    result: list[Citation] = []
    last_end = -1
    last_start = -1

    for cit in sorted_cits:
        if cit.span.start >= last_end:
            # No overlap with the previous accepted citation.
            result.append(cit)
            last_start = cit.span.start
            last_end = cit.span.end
        elif cit.span.start == last_start and cit.span.end == last_end:
            # Identical span — co-located citation from the same marker
            # (e.g. enumeration "§§ 3, 4 BGB" yields one cite per section).
            result.append(cit)
        else:
            # Proper overlap: keep the higher-confidence citation.
            prev = result[-1]
            if cit.confidence > prev.confidence:
                result[-1] = cit
                last_start = cit.span.start
                last_end = cit.span.end

    return result
