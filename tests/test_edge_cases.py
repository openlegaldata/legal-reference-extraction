"""Edge-case tests to cover remaining uncovered lines across modules."""

import pytest

from refex.errors import RefExError
from refex.extractors.law import DivideAndConquerLawRefExtractorMixin
from refex.models import BaseRef, Ref, RefMarker, RefType

# --- models.py: line 25 (__hash__) ---


def test_base_ref_hash():
    # BaseRef defines __hash__ but Ref overrides __eq__ which removes it.
    # Test BaseRef.__hash__ directly.
    ref = BaseRef()
    ref.ref_type = RefType.LAW
    h = hash(ref)
    assert isinstance(h, int)


# --- models.py: line 99 (unsupported ref type) ---


def test_ref_repr_unsupported_type():
    ref = BaseRef()
    ref.ref_type = RefType.LAW  # no book/section attrs via BaseRef
    # Ref with None ref_type
    ref2 = Ref(ref_type=RefType.LAW, book="bgb", section="1")
    ref2.ref_type = None
    with pytest.raises(ValueError, match="Unsupported ref type"):
        repr(ref2)


# --- RefMarker overlap scenarios ---


def test_ref_marker_mask_non_overlapping():
    """Non-overlapping markers can be masked sequentially."""
    m1 = RefMarker(text="§ 1 BGB", start=0, end=7)
    m2 = RefMarker(text="§ 2 BGB", start=12, end=19)

    content = "§ 1 BGB foo § 2 BGB rest"
    content = m1.replace_content_with_mask(content)
    content = m2.replace_content_with_mask(content)
    assert content == "_______ foo _______ rest"


# --- law.py: line 272 (law_book_codes is None) ---


def test_law_get_law_book_codes_none():
    ext = DivideAndConquerLawRefExtractorMixin()
    ext.law_book_codes = None
    codes = ext.get_law_book_codes()
    assert len(codes) > 0


# --- law.py: lines 300, 303, 306 (get_law_book_ref_regex error paths) ---


def test_law_get_law_book_ref_regex_empty():
    ext = DivideAndConquerLawRefExtractorMixin()
    with pytest.raises(RefExError, match="Cannot generate regex"):
        ext.get_law_book_ref_regex([])


def test_law_get_law_book_ref_regex_optional():
    ext = DivideAndConquerLawRefExtractorMixin()
    with pytest.raises(ValueError, match="optional=True"):
        ext.get_law_book_ref_regex(["BGB"], optional=True)


def test_law_get_law_book_ref_regex_group_name():
    ext = DivideAndConquerLawRefExtractorMixin()
    with pytest.raises(ValueError, match="group_name=True"):
        ext.get_law_book_ref_regex(["BGB"], group_name=True)


# --- law.py: lines 334-346 (context mode with §§ bis/und) ---


def test_law_context_bis():
    ext = DivideAndConquerLawRefExtractorMixin()
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


def test_law_context_und():
    ext = DivideAndConquerLawRefExtractorMixin()
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


# --- law.py: lines 384-385 (Anlage pattern in context mode) ---


def test_law_context_anlage():
    ext = DivideAndConquerLawRefExtractorMixin()
    ext.law_book_context = "sgb"

    content = "Siehe Anlage 3 für Details."
    markers = ext.extract_law_ref_markers(content)
    assert len(markers) >= 1
    assert markers[0].references[0].section == "anlage-3"


# Additional context-mode scenarios (ported from the deleted
# test_law_legacy.py when the legacy pre-refactor law.py was removed).


def test_law_context_single_section_plaintext():
    ext = DivideAndConquerLawRefExtractorMixin()
    ext.law_book_context = "bgb"

    content = "Gemäß § 20 ist dies der Fall."
    markers = ext.extract_law_ref_markers(content)
    assert len(markers) == 1
    assert markers[0].references[0].section == "20"
    assert markers[0].references[0].book == "bgb"


def test_law_context_html_entity_for_section_sign():
    """``&#167;`` (HTML entity for §) should be normalised in context mode."""
    ext = DivideAndConquerLawRefExtractorMixin()
    ext.law_book_context = "zpo"

    content = "Gemäß &#167; 343 ist dies der Fall."
    markers = ext.extract_law_ref_markers(content)
    assert len(markers) == 1
    assert markers[0].references[0].section == "343"


def test_law_context_no_duplicate_across_patterns():
    """Context mode runs several patterns over the text; the same section must
    not be emitted twice by two different matching patterns."""
    ext = DivideAndConquerLawRefExtractorMixin()
    ext.law_book_context = "sgb"

    content = "Es gilt § 1 Abs. 2 Satz 3 dieses Gesetzes und § 5 ist anwendbar."
    markers = ext.extract_law_ref_markers(content)
    assert len(markers) == 2
    sections = sorted([m.references[0].section for m in markers])
    assert sections == ["1", "5"]


# --- law.py: line 187 (no refs found in marker) ---


def test_law_multi_marker_no_refs(law_extractor):
    """A multi-marker pattern that matches but yields no individual section refs."""
    # This is hard to trigger since the regex is quite specific; we test the warning path
    # by checking that markers without refs are not appended
    content = "Ein Satz ohne echte Referenzen."
    new_content, markers = law_extractor.extract(content)
    # No law markers should be extracted
    law_markers = [m for m in markers if any(r.ref_type == RefType.LAW for r in m.get_references())]
    assert len(law_markers) == 0


# --- law.py: lines 248-260 (waiting_for_book / next_book pattern) ---


def test_law_ivm_pattern(law_extractor):
    """Test i.V.m. pattern that creates markers waiting for a book."""
    content = "Nach § 167 VwGO i.V.m. §§ 708 Nr. 11, 711 ZPO ist dies gültig."
    new_content, markers = law_extractor.extract(content)
    all_refs = []
    for m in markers:
        all_refs.extend(m.get_references())
    sections = [r.section for r in all_refs if r.ref_type == RefType.LAW]
    assert "167" in sections


# --- case.py: line 30 (repl2 inner function) ---


def test_case_clean_text_abbreviation(case_extractor):
    """Test that abbreviations with dots are handled by repl2."""
    text = " vgl. z.B. BVerfG, Beschluss vom 23.07.2003"
    result = case_extractor.clean_text_for_tokenizer(text)
    # repl2 replaces group(1) + underscores: ' vgl.' becomes ' ____'
    assert "vgl" not in result
    assert "____" in result


# --- RefMarker additional coverage ---


def test_ref_marker_positions():
    m = RefMarker(text="§ 1 BGB", start=10, end=17)
    assert m.start == 10
    assert m.end == 17
    assert m.end - m.start == 7


# Note: test_ref_marker_replace_content_with_mask lives in test_models.py;
# the mask-multiple-non-overlapping case is covered above in
# test_ref_marker_mask_non_overlapping.
