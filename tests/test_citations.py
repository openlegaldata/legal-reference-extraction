"""Tests for the new typed citation models (Stream C)."""

from refex.citations import (
    CaseCitation,
    CitationRelation,
    ExtractionResult,
    LawCitation,
    Span,
    make_citation_id,
)


def test_span_frozen():
    s = Span(start=0, end=5, text="hello")
    assert s.start == 0
    assert s.end == 5
    assert s.text == "hello"
    try:
        s.start = 10  # type: ignore[misc]
        assert False, "Should raise"
    except AttributeError:
        pass


def test_span_equality():
    a = Span(0, 5, "hello")
    b = Span(0, 5, "hello")
    assert a == b


def test_span_inequality():
    a = Span(0, 5, "hello")
    b = Span(0, 6, "hello!")
    assert a != b


def test_law_citation_type():
    c = LawCitation(span=Span(0, 10, "§ 433 BGB"), book="bgb", number="433")
    assert c.type == "law"


def test_law_citation_frozen():
    c = LawCitation(span=Span(0, 10, "§ 433 BGB"), book="bgb", number="433")
    try:
        c.book = "zpo"  # type: ignore[misc]
        assert False, "Should raise"
    except AttributeError:
        pass


def test_law_citation_with_structure():
    c = LawCitation(
        span=Span(0, 20, "§ 433 Abs. 1 BGB"),
        book="bgb",
        number="433",
        structure=(("absatz", "1"),),
    )
    assert c.structure == (("absatz", "1"),)


def test_law_citation_short_form():
    c = LawCitation(span=Span(0, 3, "§ 5"), kind="short")
    assert c.kind == "short"
    assert c.book is None


def test_law_citation_defaults():
    c = LawCitation(span=Span(0, 5, "§ 42"))
    assert c.kind == "full"
    assert c.confidence == 1.0
    assert c.source == "regex"
    assert c.unit is None
    assert c.structure == ()
    assert c.resolves_to is None


def test_case_citation_type():
    c = CaseCitation(span=Span(0, 15, "1 BvR 1554/89"), court="BVerfG")
    assert c.type == "case"


def test_case_citation_fields():
    c = CaseCitation(
        span=Span(10, 30, "BGH, VIII ZR 295/01"),
        court="BGH",
        file_number="VIII ZR 295/01",
        date="2003-03-19",
    )
    assert c.court == "BGH"
    assert c.file_number == "VIII ZR 295/01"
    assert c.date == "2003-03-19"


def test_relation():
    r = CitationRelation(
        source_id="abc",
        target_id="def",
        relation="ivm",
        span=Span(20, 26, "i.V.m."),
    )
    assert r.relation == "ivm"
    assert r.span.text == "i.V.m."


def test_relation_without_span():
    r = CitationRelation(source_id="a", target_id="b", relation="resolves_to")
    assert r.span is None


def test_extraction_result_empty():
    r = ExtractionResult()
    assert r.citations == []
    assert r.relations == []


def test_citation_id_deterministic():
    s = Span(0, 10, "§ 433 BGB")
    id1 = make_citation_id(s, "regex", "doc1")
    id2 = make_citation_id(s, "regex", "doc1")
    assert id1 == id2


def test_citation_id_differs_for_different_spans():
    s1 = Span(0, 10, "§ 433 BGB")
    s2 = Span(0, 10, "§ 434 BGB")
    assert make_citation_id(s1, "regex") != make_citation_id(s2, "regex")


def test_citation_id_is_12_hex_chars():
    s = Span(0, 10, "§ 433 BGB")
    cid = make_citation_id(s, "regex")
    assert len(cid) == 12
    assert all(c in "0123456789abcdef" for c in cid)
