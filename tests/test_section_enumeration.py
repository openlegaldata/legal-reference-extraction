"""``§§ X bis Y`` is a range; ``§§ X und Y`` is two sections.

Conflating them expanded "§§ 627 und 1300" into 674 citations, 672 of which
named sections that were never cited. Production accumulated markers holding
618-862 rows this way.

Ranges are additionally capped. Table-of-contents markup puts a section number
beside an unrelated number, producing spans such as "§§ 154 bis 16617" against
a code with roughly 200 sections -- 16,464 citations from one marker, which
rendered a law page at 7.4 MB and timed it out.
"""

import pytest

from refex.document import make_document
from refex.engines.regex import RegexLawExtractor
from refex.extractors.law import DivideAndConquerLawRefExtractorMixin
from refex.orchestrator import CitationExtractor


def _numbers(text: str, book: str = "bgb") -> list[str]:
    engine = RegexLawExtractor()
    engine.law_book_context = book
    extractor = CitationExtractor(engines=[engine])
    result = extractor.extract(make_document(f"<p>{text}</p>", fmt="html"))
    return [c.number for c in result.citations if type(c).__name__ == "LawCitation"]


class TestUndIsNotARange:
    def test_und_names_exactly_two_sections(self):
        assert _numbers("Nach §§ 627 und 1300 gilt.") == ["627", "1300"]

    def test_und_with_adjacent_numbers(self):
        assert _numbers("Nach §§ 91 und 92 gilt.") == ["91", "92"]

    @pytest.mark.parametrize(
        "text",
        [
            "Nach §§ 1693 und 1846 gilt.",
            "Nach §§ 91 und 708 gilt.",
            "Nach §§ 1507 und 2368 gilt.",
        ],
    )
    def test_production_und_markers_yield_two(self, text):
        """The exact markers that accumulated 154-862 rows in production."""
        assert len(_numbers(text)) == 2


class TestBisStillExpands:
    def test_small_range(self):
        assert _numbers("Nach §§ 664 bis 670 gilt.") == [
            "664",
            "665",
            "666",
            "667",
            "668",
            "669",
            "670",
        ]

    def test_legitimate_wide_block_citation(self):
        """§§ 253 bis 591 ZPO is Book 2 -- 339 sections, genuinely cited."""
        assert len(_numbers("Nach §§ 253 bis 591 gilt.")) == 339

    def test_range_at_the_cap(self):
        cap = DivideAndConquerLawRefExtractorMixin.MAX_RANGE_EXPANSION
        assert len(_numbers(f"Nach §§ 1 bis {cap} gilt.")) == cap


class TestOversizedRangeIsCapped:
    def test_beyond_the_cap_emits_endpoints_only(self):
        cap = DivideAndConquerLawRefExtractorMixin.MAX_RANGE_EXPANSION
        nums = _numbers(f"Nach §§ 1 bis {cap + 1} gilt.")
        assert nums == ["1", str(cap + 1)]

    def test_production_toc_misparse(self):
        """The marker that took a law page down: 16,464 citations -> 2."""
        assert _numbers("Nach §§ 154 bis 16617 gilt.") == ["154", "16617"]

    def test_oversized_range_is_logged(self, caplog):
        with caplog.at_level("WARNING", logger="refex.extractors.law"):
            _numbers("Nach §§ 154 bis 16617 gilt.")
        assert any("16617" in r.getMessage() for r in caplog.records)


class TestBookAlignment:
    def test_book_list_matches_section_list(self):
        """A mismatch would raise IndexError or silently mis-pair books."""
        for text in (
            "Nach §§ 627 und 1300 gilt.",
            "Nach §§ 664 bis 670 gilt.",
            "Nach §§ 154 bis 16617 gilt.",
        ):
            assert _numbers(text)  # no IndexError from zip/enumerate
