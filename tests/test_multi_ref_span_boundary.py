"""A ``§§`` marker must stop at its own book code, not run on to a later one.

The ``multi`` pattern matches a bounded run of legal-reference characters after
``§§`` and then requires a book code. That run was greedy, so within its
200-character budget it reached the *farthest* book code rather than the
nearest -- swallowing whole clauses of prose, and merging genuinely separate
citations into one marker:

    §§ 2 bis 9 BauNVO für die darin beschriebenen Baugebiete ist die
    allgemeine Zweckbestimmung in § 10 BauNVO

Downstream that is one marker with eight references instead of two citations,
and the marker text stored for display is a sentence fragment. It also breaks
any consumer that keys on marker text: a scoping query looking for "§§ N und M"
matches these as a prefix, which is how a data-cleanup pass came to mis-scope
itself by several hundred documents.
"""

import pytest

from refex.document import make_document
from refex.engines.regex import RegexLawExtractor
from refex.orchestrator import CitationExtractor


def _spans(text: str) -> set[str]:
    extractor = CitationExtractor(engines=[RegexLawExtractor()])
    result = extractor.extract(make_document(f"<p>{text}</p>", fmt="html"))
    return {c.span.text for c in result.citations if type(c).__name__ == "LawCitation"}


class TestSpanStopsAtItsOwnBook:
    def test_prose_between_two_citations_is_not_swallowed(self):
        spans = _spans(
            "Anders als im jeweiligen Absatz 1 der §§ 2 bis 9 BauNVO für die "
            "darin beschriebenen Baugebiete ist die allgemeine Zweckbestimmung "
            "in § 10 BauNVO nicht geregelt."
        )
        assert spans == {"§§ 2 bis 9 BauNVO", "§ 10 BauNVO"}

    def test_two_books_stay_separate(self):
        spans = _spans(
            "Rechtsgrundlage in der aufgrund der §§ 4 und 142 GemO und der §§ 2 und 9 KAG 1996 erlassenen Satzung."
        )
        assert spans == {"§§ 4 und 142 GemO", "§§ 2 und 9 KAG"}

    def test_span_does_not_run_into_the_next_sentence(self):
        spans = _spans("Die nach §§ 10, 11 TKG zu überprüfen. Denn der Marktregulierung unterliegen nur solche Märkte.")
        assert spans == {"§§ 10, 11 TKG"}

    @pytest.mark.parametrize(
        "text",
        [
            "Anders als der §§ 2 bis 9 BauNVO ist die Zweckbestimmung in § 10 BauNVO offen.",
            "Nach §§ 4 und 142 GemO und der §§ 2 und 9 KAG gilt.",
        ],
    )
    def test_no_span_contains_a_sentence(self, text):
        """No marker may carry a run of prose words."""
        for span in _spans(text):
            assert len(span) <= 40, f"span looks like prose: {span!r}"


class TestOrdinaryMultiRefsUnchanged:
    """The narrowing must not cost ordinary enumerations."""

    @pytest.mark.parametrize(
        "text,expected",
        [
            ("Nach §§ 1, 2 und 3 BGB gilt.", {"§§ 1, 2 und 3 BGB"}),
            ("Nach §§ 664 bis 670 BGB gilt.", {"§§ 664 bis 670 BGB"}),
            ("Nach §§ 305, 307, 308 Nr. 1 BGB gilt.", {"§§ 305, 307, 308 Nr. 1 BGB"}),
            ("Nach §§ 6 und 7 IfSG gilt.", {"§§ 6 und 7 IfSG"}),
        ],
    )
    def test_enumeration_still_matches_whole(self, text, expected):
        assert _spans(text) == expected
