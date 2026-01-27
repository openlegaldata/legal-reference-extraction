"""Tests for the legacy LawRefExtractorMixin (src/refex/extractors/law.py).

This mixin is not used by RefExtractor (which uses DivideAndConquerLawRefExtractorMixin),
but it is still part of the package and needs test coverage.
"""

import pytest

from refex.errors import RefExError
from refex.extractors.law import LawRefExtractorMixin
from refex.models import RefType


class LegacyLawExtractor(LawRefExtractorMixin):
    """Concrete class to test the mixin."""

    pass


@pytest.fixture()
def legacy():
    ext = LegacyLawExtractor()
    ext.law_book_codes = []
    return ext


# --- get_law_book_codes ---


def test_get_law_book_codes_defaults(legacy):
    codes = legacy.get_law_book_codes()
    assert "BGB" in codes
    assert "GG" in codes
    assert len(codes) == len(legacy.default_law_book_codes)


def test_get_law_book_codes_custom():
    ext = LegacyLawExtractor()
    ext.law_book_codes = ["ABC", "DEF"]
    codes = ext.get_law_book_codes()
    assert codes == ["ABC", "DEF"]


def test_get_law_book_codes_none():
    ext = LegacyLawExtractor()
    ext.law_book_codes = None
    codes = ext.get_law_book_codes()
    assert len(codes) == len(ext.default_law_book_codes)


# --- get_law_book_ref_regex ---


def test_get_law_book_ref_regex_basic(legacy):
    result = legacy.get_law_book_ref_regex(["BGB", "ZPO", "GG"])
    assert result == "BGB|ZPO|GG"


def test_get_law_book_ref_regex_to_lower(legacy):
    result = legacy.get_law_book_ref_regex(["BGB", "ZPO"], to_lower=True)
    assert result == "bgb|zpo"


def test_get_law_book_ref_regex_empty_raises(legacy):
    with pytest.raises(RefExError, match="Cannot generate regex"):
        legacy.get_law_book_ref_regex([])


def test_get_law_book_ref_regex_optional_raises(legacy):
    with pytest.raises(ValueError, match="optional=True"):
        legacy.get_law_book_ref_regex(["BGB"], optional=True)


def test_get_law_book_ref_regex_group_name_raises(legacy):
    with pytest.raises(ValueError, match="group_name=True"):
        legacy.get_law_book_ref_regex(["BGB"], group_name=True)


# --- get_law_ref_regex ---


def test_get_law_ref_regex(legacy):
    regex = legacy.get_law_ref_regex(["BGB", "ZPO"])
    assert "BGB" in regex
    assert "ZPO" in regex
    assert "§" in regex


# --- handle_single_law_ref ---


def test_handle_single_law_ref(legacy):
    codes = ["BGB"]
    refs = legacy.handle_single_law_ref(codes, "§ 433 BGB", [])
    assert len(refs) == 1
    assert refs[0].book == "bgb"
    assert refs[0].section == "433"
    assert refs[0].ref_type == RefType.LAW


def test_handle_single_law_ref_with_section_az(legacy):
    codes = ["AsylG"]
    refs = legacy.handle_single_law_ref(codes, "§ 3d AsylG", [])
    assert len(refs) == 1
    assert refs[0].section == "3d"


def test_handle_single_law_ref_no_match(legacy):
    codes = ["BGB"]
    refs = legacy.handle_single_law_ref(codes, "§ xyz", [])
    assert len(refs) == 0


def test_handle_single_law_ref_article(legacy):
    codes = ["GG"]
    refs = legacy.handle_single_law_ref(codes, "Art. 1 GG", [])
    assert len(refs) == 1
    assert refs[0].book == "gg"
    assert refs[0].section == "1"


# --- handle_multiple_law_refs ---


def test_handle_multiple_law_refs(legacy):
    codes = ["BGB"]
    refs = legacy.handle_multiple_law_refs(codes, "§§ 1, 2 BGB", [])
    assert len(refs) >= 2
    sections = [r.section for r in refs]
    assert "1" in sections
    assert "2" in sections


def test_handle_multiple_law_refs_with_range(legacy):
    codes = ["BGB"]
    refs = legacy.handle_multiple_law_refs(codes, "§§ 3 bis 6 BGB", [])
    sections = sorted([r.section for r in refs])
    # Should include 3, 4, 5, 6
    assert "3" in sections
    assert "6" in sections


def test_handle_multiple_law_refs_with_semicolon(legacy):
    codes = ["StPO"]
    refs = legacy.handle_multiple_law_refs(codes, "§§ 52; 53 StPO", [])
    sections = [r.section for r in refs]
    assert "52" in sections
    assert "53" in sections


# --- extract_law_ref_markers (main method) ---


def test_extract_law_ref_markers_single(legacy):
    content = "Gemäß § 433 BGB ist der Käufer verpflichtet."
    markers = legacy.extract_law_ref_markers(content)
    assert len(markers) >= 1
    refs = markers[0].get_references()
    assert any(r.book == "bgb" and r.section == "433" for r in refs)


def test_extract_law_ref_markers_multi(legacy):
    content = "Nach §§ 3, 4 BGB gilt dies."
    markers = legacy.extract_law_ref_markers(content)
    assert len(markers) >= 1
    all_refs = []
    for m in markers:
        all_refs.extend(m.get_references())
    sections = [r.section for r in all_refs]
    assert "3" in sections
    assert "4" in sections


def test_extract_law_ref_markers_no_match(legacy):
    content = "Ein Satz ohne Paragraphen."
    markers = legacy.extract_law_ref_markers(content)
    assert len(markers) == 0


def test_extract_law_ref_markers_with_abs(legacy):
    content = "Laut § 3 Abs. 1 AsylG ist dies der Fall."
    markers = legacy.extract_law_ref_markers(content)
    assert len(markers) >= 1


# --- extract_law_ref_markers_with_context ---


def test_extract_with_context_single_section():
    ext = LegacyLawExtractor()
    ext.law_book_codes = []
    ext.law_book_context = "bgb"

    content = "Gemäß § 20 ist dies der Fall."
    markers = ext.extract_law_ref_markers(content)
    assert len(markers) == 1
    assert markers[0].references[0].section == "20"
    assert markers[0].references[0].book == "bgb"


def test_extract_with_context_multi_section_bis():
    ext = LegacyLawExtractor()
    ext.law_book_codes = []
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
    ext = LegacyLawExtractor()
    ext.law_book_codes = []
    ext.law_book_context = "bgb"

    content = "Siehe Anlage 3 für Details."
    markers = ext.extract_law_ref_markers(content)
    assert len(markers) >= 1
    assert markers[0].references[0].section == "anlage-3"


def test_extract_with_context_html_entity():
    ext = LegacyLawExtractor()
    ext.law_book_codes = []
    ext.law_book_context = "zpo"

    content = "Gemäß &#167; 343 ist dies der Fall."
    markers = ext.extract_law_ref_markers(content)
    assert len(markers) == 1
    assert markers[0].references[0].section == "343"


def test_extract_with_context_und():
    ext = LegacyLawExtractor()
    ext.law_book_codes = []
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
    ext = LegacyLawExtractor()
    ext.law_book_codes = []
    ext.law_book_context = "sgb"

    content = "Es gilt § 1 Abs. 2 Satz 3 dieses Gesetzes und § 5 ist anwendbar."
    markers = ext.extract_law_ref_markers(content)
    assert len(markers) == 2
    sections = sorted([m.references[0].section for m in markers])
    assert sections == ["1", "5"]


# --- get_law_ref_match_single ---


def test_get_law_ref_match_single(legacy):
    match = legacy.get_law_ref_match_single(["BGB"], "§ 433 BGB")
    assert match is not None
    assert match.group("book") == "BGB"
    assert match.group("sect") == "433"


def test_get_law_ref_match_single_no_match(legacy):
    match = legacy.get_law_ref_match_single(["BGB"], "no ref here")
    assert match is None


# --- get_law_ref_match_multi ---


def test_get_law_ref_match_multi(legacy):
    matches = list(legacy.get_law_ref_match_multi(["BGB"], "§§ 1, 2 BGB"))
    assert len(matches) >= 2
