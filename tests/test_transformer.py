"""Tests for the transformer-based citation engine (Stream G).

These tests verify the label-mapping layer, sub-word → word alignment,
and the Extractor protocol — without running a full model (which
requires downloading large weights and GPU/MPS).

Model-requiring tests are marked ``@pytest.mark.slow`` and skipped by
default; run them with ``pytest -m slow`` when you have the model
available.
"""

from __future__ import annotations

import pytest

from refex.engines.transformer import (
    DEFAULT_LABEL_MAP,
    _spans_to_citations,
    _whitespace_tokenize,
    _word_labels_to_spans,
)


class TestWhitespaceTokenize:
    def test_simple(self):
        spans = _whitespace_tokenize("Gemäß § 433 BGB")
        assert len(spans) == 4
        assert spans[0] == (0, 5, "Gemäß")
        assert spans[1] == (6, 7, "§")

    def test_empty(self):
        assert _whitespace_tokenize("") == []

    def test_multiple_spaces(self):
        # Multiple spaces between tokens
        spans = _whitespace_tokenize("a   b")
        assert len(spans) == 2


class TestDefaultLabelMap:
    def test_canonical_passthrough(self):
        assert DEFAULT_LABEL_MAP["B-LAW_REF"] == "B-LAW_REF"
        assert DEFAULT_LABEL_MAP["I-CASE_REF"] == "I-CASE_REF"
        assert DEFAULT_LABEL_MAP["O"] == "O"

    def test_common_variants(self):
        # German legal NER variants
        assert DEFAULT_LABEL_MAP["B-LAW"] == "B-LAW_REF"
        assert DEFAULT_LABEL_MAP["B-GS"] == "B-LAW_REF"
        assert DEFAULT_LABEL_MAP["B-AZ"] == "B-CASE_REF"
        assert DEFAULT_LABEL_MAP["I-RS"] == "I-CASE_REF"


class TestWordLabelsToSpans:
    def test_single_law_span(self):
        text = "Gemäß § 433 BGB gilt."
        word_offsets = _whitespace_tokenize(text)
        # words: Gemäß, §, 433, BGB, gilt.
        labels = ["O", "B-LAW_REF", "I-LAW_REF", "I-LAW_REF", "O"]
        spans = _word_labels_to_spans(labels, word_offsets, text, DEFAULT_LABEL_MAP)
        assert len(spans) == 1
        start, end, span_text, label = spans[0]
        assert label == "LAW_REF"
        assert span_text == "§ 433 BGB"

    def test_multiple_spans(self):
        text = "§ 1 BGB und § 2 BGB"
        word_offsets = _whitespace_tokenize(text)
        labels = ["B-LAW_REF", "I-LAW_REF", "I-LAW_REF", "O", "B-LAW_REF", "I-LAW_REF", "I-LAW_REF"]
        spans = _word_labels_to_spans(labels, word_offsets, text, DEFAULT_LABEL_MAP)
        assert len(spans) == 2

    def test_label_mapping_applied(self):
        """Labels from the model (B-GS, B-AZ) are normalised via label_mapping."""
        text = "Gemäß § 433 BGB und VIII ZR 295/01"
        word_offsets = _whitespace_tokenize(text)
        # Model emits non-canonical labels (B-GS for law, B-AZ for case)
        labels = ["O", "B-GS", "I-GS", "I-GS", "O", "B-AZ", "I-AZ", "I-AZ"]
        spans = _word_labels_to_spans(labels, word_offsets, text, DEFAULT_LABEL_MAP)
        types = [s[3] for s in spans]
        assert "LAW_REF" in types
        assert "CASE_REF" in types

    def test_span_at_end(self):
        text = "vgl § 5 BGB"
        word_offsets = _whitespace_tokenize(text)
        labels = ["O", "B-LAW_REF", "I-LAW_REF", "I-LAW_REF"]
        spans = _word_labels_to_spans(labels, word_offsets, text, DEFAULT_LABEL_MAP)
        assert len(spans) == 1

    def test_unknown_label_treated_as_O(self):
        text = "§ 1 BGB foo"
        word_offsets = _whitespace_tokenize(text)
        # "B-UNKNOWN" is not in DEFAULT_LABEL_MAP → treated as O, span closes
        labels = ["B-LAW_REF", "I-LAW_REF", "I-LAW_REF", "B-UNKNOWN"]
        spans = _word_labels_to_spans(labels, word_offsets, text, DEFAULT_LABEL_MAP)
        assert len(spans) == 1  # only the law span
        assert spans[0][3] == "LAW_REF"


class TestSpansToCitations:
    def test_law_citation(self):
        spans = [(6, 15, "§ 433 BGB", "LAW_REF")]
        cits = _spans_to_citations(spans)
        assert len(cits) == 1
        assert cits[0].type == "law"
        assert cits[0].book == "bgb"
        assert cits[0].number == "433"

    def test_case_citation(self):
        spans = [(0, 14, "VIII ZR 295/01", "CASE_REF")]
        cits = _spans_to_citations(spans)
        assert len(cits) == 1
        assert cits[0].type == "case"
        assert cits[0].file_number == "VIII ZR 295/01"

    def test_unknown_label_skipped(self):
        spans = [(0, 5, "foo", "UNKNOWN_REF")]
        cits = _spans_to_citations(spans)
        assert cits == []

    def test_multiple_citations(self):
        spans = [
            (0, 9, "§ 433 BGB", "LAW_REF"),
            (20, 34, "VIII ZR 295/01", "CASE_REF"),
        ]
        cits = _spans_to_citations(spans)
        assert len(cits) == 2
        assert cits[0].type == "law"
        assert cits[1].type == "case"

    def test_confidence_is_set(self):
        spans = [(0, 9, "§ 433 BGB", "LAW_REF")]
        cits = _spans_to_citations(spans)
        assert cits[0].confidence == 0.85


@pytest.mark.slow
class TestTransformerExtractor:
    """Integration tests that require downloading the transformer model.

    Run with: pytest -m slow
    """

    def test_extract_law(self):
        from refex.engines.transformer import TransformerExtractor

        ext = TransformerExtractor()
        cits, _ = ext.extract("Gemäß § 433 Abs. 1 BGB schuldet der Verkäufer.")
        law_cits = [c for c in cits if c.type == "law"]
        assert len(law_cits) >= 1

    def test_extract_empty(self):
        from refex.engines.transformer import TransformerExtractor

        ext = TransformerExtractor()
        cits, rels = ext.extract("")
        assert cits == []
        assert rels == []

    def test_batch_extract(self):
        from refex.engines.transformer import TransformerExtractor

        ext = TransformerExtractor()
        results = ext.extract_batch(
            ["Gemäß § 433 BGB gilt.", "Vgl. BGH, VIII ZR 295/01."],
            batch_size=2,
        )
        assert len(results) == 2
        for cits, _ in results:
            assert isinstance(cits, list)

    def test_spans_are_valid(self):
        from refex.engines.transformer import TransformerExtractor

        ext = TransformerExtractor()
        text = "Gemäß § 433 BGB schuldet der Verkäufer die Lieferung."
        cits, _ = ext.extract(text)
        for c in cits:
            assert text[c.span.start : c.span.end] == c.span.text
