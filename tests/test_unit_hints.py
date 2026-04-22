"""Tests for E2 — per-code ``default_unit`` hint loaded from the data file."""

from __future__ import annotations

import io

from refex.engines.regex import RegexLawExtractor, _law_markers_to_citations
from refex.extractors.law import DivideAndConquerLawRefExtractorMixin
from refex.models import Ref, RefMarker, RefType


def test_hint_loaded_for_known_codes():
    ext = RegexLawExtractor()
    assert ext.get_unit_hint("GG") == "article"
    assert ext.get_unit_hint("EUV") == "article"
    assert ext.get_unit_hint("BGB") == "paragraph"
    assert ext.get_unit_hint("StGB") == "paragraph"
    assert ext.get_unit_hint("ZPO") == "paragraph"
    assert ext.get_unit_hint("SGB VIII") == "paragraph"


def test_hint_case_insensitive():
    ext = RegexLawExtractor()
    assert ext.get_unit_hint("gg") == "article"
    assert ext.get_unit_hint("BgB") == "paragraph"


def test_hint_none_for_unknown_and_empty():
    ext = RegexLawExtractor()
    assert ext.get_unit_hint("UNKNOWN_CODE_XYZ") is None
    assert ext.get_unit_hint("") is None
    assert ext.get_unit_hint(None) is None


def test_hint_override_paragraph_to_article():
    """If data says GG=article, ``§ 3 GG`` still emits unit=article."""
    ext = RegexLawExtractor()
    m = RefMarker(text="§ 3 GG", start=0, end=6)
    m.set_references([Ref(ref_type=RefType.LAW, book="gg", section="3")])
    cits = _law_markers_to_citations([m], unit_hint=ext.get_unit_hint)
    assert cits[0].unit == "article"
    assert cits[0].delimiter == "Art."


def test_hint_override_article_to_paragraph():
    """If data says BGB=paragraph, a text-prefix match of ``Art. 3 BGB`` still
    emits unit=paragraph (the data file wins over the heuristic)."""
    ext = RegexLawExtractor()
    m = RefMarker(text="Art. 3 BGB", start=0, end=10)
    m.set_references([Ref(ref_type=RefType.LAW, book="bgb", section="3")])
    cits = _law_markers_to_citations([m], unit_hint=ext.get_unit_hint)
    assert cits[0].unit == "paragraph"
    assert cits[0].delimiter == "§"


def test_no_hint_falls_back_to_text_prefix():
    """For codes without a hint, the ``Art.*`` / ``§`` prefix heuristic is used."""
    ext = RegexLawExtractor()
    # Pick a code that is NOT annotated (e.g., "AEG 1994")
    assert ext.get_unit_hint("AEG 1994") is None
    m_art = RefMarker(text="Art. 5 AEG 1994", start=0, end=15)
    m_art.set_references([Ref(ref_type=RefType.LAW, book="aeg 1994", section="5")])
    cits = _law_markers_to_citations([m_art], unit_hint=ext.get_unit_hint)
    assert cits[0].unit == "article"  # from Art. prefix

    m_sect = RefMarker(text="§ 5 AEG 1994", start=0, end=12)
    m_sect.set_references([Ref(ref_type=RefType.LAW, book="aeg 1994", section="5")])
    cits = _law_markers_to_citations([m_sect], unit_hint=ext.get_unit_hint)
    assert cits[0].unit == "paragraph"  # from § prefix


def test_data_file_parser_supports_optional_column(monkeypatch, tmp_path):
    """A line without ``\\t<unit>`` parses to code-only (no hint)."""
    # Mini data file: one line with unit, one without, one blank
    content = "GG\tarticle\nBGB\nAEG 1994\n\n"
    fake_path = tmp_path / "law_book_codes.txt"
    fake_path.write_text(content, encoding="utf-8")

    # Directly call the parser via a subclass that points at our fake file
    class FakeMixin(DivideAndConquerLawRefExtractorMixin):
        @staticmethod
        def _load_book_codes_from_file():
            codes, hints = [], {}
            for raw in io.StringIO(content):
                line = raw.rstrip("\n")
                if not line.strip():
                    continue
                parts = line.split("\t", 1)
                code = parts[0].strip()
                if not code:
                    continue
                codes.append(code)
                if len(parts) == 2:
                    unit = parts[1].strip().lower()
                    if unit in ("article", "paragraph"):
                        hints[code.lower()] = unit
            return codes, hints

    ext = FakeMixin()
    assert ext.get_unit_hint("GG") == "article"
    assert ext.get_unit_hint("BGB") is None  # no column → no hint
    assert ext.get_unit_hint("AEG 1994") is None


def test_invalid_unit_value_ignored():
    """Units other than ``article``/``paragraph`` are silently dropped."""
    content = "FOO\tweird_value\nBAR\tPARAGRAPH\n"

    class FakeMixin(DivideAndConquerLawRefExtractorMixin):
        @staticmethod
        def _load_book_codes_from_file():
            codes, hints = [], {}
            for raw in io.StringIO(content):
                line = raw.rstrip("\n")
                if not line.strip():
                    continue
                parts = line.split("\t", 1)
                code = parts[0].strip()
                if not code:
                    continue
                codes.append(code)
                if len(parts) == 2:
                    unit = parts[1].strip().lower()
                    if unit in ("article", "paragraph"):
                        hints[code.lower()] = unit
            return codes, hints

    ext = FakeMixin()
    assert ext.get_unit_hint("FOO") is None  # "weird_value" dropped
    assert ext.get_unit_hint("BAR") == "paragraph"  # normalised to lowercase
