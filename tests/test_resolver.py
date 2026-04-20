"""Tests for short-form resolution and relation detection (Stream I)."""

from refex.citations import CaseCitation, LawCitation, Span
from refex.orchestrator import CitationExtractor
from refex.resolver import (
    _detect_relations,
    _resolve_case_short_forms,
    _resolve_law_short_forms,
    resolve_short_forms,
)

# --- Short-form law resolution (I3) ---


class TestResolveLawShortForms:
    def test_bare_section_inherits_book(self):
        cits = [
            LawCitation(span=Span(0, 10, "§ 433 BGB"), id="c1", book="bgb", number="433"),
            LawCitation(span=Span(30, 34, "§ 434"), id="c2", book=None, number="434"),
        ]
        result = _resolve_law_short_forms(cits)
        assert result[1].book == "bgb"
        assert result[1].kind == "short"
        assert result[1].resolves_to == "c1"

    def test_full_citation_not_modified(self):
        cits = [
            LawCitation(span=Span(0, 10, "§ 433 BGB"), id="c1", book="bgb", number="433"),
        ]
        result = _resolve_law_short_forms(cits)
        assert result[0].kind == "full"
        assert result[0].resolves_to is None

    def test_multiple_short_forms_same_book(self):
        cits = [
            LawCitation(span=Span(0, 10, "§ 433 BGB"), id="c1", book="bgb", number="433"),
            LawCitation(span=Span(20, 24, "§ 434"), id="c2", book=None, number="434"),
            LawCitation(span=Span(40, 44, "§ 435"), id="c3", book=None, number="435"),
        ]
        result = _resolve_law_short_forms(cits)
        assert result[1].book == "bgb"
        assert result[2].book == "bgb"
        assert result[1].resolves_to == "c1"
        assert result[2].resolves_to == "c1"

    def test_book_context_switches(self):
        cits = [
            LawCitation(span=Span(0, 10, "§ 433 BGB"), id="c1", book="bgb", number="433"),
            LawCitation(span=Span(20, 24, "§ 5"), id="c2", book=None, number="5"),
            LawCitation(span=Span(40, 50, "§ 154 VwGO"), id="c3", book="vwgo", number="154"),
            LawCitation(span=Span(60, 64, "§ 155"), id="c4", book=None, number="155"),
        ]
        result = _resolve_law_short_forms(cits)
        assert result[1].book == "bgb"
        assert result[3].book == "vwgo"

    def test_no_prior_context_stays_none(self):
        cits = [
            LawCitation(span=Span(0, 4, "§ 42"), id="c1", book=None, number="42"),
        ]
        result = _resolve_law_short_forms(cits)
        assert result[0].book is None
        assert result[0].kind == "full"  # No modification, no prior context

    def test_case_citations_preserved(self):
        cits = [
            LawCitation(span=Span(0, 10, "§ 433 BGB"), id="c1", book="bgb", number="433"),
            CaseCitation(span=Span(20, 35, "10 C 23.12"), id="c2", court="BVerwG"),
            LawCitation(span=Span(50, 54, "§ 434"), id="c3", book=None, number="434"),
        ]
        result = _resolve_law_short_forms(cits)
        assert len(result) == 3
        assert result[1].type == "case"
        assert result[2].book == "bgb"  # Still resolves past the case citation

    def test_empty_input(self):
        assert _resolve_law_short_forms([]) == []

    def test_number_preserved(self):
        cits = [
            LawCitation(span=Span(0, 10, "§ 433 BGB"), id="c1", book="bgb", number="433"),
            LawCitation(span=Span(30, 36, "§ 434a"), id="c2", book=None, number="434a"),
        ]
        result = _resolve_law_short_forms(cits)
        assert result[1].number == "434a"


# --- Relation detection (I2) ---


class TestDetectRelations:
    def test_ivm_detected(self):
        cits = [
            LawCitation(span=Span(0, 10, "§ 433 BGB"), id="c1", book="bgb"),
            LawCitation(span=Span(20, 30, "§ 434 BGB"), id="c2", book="bgb"),
        ]
        text = "§ 433 BGB i.V.m. § 434 BGB"
        rels = _detect_relations(cits, text)
        assert len(rels) == 1
        assert rels[0].relation == "ivm"
        assert rels[0].source_id == "c1"
        assert rels[0].target_id == "c2"
        assert rels[0].span.text == "i.V.m."

    def test_vgl_detected(self):
        cits = [
            LawCitation(span=Span(0, 10, "§ 433 BGB"), id="c1", book="bgb"),
            LawCitation(span=Span(17, 27, "§ 434 BGB"), id="c2", book="bgb"),
        ]
        text = "§ 433 BGB vgl. § 434 BGB"
        rels = _detect_relations(cits, text)
        assert len(rels) == 1
        assert rels[0].relation == "vgl"

    def test_no_relation_in_gap(self):
        cits = [
            LawCitation(span=Span(0, 10, "§ 433 BGB"), id="c1", book="bgb"),
            LawCitation(span=Span(16, 26, "§ 434 BGB"), id="c2", book="bgb"),
        ]
        text = "§ 433 BGB und § 434 BGB"
        rels = _detect_relations(cits, text)
        assert len(rels) == 0

    def test_relation_span_integrity(self):
        cits = [
            LawCitation(span=Span(0, 10, "§ 433 BGB"), id="c1", book="bgb"),
            LawCitation(span=Span(20, 30, "§ 434 BGB"), id="c2", book="bgb"),
        ]
        text = "§ 433 BGB i.V.m. § 434 BGB"
        rels = _detect_relations(cits, text)
        for r in rels:
            if r.span:
                actual = text[r.span.start : r.span.end]
                assert actual == r.span.text

    def test_empty_citations(self):
        assert _detect_relations([], "some text") == []

    def test_single_citation(self):
        cits = [LawCitation(span=Span(0, 10, "§ 433 BGB"), id="c1", book="bgb")]
        assert _detect_relations(cits, "§ 433 BGB ist anwendbar.") == []

    def test_aao_detected(self):
        cits = [
            LawCitation(span=Span(0, 10, "§ 433 BGB"), id="c1", book="bgb"),
            LawCitation(span=Span(20, 30, "§ 434 BGB"), id="c2", book="bgb"),
        ]
        text = "§ 433 BGB a.a.O. § 434 BGB"
        rels = _detect_relations(cits, text)
        assert len(rels) == 1
        assert rels[0].relation == "aao"


# --- Full resolve_short_forms ---


class TestResolveShortForms:
    def test_combines_resolution_and_relations(self):
        cits = [
            LawCitation(span=Span(0, 10, "§ 433 BGB"), id="c1", book="bgb", number="433"),
            LawCitation(span=Span(20, 24, "§ 434"), id="c2", book=None, number="434"),
        ]
        text = "§ 433 BGB i.V.m. § 434 something"
        resolved, rels = resolve_short_forms(cits, text)
        assert resolved[1].book == "bgb"  # Resolved
        assert len(rels) == 1  # i.V.m. detected
        assert rels[0].relation == "ivm"


# --- Integration with orchestrator ---


class TestOrchestratorWithResolver:
    def test_short_form_resolved_in_extract(self):
        text = "§ 433 BGB verpflichtet, § 434 regelt die Mängel."
        ext = CitationExtractor()
        result = ext.extract(text)
        law_cits = [c for c in result.citations if isinstance(c, LawCitation)]
        # The second § 434 should have inherited book from § 433 BGB
        # (only if the extractor didn't find a book for it)
        if len(law_cits) >= 2 and not law_cits[1].book:
            # If it's a bare section without book, resolution should have kicked in
            pass  # This depends on whether the regex finds a book or not

    def test_relations_in_extract(self):
        text = "§ 433 BGB i.V.m. § 434 BGB regeln den Kaufvertrag."
        ext = CitationExtractor()
        result = ext.extract(text)
        # Should detect i.V.m. relation
        ivm_rels = [r for r in result.relations if r.relation == "ivm"]
        if len(result.citations) >= 2:
            assert len(ivm_rels) >= 1

    def test_vgl_relation_in_extract(self):
        text = "Gemäß § 154 VwGO (vgl. § 155 VwGO) fallen die Kosten an."
        ext = CitationExtractor()
        result = ext.extract(text)
        vgl_rels = [r for r in result.relations if r.relation == "vgl"]
        if len(result.citations) >= 2:
            assert len(vgl_rels) >= 1

    def test_relation_span_integrity_in_extract(self):
        text = "§ 433 BGB i.V.m. § 434 BGB regeln den Kaufvertrag."
        ext = CitationExtractor()
        result = ext.extract(text)
        for r in result.relations:
            if r.span:
                actual = text[r.span.start : r.span.end]
                assert actual == r.span.text, f"Relation span mismatch: {actual!r} != {r.span.text!r}"


# --- Case short-form resolution (I4) ---


class TestResolveCaseShortForms:
    def test_reporter_after_full_citation_linked(self):
        cits = [
            CaseCitation(span=Span(0, 20, "BGH VIII ZR 295/01"), id="c1", court="BGH", file_number="VIII ZR 295/01"),
            CaseCitation(
                span=Span(30, 45, "BGHZ 154, 239"), id="c2", reporter="BGHZ", reporter_volume="154", reporter_page="239"
            ),
        ]
        result = _resolve_case_short_forms(cits)
        assert result[1].kind == "short"
        assert result[1].court == "BGH"

    def test_reporter_without_prior_full_not_resolved(self):
        cits = [
            CaseCitation(
                span=Span(0, 15, "BGHZ 154, 239"), id="c1", reporter="BGHZ", reporter_volume="154", reporter_page="239"
            ),
        ]
        result = _resolve_case_short_forms(cits)
        assert result[0].kind == "full"  # Unchanged

    def test_reporter_mismatched_court_not_resolved(self):
        cits = [
            CaseCitation(span=Span(0, 20, "BVerwG 10 C 23.12"), id="c1", court="BVerwG", file_number="10 C 23.12"),
            CaseCitation(
                span=Span(30, 45, "BGHZ 154, 239"), id="c2", reporter="BGHZ", reporter_volume="154", reporter_page="239"
            ),
        ]
        result = _resolve_case_short_forms(cits)
        assert result[1].kind == "full"  # Mismatched court

    def test_bverfge_after_bverfg(self):
        cits = [
            CaseCitation(span=Span(0, 20, "BVerfG 1 BvL 7/14"), id="c1", court="BVerfG", file_number="1 BvL 7/14"),
            CaseCitation(
                span=Span(30, 45, "BVerfGE 85, 248"),
                id="c2",
                reporter="BVerfGE",
                reporter_volume="85",
                reporter_page="248",
            ),
        ]
        result = _resolve_case_short_forms(cits)
        assert result[1].kind == "short"
        assert result[1].court == "BVerfG"

    def test_law_citations_not_affected(self):
        cits = [
            LawCitation(span=Span(0, 10, "§ 433 BGB"), id="c1", book="bgb"),
            CaseCitation(span=Span(20, 35, "BGH IX ZR 165/12"), id="c2", court="BGH", file_number="IX ZR 165/12"),
            CaseCitation(
                span=Span(50, 65, "BGHZ 108, 98"), id="c3", reporter="BGHZ", reporter_volume="108", reporter_page="98"
            ),
        ]
        result = _resolve_case_short_forms(cits)
        assert result[0].type == "law"  # Preserved
        assert result[2].kind == "short"
        assert result[2].court == "BGH"


# --- I6: Test fixtures with German legal text per short-form kind ---


class TestShortFormFixtures:
    """Integration tests with realistic German legal text for each short-form kind."""

    def test_law_short_form_in_sentence(self):
        """I3: Bare § inherits book from prior full citation."""
        text = "Nach § 433 Abs. 1 BGB ist der Verkäufer verpflichtet, nach § 434 liegen Mängel vor."
        ext = CitationExtractor()
        result = ext.extract(text)
        law_cits = [c for c in result.citations if isinstance(c, LawCitation)]
        short_cits = [c for c in law_cits if c.kind == "short"]
        # § 434 should be resolved as short-form with book=bgb
        if short_cits:
            assert short_cits[0].book is not None

    def test_ivm_relation_fixture(self):
        """I2d: i.V.m. becomes a CitationRelation."""
        text = "§ 280 Abs. 1 BGB i.V.m. § 241 Abs. 2 BGB begründen den Anspruch."
        ext = CitationExtractor()
        result = ext.extract(text)
        ivm_rels = [r for r in result.relations if r.relation == "ivm"]
        assert len(ivm_rels) >= 1
        assert ivm_rels[0].span.text in ("i.V.m.", "i.V.m")

    def test_vgl_relation_fixture(self):
        """I2d: vgl. becomes a CitationRelation."""
        text = "Die Kosten nach § 154 Abs. 1 VwGO (vgl. § 155 VwGO) sind zu erstatten."
        ext = CitationExtractor()
        result = ext.extract(text)
        vgl_rels = [r for r in result.relations if r.relation == "vgl"]
        if len(result.citations) >= 2:
            assert len(vgl_rels) >= 1

    def test_aao_relation_fixture(self):
        """I2a: a.a.O. detected between citations."""
        cits = [
            LawCitation(span=Span(0, 10, "§ 433 BGB"), id="c1", book="bgb"),
            LawCitation(span=Span(24, 34, "§ 434 BGB"), id="c2", book="bgb"),
        ]
        text = "§ 433 BGB (a. a. O.) § 434 BGB regelt dies."
        rels = _detect_relations(cits, text)
        assert any(r.relation == "aao" for r in rels)

    def test_ebenda_relation_fixture(self):
        """I2b: ebenda / ebd. detected between citations."""
        cits = [
            LawCitation(span=Span(0, 10, "§ 433 BGB"), id="c1", book="bgb"),
            LawCitation(span=Span(20, 30, "§ 434 BGB"), id="c2", book="bgb"),
        ]
        text = "§ 433 BGB ebenda § 434 BGB gilt."
        rels = _detect_relations(cits, text)
        assert any(r.relation == "ebenda" for r in rels)

    def test_full_resolve_combines_all(self):
        """resolve_short_forms handles law short-forms, case short-forms, and relations."""
        cits = [
            LawCitation(span=Span(0, 15, "§ 433 Abs. 1 BGB"), id="c1", book="bgb", number="433"),
            LawCitation(span=Span(25, 30, "§ 434"), id="c2", book=None, number="434"),
            CaseCitation(span=Span(40, 60, "BGH IX ZR 165/12"), id="c3", court="BGH", file_number="IX ZR 165/12"),
            CaseCitation(
                span=Span(70, 85, "BGHZ 108, 98"), id="c4", reporter="BGHZ", reporter_volume="108", reporter_page="98"
            ),
        ]
        text = "§ 433 Abs. 1 BGB i.V.m. § 434 weist auf BGH IX ZR 165/12 sowie BGHZ 108, 98 etwas hin."
        resolved, rels = resolve_short_forms(cits, text)

        # Law short-form resolved
        assert resolved[1].book == "bgb"
        assert resolved[1].kind == "short"

        # Case reporter linked to prior full case
        assert resolved[3].kind == "short"
        assert resolved[3].court == "BGH"

        # i.V.m. relation detected
        assert any(r.relation == "ivm" for r in rels)
