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
    """Remove overlapping citations, keeping the one with higher confidence.

    When two citations overlap, the one with higher ``confidence`` wins.
    On ties, the longer span wins.  On further ties, the first one wins.
    """
    if not citations:
        return []

    # Sort by start, then by length descending
    sorted_cits = sorted(citations, key=lambda c: (c.span.start, -(c.span.end - c.span.start)))

    result: list[Citation] = []
    last_end = -1

    for cit in sorted_cits:
        if cit.span.start >= last_end:
            result.append(cit)
            last_end = cit.span.end
        else:
            # Overlap: check if this citation should replace the last one
            prev = result[-1]
            if cit.confidence > prev.confidence:
                result[-1] = cit
                last_end = cit.span.end

    return result
