"""Regex-based extraction engines (C3).

Wraps the existing ``DivideAndConquerLawRefExtractorMixin`` and
``CaseRefExtractorMixin`` to emit the new typed ``Citation`` objects.
"""

from __future__ import annotations

from refex.citations import (
    CaseCitation,
    Citation,
    CitationRelation,
    LawCitation,
    Span,
    make_citation_id,
)
from refex.extractors.case import CaseRefExtractorMixin
from refex.extractors.law import DivideAndConquerLawRefExtractorMixin
from refex.models import RefMarker, RefType


class RegexLawExtractor(DivideAndConquerLawRefExtractorMixin):
    """Law citation extractor emitting typed ``LawCitation`` objects."""

    def extract(self, text: str) -> tuple[list[Citation], list[CitationRelation]]:
        markers = self.extract_law_ref_markers(text, is_html=False)
        citations = _law_markers_to_citations(markers, unit_hint=self.get_unit_hint)
        return citations, []


class RegexCaseExtractor(CaseRefExtractorMixin):
    """Case citation extractor emitting typed ``CaseCitation`` objects."""

    def extract(self, text: str) -> tuple[list[Citation], list[CitationRelation]]:
        markers = self.extract_case_ref_markers(text)
        citations = _case_markers_to_citations(markers)
        return citations, []


def _law_markers_to_citations(
    markers: list[RefMarker],
    unit_hint: callable | None = None,
) -> list[Citation]:
    """Convert law RefMarkers to typed LawCitation objects.

    ``unit_hint`` (E2) is an optional ``(book_code) -> "article"|"paragraph"|None``
    callable.  When it returns a non-None value for a book, that unit is
    authoritative; otherwise we fall back to the marker-text prefix
    heuristic (``Art.*`` → article, else paragraph).
    """
    citations: list[Citation] = []
    for marker in markers:
        span = Span(start=marker.start, end=marker.end, text=marker.text)
        for ref in marker.get_references():
            if ref.ref_type != RefType.LAW:
                continue
            cid = make_citation_id(span, "regex")
            # Detect Art./Artikel by marker text (fallback heuristic)
            is_article = marker.text.lstrip().startswith(("Art", "art"))

            # E2: authoritative override from the data file when present.
            hint = unit_hint(ref.book) if unit_hint else None
            if hint == "article":
                is_article = True
            elif hint == "paragraph":
                is_article = False

            citations.append(
                LawCitation(
                    span=span,
                    id=cid,
                    book=ref.book if ref.book else None,
                    number=ref.section if ref.section else None,
                    unit="article" if is_article else "paragraph",
                    delimiter="Art." if is_article else "§",
                )
            )
    return citations


def _case_markers_to_citations(markers: list[RefMarker]) -> list[Citation]:
    """Convert case RefMarkers to typed CaseCitation objects."""
    citations: list[Citation] = []
    for marker in markers:
        span = Span(start=marker.start, end=marker.end, text=marker.text)
        for ref in marker.get_references():
            if ref.ref_type != RefType.CASE:
                continue
            cid = make_citation_id(span, "regex")
            citations.append(
                CaseCitation(
                    span=span,
                    id=cid,
                    court=ref.court if ref.court else None,
                    file_number=ref.file_number if ref.file_number else None,
                    date=ref.date if ref.date else None,
                )
            )
    return citations
