"""Tests for JSONL output serializers (Stream D)."""

import json

from refex.citations import (
    CaseCitation,
    CitationRelation,
    ExtractionResult,
    LawCitation,
    Span,
)
from refex.orchestrator import CitationExtractor
from refex.serializers import to_dict, to_json, to_jsonl


class TestToDict:
    def test_law_citation(self):
        cit = LawCitation(
            span=Span(0, 10, "§ 433 BGB"),
            id="abc",
            book="bgb",
            number="433",
            unit="paragraph",
            delimiter="§",
            structure=(("absatz", "1"),),
        )
        d = to_dict(cit)
        assert d["type"] == "law"
        assert d["book"] == "bgb"
        assert d["number"] == "433"
        assert d["unit"] == "paragraph"
        assert d["structure"] == {"absatz": "1"}
        assert d["span"]["start"] == 0
        assert d["span"]["end"] == 10
        assert d["span"]["text"] == "§ 433 BGB"

    def test_case_citation(self):
        cit = CaseCitation(
            span=Span(5, 20, "10 C 23.12"),
            id="def",
            court="BVerwG",
            file_number="10 C 23.12",
            date="2013-02-20",
        )
        d = to_dict(cit)
        assert d["type"] == "case"
        assert d["court"] == "BVerwG"
        assert d["file_number"] == "10 C 23.12"
        assert d["date"] == "2013-02-20"

    def test_law_citation_minimal(self):
        cit = LawCitation(span=Span(0, 3, "§ 1"), id="x")
        d = to_dict(cit)
        assert d["type"] == "law"
        assert "structure" not in d  # empty tuple → not included
        assert "resolves_to" not in d

    def test_case_citation_minimal(self):
        cit = CaseCitation(span=Span(0, 5, "1 A 1"), id="y")
        d = to_dict(cit)
        assert d["type"] == "case"
        assert "court" not in d
        assert "date" not in d

    def test_dict_is_json_serializable(self):
        cit = LawCitation(
            span=Span(0, 10, "§ 433 BGB"),
            id="abc",
            book="bgb",
            number="433",
        )
        d = to_dict(cit)
        # Should not raise
        json.dumps(d)


class TestToJsonl:
    def test_basic(self):
        result = ExtractionResult(
            citations=[
                LawCitation(span=Span(0, 10, "§ 433 BGB"), id="c1", book="bgb", number="433"),
            ]
        )
        line = to_jsonl(result, doc_id="test_doc")
        parsed = json.loads(line)
        assert parsed["doc_id"] == "test_doc"
        assert len(parsed["citations"]) == 1
        assert parsed["citations"][0]["book"] == "bgb"

    def test_with_relations(self):
        result = ExtractionResult(
            citations=[
                LawCitation(span=Span(0, 10, "§ 1 BGB"), id="c1", book="bgb"),
                LawCitation(span=Span(20, 30, "§ 2 BGB"), id="c2", book="bgb"),
            ],
            relations=[
                CitationRelation(
                    source_id="c1",
                    target_id="c2",
                    relation="ivm",
                    span=Span(12, 18, "i.V.m."),
                ),
            ],
        )
        line = to_jsonl(result)
        parsed = json.loads(line)
        assert len(parsed["relations"]) == 1
        assert parsed["relations"][0]["relation"] == "ivm"
        assert parsed["relations"][0]["span"]["text"] == "i.V.m."

    def test_empty_result(self):
        line = to_jsonl(ExtractionResult())
        parsed = json.loads(line)
        assert parsed["citations"] == []
        assert parsed["relations"] == []

    def test_unicode_preserved(self):
        result = ExtractionResult(
            citations=[
                LawCitation(span=Span(0, 5, "§ 1 GÜ"), id="c1", book="gü"),
            ]
        )
        line = to_jsonl(result)
        assert "gü" in line  # Not escaped to \\u00fc

    def test_single_line(self):
        result = ExtractionResult(
            citations=[
                LawCitation(span=Span(0, 10, "§ 433 BGB"), id="c1"),
                CaseCitation(span=Span(15, 25, "10 C 23.12"), id="c2"),
            ]
        )
        line = to_jsonl(result)
        assert "\n" not in line


class TestToJson:
    def test_pretty_printed(self):
        result = ExtractionResult(
            citations=[
                LawCitation(span=Span(0, 10, "§ 433 BGB"), id="c1", book="bgb"),
            ]
        )
        output = to_json(result, doc_id="doc1")
        assert "\n" in output  # Multi-line
        parsed = json.loads(output)
        assert parsed["doc_id"] == "doc1"


class TestGoldenRoundTrip:
    def test_law_extraction_round_trip(self):
        text = "Gemäß § 433 Abs. 1 BGB ist der Käufer verpflichtet."
        ext = CitationExtractor()
        result = ext.extract(text)

        line = to_jsonl(result, doc_id="golden_1")
        parsed = json.loads(line)

        assert len(parsed["citations"]) >= 1
        cit = parsed["citations"][0]
        assert cit["type"] == "law"
        assert cit["span"]["text"] == text[cit["span"]["start"] : cit["span"]["end"]]

    def test_mixed_extraction_round_trip(self):
        text = "§ 154 VwGO (vgl. BVerwG, Az. 10 C 23.12)."
        ext = CitationExtractor()
        result = ext.extract(text)

        output = to_json(result, doc_id="golden_2")
        parsed = json.loads(output)

        for cit in parsed["citations"]:
            actual = text[cit["span"]["start"] : cit["span"]["end"]]
            assert actual == cit["span"]["text"], f"Span mismatch: {actual!r} != {cit['span']['text']!r}"

    def test_art_extraction_round_trip(self):
        text = "Gemäß Art. 12 Abs. 1 GG ist die Berufsfreiheit geschützt."
        ext = CitationExtractor()
        result = ext.extract(text)

        line = to_jsonl(result, doc_id="golden_3")
        parsed = json.loads(line)

        law_cits = [c for c in parsed["citations"] if c["type"] == "law"]
        assert len(law_cits) >= 1
        assert law_cits[0]["unit"] == "article"
        assert law_cits[0]["delimiter"] == "Art."
