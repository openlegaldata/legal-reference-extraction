"""Tests ported from the legacy LawRefExtractorMixin.

The legacy law.py was deleted in Stream B9.  These tests verify that
the DivideAndConquerLawRefExtractorMixin covers all the context-based
extraction behaviour that the legacy extractor provided.
"""

from refex.extractors.law_dnc import DivideAndConquerLawRefExtractorMixin


class ContextLawExtractor(DivideAndConquerLawRefExtractorMixin):
    """Concrete class to test the context-based extraction path."""


# --- extract_law_ref_markers_with_context ---


def test_extract_with_context_single_section():
    ext = ContextLawExtractor()
    ext.law_book_context = "bgb"

    content = "Gemäß § 20 ist dies der Fall."
    markers = ext.extract_law_ref_markers(content)
    assert len(markers) == 1
    assert markers[0].references[0].section == "20"
    assert markers[0].references[0].book == "bgb"


def test_extract_with_context_multi_section_bis():
    ext = ContextLawExtractor()
    ext.law_book_context = "bgb"

    content = "Es gelten §§ 664 bis 670 entsprechend."
    markers = ext.extract_law_ref_markers(content)
    assert len(markers) >= 1
    all_refs = []
    for m in markers:
        all_refs.extend(m.get_references())
    sections = [r.section for r in all_refs]
    assert "664" in sections
    assert "665" in sections
    assert "670" in sections


def test_extract_with_context_anlage():
    ext = ContextLawExtractor()
    ext.law_book_context = "bgb"

    content = "Siehe Anlage 3 für Details."
    markers = ext.extract_law_ref_markers(content)
    assert len(markers) >= 1
    assert markers[0].references[0].section == "anlage-3"


def test_extract_with_context_html_entity():
    ext = ContextLawExtractor()
    ext.law_book_context = "zpo"

    content = "Gemäß &#167; 343 ist dies der Fall."
    markers = ext.extract_law_ref_markers(content)
    assert len(markers) == 1
    assert markers[0].references[0].section == "343"


def test_extract_with_context_und():
    ext = ContextLawExtractor()
    ext.law_book_context = "bgb"

    content = "Es gelten §§ 10 und 20 entsprechend."
    markers = ext.extract_law_ref_markers(content)
    assert len(markers) >= 1
    all_refs = []
    for m in markers:
        all_refs.extend(m.get_references())
    sections = [r.section for r in all_refs]
    assert "10" in sections
    assert "20" in sections


def test_extract_with_context_multiple_patterns():
    """Test that multiple patterns don't produce duplicate matches."""
    ext = ContextLawExtractor()
    ext.law_book_context = "sgb"

    content = "Es gilt § 1 Abs. 2 Satz 3 dieses Gesetzes und § 5 ist anwendbar."
    markers = ext.extract_law_ref_markers(content)
    assert len(markers) == 2
    sections = sorted([m.references[0].section for m in markers])
    assert sections == ["1", "5"]
