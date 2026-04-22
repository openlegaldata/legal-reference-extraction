"""Tests for the CRF citation extraction engine (Stream F).

These tests verify the feature extractor, BIO → span conversion, and
basic sanity of the trained model (if available).  Training itself is
not tested here (too slow, needs benchmark data).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from refex.engines.crf import (
    _parse_case_fields,
    _parse_law_fields,
    _word_shape,
    bio_to_spans,
    extract_features,
    text_to_features,
    tokenize,
)


class TestWordShape:
    def test_digits(self):
        assert _word_shape("123") == "ddd"
        assert _word_shape("2003") == "dddd"
        assert _word_shape("12345") == "dddd"  # capped at 4

    def test_upper(self):
        assert _word_shape("BGB") == "XX"
        assert _word_shape("ZPO") == "XX"

    def test_lower(self):
        assert _word_shape("vom") == "xx"

    def test_title(self):
        assert _word_shape("Urteil") == "Xx"

    def test_mixed(self):
        assert _word_shape("i.V.m.") == "other"


class TestTokenize:
    def test_simple(self):
        spans = tokenize("Das BGB regelt")
        assert len(spans) == 3
        assert spans[0] == (0, 3, "Das")
        assert spans[1] == (4, 7, "BGB")
        assert spans[2] == (8, 14, "regelt")

    def test_empty(self):
        assert tokenize("") == []

    def test_section_sign(self):
        spans = tokenize("§ 433 BGB")
        assert spans[0][2] == "§"
        assert spans[1][2] == "433"
        assert spans[2][2] == "BGB"


class TestExtractFeatures:
    def test_section_sign_feature(self):
        tokens = ["§", "433", "BGB"]
        features = extract_features(tokens, 0)
        assert features["word.is_section"] is True
        assert features["BOS"] is True
        assert features["next.isdigit"] is True

    def test_middle_token(self):
        tokens = ["§", "433", "BGB"]
        features = extract_features(tokens, 1)
        assert features["word.isdigit"] is True
        assert features["prev.is_section"] is True
        assert features["next.isupper"] is True

    def test_last_token(self):
        tokens = ["§", "433", "BGB"]
        features = extract_features(tokens, 2)
        assert features["word.isupper"] is True
        assert features["EOS"] is True

    def test_file_number_features(self):
        tokens = ["VIII", "ZR", "295/01"]
        features = extract_features(tokens, 2)
        assert features["word.has_slash"] is True
        assert features["word.looks_like_fn"] is True

    def test_art_feature(self):
        tokens = ["Art.", "12", "GG"]
        features = extract_features(tokens, 0)
        assert features["word.is_art"] is True

    def test_abs_feature(self):
        tokens = ["§", "1", "Abs.", "2", "BGB"]
        features = extract_features(tokens, 2)
        assert features["word.is_abs"] is True


class TestTextToFeatures:
    def test_feature_count_matches_tokens(self):
        text = "Gemäß § 433 BGB ist der Käufer verpflichtet."
        features, token_spans = text_to_features(text)
        assert len(features) == len(token_spans)

    def test_empty_text(self):
        features, token_spans = text_to_features("")
        assert features == []
        assert token_spans == []


class TestBioToSpans:
    def test_simple_span(self):
        text = "Gemäß § 433 BGB gilt."
        token_spans = tokenize(text)
        # tokens: "Gemäß", "§", "433", "BGB", "gilt."
        labels = ["O", "B-LAW_REF", "I-LAW_REF", "I-LAW_REF", "O"]
        spans = bio_to_spans(labels, token_spans, text)
        assert len(spans) == 1
        start, end, span_text, label = spans[0]
        assert label == "LAW_REF"
        assert "§ 433 BGB" in text[start:end]

    def test_multiple_spans(self):
        text = "§ 433 BGB und § 280 BGB"
        token_spans = tokenize(text)
        # tokens: "§", "433", "BGB", "und", "§", "280", "BGB"
        labels = ["B-LAW_REF", "I-LAW_REF", "I-LAW_REF", "O", "B-LAW_REF", "I-LAW_REF", "I-LAW_REF"]
        spans = bio_to_spans(labels, token_spans, text)
        assert len(spans) == 2

    def test_no_spans(self):
        text = "Kein Zitat hier."
        token_spans = tokenize(text)
        labels = ["O"] * len(token_spans)
        spans = bio_to_spans(labels, token_spans, text)
        assert spans == []

    def test_span_at_end(self):
        text = "bar § 433 BGB"
        token_spans = tokenize(text)
        # tokens: "bar", "§", "433", "BGB"
        labels = ["O", "B-LAW_REF", "I-LAW_REF", "I-LAW_REF"]
        spans = bio_to_spans(labels, token_spans, text)
        assert len(spans) == 1


class TestParseLawFields:
    def test_simple_law(self):
        book, number = _parse_law_fields("§ 433 BGB")
        assert book == "bgb"
        assert number == "433"

    def test_multi_section(self):
        book, number = _parse_law_fields("§§ 708 ZPO")
        assert book == "zpo"
        assert number == "708"

    def test_with_abs(self):
        book, number = _parse_law_fields("§ 433 Abs. 1 BGB")
        assert book == "bgb"
        assert number == "433"


class TestParseCaseFields:
    def test_file_number_only(self):
        court, fn = _parse_case_fields("VIII ZR 295/01")
        assert fn == "VIII ZR 295/01"

    def test_with_court(self):
        court, fn = _parse_case_fields("BGH, Urteil vom 12.03.2020 - VIII ZR 295/01")
        assert court is not None
        assert "BGH" in court
        assert fn == "VIII ZR 295/01"


class TestCRFExtractor:
    """Basic smoke test — only runs if the model is available."""

    _model_path = Path(__file__).parent.parent / "src" / "refex" / "data" / "crf_model.pkl"

    @pytest.fixture
    def extractor(self):
        if not self._model_path.exists():
            pytest.skip("CRF model not trained — run `make train-crf` first")
        from refex.engines.crf import CRFExtractor

        return CRFExtractor()

    def test_extract_returns_list(self, extractor):
        cits, rels = extractor.extract("Gemäß § 433 Abs. 1 BGB schuldet der Verkäufer.")
        assert isinstance(cits, list)
        assert isinstance(rels, list)

    def test_extract_empty_text(self, extractor):
        cits, rels = extractor.extract("")
        assert cits == []
        assert rels == []

    def test_extract_finds_law(self, extractor):
        cits, _ = extractor.extract(
            "Die Berufung ist gemäß §§ 511, 513 ZPO zulässig. Der Kläger hat gem. § 433 Abs. 1 BGB einen Anspruch."
        )
        # Should find at least one law citation
        law_cits = [c for c in cits if c.type == "law"]
        assert len(law_cits) >= 1

    def test_spans_are_valid(self, extractor):
        text = "Gemäß § 433 BGB schuldet der Verkäufer die Lieferung."
        cits, _ = extractor.extract(text)
        for c in cits:
            assert text[c.span.start : c.span.end] == c.span.text
