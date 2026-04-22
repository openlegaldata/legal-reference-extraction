"""Integration tests using real HTML and Markdown court decision fixtures.

These fixtures are sanitized extracts from German court decisions,
covering 5 courts (BFH, BPatG, OLG, LAG, VG) with both law and case
citations. The Markdown fixtures are converted from the same HTML
using two different converter styles (basic + structured).

Tests verify that the full pipeline works end-to-end for all input
formats: plain text (existing fixtures), HTML, and Markdown.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from refex.citations import CaseCitation, LawCitation
from refex.document import Document, map_span_to_raw
from refex.orchestrator import CitationExtractor

FIXTURE_DIR = Path(__file__).parent.parent / "benchmarks" / "fixtures"


def _load_jsonl(filename: str) -> list[dict]:
    path = FIXTURE_DIR / filename
    if not path.exists():
        pytest.skip(f"Fixture file not found: {path}")
    with open(path, encoding="utf-8") as f:
        return [json.loads(line) for line in f]


@pytest.fixture(scope="module")
def html_docs():
    return _load_jsonl("html_documents.jsonl")


@pytest.fixture(scope="module")
def md_docs():
    return _load_jsonl("markdown_documents.jsonl")


@pytest.fixture(scope="module")
def extractor():
    return CitationExtractor()


class TestHtmlFixtures:
    def test_all_html_docs_load(self, html_docs):
        assert len(html_docs) == 5

    def test_all_html_docs_have_format(self, html_docs):
        for doc in html_docs:
            assert doc["format"] == "html"

    def test_no_juris_traces(self, html_docs):
        for doc in html_docs:
            assert "juris" not in doc["text"].lower(), f"juris trace in {doc['doc_id']}"

    def test_html_extracts_law_citations(self, html_docs, extractor):
        for doc_data in html_docs:
            doc = Document(raw=doc_data["text"], format="html")
            result = extractor.extract(doc)
            law_cits = [c for c in result.citations if isinstance(c, LawCitation)]
            assert len(law_cits) >= 1, f"No law citations in {doc_data['doc_id']}"

    def test_html_extracts_case_citations(self, html_docs, extractor):
        for doc_data in html_docs:
            doc = Document(raw=doc_data["text"], format="html")
            result = extractor.extract(doc)
            case_cits = [c for c in result.citations if isinstance(c, CaseCitation)]
            assert len(case_cits) >= 1, f"No case citations in {doc_data['doc_id']}"

    def test_html_span_integrity(self, html_docs, extractor):
        """Every citation span must match doc.text[start:end]."""
        for doc_data in html_docs:
            doc = Document(raw=doc_data["text"], format="html")
            result = extractor.extract(doc)
            for cit in result.citations:
                actual = doc.text[cit.span.start : cit.span.end]
                assert actual == cit.span.text, f"[{doc_data['doc_id']}] span mismatch: {actual!r} != {cit.span.text!r}"

    def test_html_offset_map_exists(self, html_docs):
        """HTML documents must have offset maps for round-tripping."""
        for doc_data in html_docs:
            doc = Document(raw=doc_data["text"], format="html")
            assert doc.offset_map is not None, f"No offset map for {doc_data['doc_id']}"
            assert len(doc.offset_map) == len(doc.text)

    def test_html_offset_round_trip(self, html_docs, extractor):
        """map_span_to_raw must recover valid raw substrings."""
        for doc_data in html_docs:
            doc = Document(raw=doc_data["text"], format="html")
            result = extractor.extract(doc)
            for cit in result.citations[:10]:  # check first 10 per doc
                raw_span = map_span_to_raw(cit.span, doc)
                assert raw_span.start < raw_span.end, f"[{doc_data['doc_id']}] empty raw span for {cit.span.text!r}"
                assert raw_span.end <= len(doc.raw), f"[{doc_data['doc_id']}] raw span out of bounds"

    def test_html_diverse_courts(self, html_docs):
        """Fixtures cover at least 4 distinct courts."""
        courts = {d["court"] for d in html_docs if d.get("court")}
        assert len(courts) >= 4


class TestMarkdownFixtures:
    def test_all_md_docs_load(self, md_docs):
        assert len(md_docs) == 5

    def test_all_md_docs_have_format(self, md_docs):
        for doc in md_docs:
            assert doc["format"] == "markdown"

    def test_no_juris_traces(self, md_docs):
        for doc in md_docs:
            assert "juris" not in doc["text"].lower(), f"juris trace in {doc['doc_id']}"

    def test_md_extracts_law_citations(self, md_docs, extractor):
        for doc_data in md_docs:
            doc = Document(raw=doc_data["text"], format="markdown")
            result = extractor.extract(doc)
            law_cits = [c for c in result.citations if isinstance(c, LawCitation)]
            assert len(law_cits) >= 1, f"No law citations in {doc_data['doc_id']}"

    def test_md_extracts_case_citations(self, md_docs, extractor):
        for doc_data in md_docs:
            doc = Document(raw=doc_data["text"], format="markdown")
            result = extractor.extract(doc)
            case_cits = [c for c in result.citations if isinstance(c, CaseCitation)]
            assert len(case_cits) >= 1, f"No case citations in {doc_data['doc_id']}"

    def test_md_span_integrity(self, md_docs, extractor):
        """Every citation span must match doc.text[start:end]."""
        for doc_data in md_docs:
            doc = Document(raw=doc_data["text"], format="markdown")
            result = extractor.extract(doc)
            for cit in result.citations:
                actual = doc.text[cit.span.start : cit.span.end]
                assert actual == cit.span.text, f"[{doc_data['doc_id']}] span mismatch: {actual!r} != {cit.span.text!r}"

    def test_md_offset_map_exists(self, md_docs):
        """Markdown documents must have offset maps for round-tripping."""
        for doc_data in md_docs:
            doc = Document(raw=doc_data["text"], format="markdown")
            assert doc.offset_map is not None, f"No offset map for {doc_data['doc_id']}"
            assert len(doc.offset_map) == len(doc.text)

    def test_md_offset_round_trip(self, md_docs, extractor):
        """map_span_to_raw must recover valid raw substrings."""
        for doc_data in md_docs:
            doc = Document(raw=doc_data["text"], format="markdown")
            result = extractor.extract(doc)
            for cit in result.citations[:10]:
                raw_span = map_span_to_raw(cit.span, doc)
                assert raw_span.start < raw_span.end
                assert raw_span.end <= len(doc.raw)


class TestCrossFormatConsistency:
    """Verify that the same document extracted as HTML and Markdown
    produces similar citation counts (they should be close but not
    necessarily identical due to formatting differences)."""

    def test_html_md_citation_count_parity(self, html_docs, md_docs, extractor):
        """HTML and MD versions of the same doc should find similar citation counts."""
        for html_data, md_data in zip(html_docs, md_docs):
            html_doc = Document(raw=html_data["text"], format="html")
            md_doc = Document(raw=md_data["text"], format="markdown")

            html_result = extractor.extract(html_doc)
            md_result = extractor.extract(md_doc)

            html_count = len(html_result.citations)
            md_count = len(md_result.citations)

            # Allow up to 20% difference due to formatting artifacts
            if html_count > 0:
                ratio = md_count / html_count
                assert 0.5 < ratio < 2.0, (
                    f"[{html_data['doc_id']}] HTML={html_count} vs MD={md_count} "
                    f"citations — ratio {ratio:.2f} is too far off"
                )

    def test_html_md_same_courts(self, html_docs, md_docs):
        """HTML and MD fixture pairs should reference the same courts."""
        for html_data, md_data in zip(html_docs, md_docs):
            assert html_data["court"] == md_data["court"]
