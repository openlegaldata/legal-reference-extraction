"""Tests for the CitationExtractor orchestrator and regex engines (Stream C)."""

from refex.citations import CaseCitation, ExtractionResult, LawCitation, Span
from refex.compat import citations_to_ref_markers, to_ref_marker_string
from refex.engines.regex import RegexCaseExtractor, RegexLawExtractor
from refex.models import RefType
from refex.orchestrator import CitationExtractor, _resolve_overlaps

# --- RegexLawExtractor ---


class TestRegexLawExtractor:
    def test_simple_ref(self):
        ext = RegexLawExtractor()
        cits, rels = ext.extract("Gemäß § 433 BGB ist der Käufer verpflichtet.")
        assert len(cits) >= 1
        law = next(c for c in cits if isinstance(c, LawCitation))
        assert law.book == "bgb"
        assert law.number == "433"
        assert law.type == "law"

    def test_multi_ref(self):
        ext = RegexLawExtractor()
        cits, rels = ext.extract("Laut §§ 3, 4 BGB gilt dies.")
        assert len(cits) >= 2
        sections = {c.number for c in cits if isinstance(c, LawCitation)}
        assert "3" in sections
        assert "4" in sections

    def test_no_match(self):
        ext = RegexLawExtractor()
        cits, _ = ext.extract("Ein Satz ohne jegliche Paragraphen.")
        assert len(cits) == 0

    def test_span_integrity(self):
        text = "Wegen § 154 Abs. 1 VwGO fallen die Kosten an."
        ext = RegexLawExtractor()
        cits, _ = ext.extract(text)
        for c in cits:
            assert text[c.span.start : c.span.end] == c.span.text

    def test_nbsp_section_sign(self):
        """Non-breaking space after § should still match."""
        ext = RegexLawExtractor()
        cits, _ = ext.extract("nach §\xa042 Abs. 1 VwGO bezüglich")
        assert len(cits) >= 1
        assert any(c.number == "42" for c in cits if isinstance(c, LawCitation))

    def test_full_name_citation(self):
        ext = RegexLawExtractor()
        cits, _ = ext.extract("§ 40 des Verwaltungsverfahrensgesetzes ist anwendbar.")
        assert len(cits) >= 1
        law = next(c for c in cits if isinstance(c, LawCitation))
        assert "verwaltungsverfahrensgesetz" in (law.book or "")


# --- RegexCaseExtractor ---


class TestRegexCaseExtractor:
    def test_simple_case_ref(self):
        ext = RegexCaseExtractor()
        cits, _ = ext.extract("BVerwG, Urteil vom 20. Februar 2013, - 10 C 23.12 -")
        assert len(cits) >= 1
        case = next(c for c in cits if isinstance(c, CaseCitation))
        assert case.type == "case"
        assert case.file_number is not None

    def test_span_integrity(self):
        text = "Das OVG hat entschieden (Az. 1 A 100/20)."
        ext = RegexCaseExtractor()
        cits, _ = ext.extract(text)
        for c in cits:
            assert text[c.span.start : c.span.end] == c.span.text


# --- CitationExtractor orchestrator ---


class TestCitationExtractor:
    def test_default_engines(self):
        ext = CitationExtractor()
        assert len(ext.engines) == 2

    def test_extracts_law_and_case(self):
        text = "Gemäß § 433 BGB (vgl. BVerwG, Az. 10 C 23.12) ist dies so."
        ext = CitationExtractor()
        result = ext.extract(text)
        types = {c.type for c in result.citations}
        assert "law" in types

    def test_result_type(self):
        ext = CitationExtractor()
        result = ext.extract("§ 1 BGB")
        assert isinstance(result, ExtractionResult)

    def test_span_integrity_all(self):
        text = "§ 433 Abs. 1 BGB und § 812 BGB regeln verschiedene Ansprüche."
        ext = CitationExtractor()
        result = ext.extract(text)
        for c in result.citations:
            actual = text[c.span.start : c.span.end]
            assert actual == c.span.text, f"Span mismatch: {actual!r} != {c.span.text!r}"

    def test_empty_input(self):
        ext = CitationExtractor()
        result = ext.extract("")
        assert result.citations == []

    def test_no_overlap_in_output(self):
        text = "§ 433 BGB und § 812 BGB"
        ext = CitationExtractor()
        result = ext.extract(text)
        sorted_cits = sorted(result.citations, key=lambda c: c.span.start)
        for i in range(len(sorted_cits) - 1):
            assert sorted_cits[i].span.end <= sorted_cits[i + 1].span.start


# --- Overlap resolution ---


class TestResolveOverlaps:
    def test_no_overlaps(self):
        cits = [
            LawCitation(span=Span(0, 5, "§ 1 A"), book="a"),
            LawCitation(span=Span(10, 15, "§ 2 B"), book="b"),
        ]
        result = _resolve_overlaps(cits)
        assert len(result) == 2

    def test_removes_overlap(self):
        cits = [
            LawCitation(span=Span(0, 10, "§ 1 A long"), book="a"),
            LawCitation(span=Span(5, 15, "A long § 2"), book="b"),
        ]
        result = _resolve_overlaps(cits)
        assert len(result) == 1

    def test_higher_confidence_wins(self):
        cits = [
            LawCitation(span=Span(0, 10, "§ 1 A long"), book="a", confidence=0.5),
            LawCitation(span=Span(5, 15, "A long § 2"), book="b", confidence=0.9),
        ]
        result = _resolve_overlaps(cits)
        assert len(result) == 1
        assert result[0].book == "b"

    def test_empty_input(self):
        assert _resolve_overlaps([]) == []


# --- Backward compatibility adapter (C5/C6) ---


class TestCompat:
    def test_citations_to_ref_markers(self):
        result = ExtractionResult(
            citations=[
                LawCitation(span=Span(6, 15, "§ 433 BGB"), book="bgb", number="433"),
                CaseCitation(span=Span(20, 30, "10 C 23.12"), court="BVerwG"),
            ]
        )
        markers = citations_to_ref_markers(result)
        assert len(markers) == 2
        assert markers[0].text == "§ 433 BGB"
        assert markers[0].references[0].ref_type == RefType.LAW
        assert markers[0].references[0].book == "bgb"
        assert markers[1].references[0].ref_type == RefType.CASE

    def test_to_ref_marker_string(self):
        result = ExtractionResult(
            citations=[
                LawCitation(span=Span(6, 15, "§ 433 BGB"), book="bgb", number="433"),
            ]
        )
        content = "Laut § 433 BGB ist dies so."
        import warnings

        with warnings.catch_warnings():
            warnings.simplefilter("ignore", DeprecationWarning)
            output = to_ref_marker_string(result, content)
        assert "[ref=" in output
        assert "[/ref]" in output
        assert "§ 433 BGB" in output

    def test_round_trip_law(self):
        """New API → legacy markers → check fields preserved."""
        result = ExtractionResult(
            citations=[
                LawCitation(
                    span=Span(0, 10, "§ 433 BGB"),
                    book="bgb",
                    number="433",
                ),
            ]
        )
        markers = citations_to_ref_markers(result)
        ref = markers[0].references[0]
        assert ref.ref_type == RefType.LAW
        assert ref.book == "bgb"
        assert ref.section == "433"

    def test_round_trip_case(self):
        result = ExtractionResult(
            citations=[
                CaseCitation(
                    span=Span(0, 15, "10 C 23.12"),
                    court="BVerwG",
                    file_number="10 C 23.12",
                    date="2013-02-20",
                ),
            ]
        )
        markers = citations_to_ref_markers(result)
        ref = markers[0].references[0]
        assert ref.ref_type == RefType.CASE
        assert ref.court == "BVerwG"
        assert ref.file_number == "10 C 23.12"
        assert ref.date == "2013-02-20"
