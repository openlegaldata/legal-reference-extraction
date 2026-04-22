"""Tests for output format adapters (D3-D7)."""

import json

from refex.citations import (
    STRUCTURE_KEYS,
    CaseCitation,
    ExtractionResult,
    LawCitation,
    Span,
)
from refex.orchestrator import CitationExtractor
from refex.serializers import (
    to_akn_ref,
    to_gliner,
    to_hf_bio,
    to_spacy_doc,
    to_web_annotation,
)

TEXT = "Gemäß § 433 BGB und BVerwG 10 C 23.12 ist das klar."

RESULT = ExtractionResult(
    citations=[
        LawCitation(
            span=Span(6, 15, "§ 433 BGB"), id="law1", book="bgb", number="433", unit="paragraph", delimiter="§"
        ),
        CaseCitation(span=Span(20, 37, "BVerwG 10 C 23.12"), id="case1", court="BVerwG", file_number="10 C 23.12"),
    ]
)


class TestSpacyDoc:
    def test_basic_structure(self):
        doc = to_spacy_doc(RESULT, TEXT)
        assert doc["text"] == TEXT
        assert "tokens" in doc
        assert len(doc["tokens"]) > 0
        assert "spans" in doc
        assert "citations" in doc["spans"]

    def test_span_labels(self):
        doc = to_spacy_doc(RESULT, TEXT)
        spans = doc["spans"]["citations"]
        assert len(spans) == 2
        assert spans[0]["label"] == "LAW_REF"
        assert spans[1]["label"] == "CASE_REF"

    def test_span_token_indices(self):
        doc = to_spacy_doc(RESULT, TEXT)
        spans = doc["spans"]["citations"]
        tokens = doc["tokens"]
        # First span covers "§ 433 BGB" — 3 tokens
        s0 = spans[0]
        assert s0["start_token"] >= 0
        assert s0["end_token"] > s0["start_token"]
        # Reconstruct text from tokens
        span_tokens = tokens[s0["start_token"] : s0["end_token"]]
        assert len(span_tokens) == 3  # §, 433, BGB

    def test_kb_id(self):
        doc = to_spacy_doc(RESULT, TEXT)
        spans = doc["spans"]["citations"]
        assert spans[0]["kb_id"] == "law1"
        assert spans[1]["kb_id"] == "case1"

    def test_empty_result(self):
        doc = to_spacy_doc(ExtractionResult(), "Kein Verweis hier.")
        assert doc["spans"]["citations"] == []

    def test_is_json_serializable(self):
        doc = to_spacy_doc(RESULT, TEXT)
        json.dumps(doc)  # Should not raise


class TestHfBio:
    def test_basic_structure(self):
        bio = to_hf_bio(RESULT, TEXT)
        assert "tokens" in bio
        assert "ner_tags" in bio
        assert len(bio["tokens"]) == len(bio["ner_tags"])

    def test_bio_labels(self):
        bio = to_hf_bio(RESULT, TEXT)
        tags = bio["ner_tags"]
        tokens = bio["tokens"]
        # Find the § token
        idx_sect = tokens.index("§")
        assert tags[idx_sect] == "B-LAW_REF"
        assert tags[idx_sect + 1] == "I-LAW_REF"  # 433
        assert tags[idx_sect + 2] == "I-LAW_REF"  # BGB

    def test_o_tags(self):
        bio = to_hf_bio(RESULT, TEXT)
        # First token "Gemäß" should be O
        assert bio["ner_tags"][0] == "O"

    def test_case_bio_labels(self):
        bio = to_hf_bio(RESULT, TEXT)
        tags = bio["ner_tags"]
        tokens = bio["tokens"]
        # "BVerwG" should start with B-CASE_REF
        idx_bverwg = tokens.index("BVerwG")
        assert tags[idx_bverwg] == "B-CASE_REF"

    def test_empty_result(self):
        bio = to_hf_bio(ExtractionResult(), "Einfacher Text hier.")
        assert all(t == "O" for t in bio["ner_tags"])

    def test_round_trip_with_extractor(self):
        text = "§ 1 BGB und § 2 BGB sind wichtig."
        ext = CitationExtractor()
        result = ext.extract(text)
        bio = to_hf_bio(result, text)
        # At least some B- tags must exist
        assert any(t.startswith("B-") for t in bio["ner_tags"])


class TestGliner:
    def test_basic(self):
        spans = to_gliner(RESULT)
        assert len(spans) == 2

    def test_span_fields(self):
        spans = to_gliner(RESULT)
        for s in spans:
            assert "start" in s
            assert "end" in s
            assert "label" in s
            assert "text" in s

    def test_labels(self):
        spans = to_gliner(RESULT)
        assert spans[0]["label"] == "LAW_REF"
        assert spans[1]["label"] == "CASE_REF"

    def test_offsets(self):
        spans = to_gliner(RESULT)
        assert spans[0]["start"] == 6
        assert spans[0]["end"] == 15
        assert spans[0]["text"] == "§ 433 BGB"

    def test_empty(self):
        assert to_gliner(ExtractionResult()) == []

    def test_text_slice_matches(self):
        spans = to_gliner(RESULT)
        for s in spans:
            assert TEXT[s["start"] : s["end"]] == s["text"]


class TestWebAnnotation:
    def test_basic(self):
        annos = to_web_annotation(RESULT, source_uri="urn:doc:test")
        assert len(annos) == 2

    def test_context(self):
        annos = to_web_annotation(RESULT)
        for a in annos:
            assert a["@context"] == "http://www.w3.org/ns/anno.jsonld"
            assert a["type"] == "Annotation"

    def test_selector(self):
        annos = to_web_annotation(RESULT)
        sel = annos[0]["target"]["selector"]
        assert sel["type"] == "TextPositionSelector"
        assert sel["start"] == 6
        assert sel["end"] == 15

    def test_body_tag(self):
        annos = to_web_annotation(RESULT)
        assert annos[0]["body"]["value"] == "LAW_REF"
        assert annos[1]["body"]["value"] == "CASE_REF"

    def test_source_uri(self):
        annos = to_web_annotation(RESULT, source_uri="https://example.com/doc/1")
        assert annos[0]["target"]["source"] == "https://example.com/doc/1"

    def test_properties_present(self):
        annos = to_web_annotation(RESULT)
        props = annos[0]["body"]["properties"]
        assert props["type"] == "law"
        assert props["book"] == "bgb"

    def test_is_json_serializable(self):
        annos = to_web_annotation(RESULT)
        json.dumps(annos)  # Should not raise


class TestAknRef:
    def test_basic(self):
        xml = to_akn_ref(RESULT, TEXT)
        assert "<ref " in xml
        assert "</ref>" in xml

    def test_law_href(self):
        xml = to_akn_ref(RESULT, TEXT)
        assert 'href="/akn/de/act/bgb/~433"' in xml

    def test_case_href(self):
        xml = to_akn_ref(RESULT, TEXT)
        assert 'href="/akn/de/judgment/BVerwG/10 C 23.12"' in xml

    def test_ref_text_preserved(self):
        xml = to_akn_ref(RESULT, TEXT)
        assert "§ 433 BGB" in xml
        assert "BVerwG 10 C 23.12" in xml

    def test_surrounding_text_preserved(self):
        xml = to_akn_ref(RESULT, TEXT)
        assert "Gemäß" in xml
        assert "ist das klar." in xml

    def test_empty(self):
        xml = to_akn_ref(ExtractionResult(), "Kein Verweis.")
        assert xml == "Kein Verweis."

    def test_xml_escaping(self):
        result = ExtractionResult(
            citations=[
                LawCitation(span=Span(0, 5, "§ <1>"), id="a&b", book="test"),
            ]
        )
        xml = to_akn_ref(result, "§ <1> test")
        assert "&lt;" in xml
        assert "&amp;" in xml


class TestStructureKeys:
    def test_standard_keys_present(self):
        for key in ("absatz", "satz", "nummer", "halbsatz", "buchstabe"):
            assert key in STRUCTURE_KEYS

    def test_extended_keys_present(self):
        for key in ("buch", "teil", "kapitel", "abschnitt", "anlage"):
            assert key in STRUCTURE_KEYS

    def test_is_frozenset(self):
        assert isinstance(STRUCTURE_KEYS, frozenset)

    def test_no_empty_keys(self):
        assert "" not in STRUCTURE_KEYS
        assert all(k.strip() == k for k in STRUCTURE_KEYS)
