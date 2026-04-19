"""Tests for Art./Artikel extraction (Stream E)."""

from refex.citations import LawCitation
from refex.engines.regex import RegexLawExtractor
from refex.extractor import RefExtractor

# --- Regex extraction (legacy API) ---


def test_art_single_ref():
    e = RefExtractor()
    e.do_case_refs = False
    _, markers = e.extract("Gemäß Art. 12 Abs. 1 GG ist dies geschützt.")
    refs = [r for m in markers for r in m.get_references()]
    assert any(r.book == "gg" and r.section == "12" for r in refs)


def test_art_multi_ref():
    e = RefExtractor()
    e.do_case_refs = False
    _, markers = e.extract("Die Art. 1, 2, 3 GG schützen Grundrechte.")
    refs = [r for m in markers for r in m.get_references()]
    sections = {r.section for r in refs}
    assert sections == {"1", "2", "3"}
    assert all(r.book == "gg" for r in refs)


def test_art_without_period():
    e = RefExtractor()
    e.do_case_refs = False
    _, markers = e.extract("Nach Art 5 GG ist die Pressefreiheit geschützt.")
    refs = [r for m in markers for r in m.get_references()]
    assert any(r.book == "gg" and r.section == "5" for r in refs)


def test_artikel_full_word():
    e = RefExtractor()
    e.do_case_refs = False
    _, markers = e.extract("Gemäß Artikel 20 GG ist dies so.")
    refs = [r for m in markers for r in m.get_references()]
    assert any(r.book == "gg" and r.section == "20" for r in refs)


def test_art_no_false_positive_in_text():
    """The word 'Art' in normal text should not trigger extraction."""
    e = RefExtractor()
    e.do_case_refs = False
    _, markers = e.extract("Diese Art der Beweisführung ist unzulässig.")
    refs = [r for m in markers for r in m.get_references()]
    assert len(refs) == 0


def test_art_with_abs_and_satz():
    e = RefExtractor()
    e.do_case_refs = False
    _, markers = e.extract("Art. 3 Abs. 1 Satz 2 GG verbietet Diskriminierung.")
    refs = [r for m in markers for r in m.get_references()]
    assert any(r.book == "gg" and r.section == "3" for r in refs)


# --- New typed API ---


def test_typed_art_citation():
    ext = RegexLawExtractor()
    cits, _ = ext.extract("Art. 12 Abs. 1 GG ist einschlägig.")
    law_cits = [c for c in cits if isinstance(c, LawCitation)]
    assert len(law_cits) >= 1
    art = law_cits[0]
    assert art.unit == "article"
    assert art.delimiter == "Art."
    assert art.book == "gg"
    assert art.number == "12"


def test_typed_paragraph_citation():
    ext = RegexLawExtractor()
    cits, _ = ext.extract("§ 433 BGB regelt den Kaufvertrag.")
    law_cits = [c for c in cits if isinstance(c, LawCitation)]
    assert len(law_cits) >= 1
    par = law_cits[0]
    assert par.unit == "paragraph"
    assert par.delimiter == "§"


def test_art_span_integrity():
    text = "Gemäß Art. 14 Abs. 1 GG ist das Eigentum geschützt."
    ext = RegexLawExtractor()
    cits, _ = ext.extract(text)
    for c in cits:
        actual = text[c.span.start : c.span.end]
        assert actual == c.span.text
