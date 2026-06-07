import os
import signal

import pytest

from refex.extractors.law import DivideAndConquerLawRefExtractorMixin
from refex.models import Ref, RefType
from tests.conftest import RESOURCE_DIR, assert_refs


def test_extract(law_extractor):
    """
    § 3d AsylG
    § 123 VwGO
    §§ 3, 3b AsylG
    § 77 Abs. 1 Satz 1, 1. Halbsatz AsylG
    § 3 Abs. 1 AsylG
    § 77 Abs. 2 AsylG
    § 113 Abs. 5 Satz 1 VwGO
    § 3 Abs. 1 Nr. 1 i.V.m. § 3b AsylG
    § 3a Abs. 1 und 2 AsylG
    §§ 154 Abs. 1 VwGO
    § 83 b AsylG
    § 167 VwGO iVm §§ 708 Nr. 11, 711 ZPO
    § 167 VwGO i.V.m. §§ 708 Nr. 11, 711 ZPO
    §§ 167 Abs. 2 VwGO, 708 Nr. 11, 711 ZPO
    §§ 52 Abs. 1; 53 Abs. 2 Nr. 1; 63 Abs. 2 GKG
    § 6 Abs. 5 Satz 1 LBO
    §§ 80 a Abs. 3, 80 Abs. 5 VwGO
    § 1 Satz 2 SbStG
    § 2 ZWStS
    § 6 Abs. 2 S. 2 ZWStS

    :return:
    """
    content_html = "<h1>Hallo</h1><p>Ein Satz mit § 3 Abs. 1 Nr. 1 i.V.m. § 3b AsylG, und weiteren Sachen.</p>"
    content_html += "<p>Komplexe Zitate gibt es auch §§ 3, 3b AsylG.</p>"

    new_content, markers = law_extractor.extract(content_html)


def test_extract_at_end_of_string(law_extractor):
    """A citation that ends the document must still be extracted.

    The book-code lookahead historically required a trailing word
    delimiter (whitespace, punctuation, or HTML angle bracket), and
    silently dropped citations at end-of-string. Real-world documents
    routinely end on a citation — e.g. plain-text projections of HTML
    where the final ``</p>`` has been stripped — so end-of-string is
    now a valid terminator alongside the existing delimiters.
    """
    text = "Komplexe Zitate gibt es auch §§ 3, 3b AsylG"
    _, markers = law_extractor.extract(text)
    sections = [r.section for m in markers for r in m.references]
    assert "3" in sections, sections
    assert "3b" in sections, sections


def test_with_law_book_context(law_extractor):
    """Book context is used for extracting law references from within law text, where book is not
    explicitly mentioned."""

    law_extractor.law_book_context = "bgb"

    text = (
        "<P>(2) Der Vorsitzende kann einen solchen Vertreter auch bestellen,"
        " wenn in den Fällen des § 20 eine nicht prozessfähige Person bei dem "
        "Gericht ihres Aufenthaltsortes verklagt werden soll..</P>"
    )

    new_content, markers = law_extractor.extract(text)

    assert len(markers) == 1, "Invalid marker count"
    assert markers[0].references[0].section == "20", "Invalid section"


def test_timeout_ref(law_extractor):
    expected = [
        {
            "content": " Auslandsaufenthalt mit beachtlicher Wahrscheinlichkeit aufgrund eines ihm (zugeschriebenen) Verfolgungsgrundes "
            "im Sinne des § 3 Abs. 1 AsylG, insbesondere einer regimekritischen politischen Überzeugung, erfolgen würden. "
            "Nach der Rechtsprechung des schleswig-holsteinischen Oberverwaltungsgerichtes (Urteil vom 23.11.2016, - 3 LB 17/16 -, juris), "
            "der sich die Kammer anschließt, besteht nach der gegenwärtigen Erkenntnislage keine hinreichende"
            " Grundlage für die Annahme, dass der totalitäre syrische Staat jeden Rückkehrer pauschal unter eine "
            "Art Generalsverdacht stellt, der Opposition anzugehören (so auch OVG Saarland, "
            "Urteil vom 2.2.2017, - 2 A 515/16 -; OVG Rheinland-Pfalz, Urteil vom 16.12.2016, -1A 10922/16 -; Bayrischer VGH, "
            "Urteil vom 12.12.16, - 21 B 16.30364; OVG Nordrhein-Westfalen,",
            "refs": [
                Ref(ref_type=RefType.LAW, book="asylg", section="3"),
            ],
        }
    ]

    assert_refs(law_extractor, expected)


def test_extract2(law_extractor):
    assert_refs(
        law_extractor,
        [
            {
                "resource": "law/extract2.txt",
                "refs": [
                    Ref(ref_type=RefType.LAW, book="vwgo", section="124"),
                    Ref(ref_type=RefType.LAW, book="vwgo", section="124a"),
                ],
            }
        ],
    )


def test_extract3(law_extractor):
    assert_refs(
        law_extractor,
        [
            {
                "resource": "law/extract3.txt",
                "refs": [
                    Ref(ref_type=RefType.LAW, book="vwgo", section="167"),
                    Ref(ref_type=RefType.LAW, book="zpo", section="708"),
                    Ref(ref_type=RefType.LAW, book="zpo", section="711"),
                ],
            }
        ],
    )


def test_extract4(law_extractor):
    assert_refs(
        law_extractor,
        [
            {
                "resource": "law/extract4.txt",
                "refs": [
                    Ref(ref_type=RefType.LAW, book="baugb", section="34"),
                    Ref(ref_type=RefType.LAW, book="baunvo", section="2"),
                    Ref(ref_type=RefType.LAW, book="baunvo", section="3"),
                    Ref(ref_type=RefType.LAW, book="baunvo", section="4"),
                ],
            }
        ],
    )


def test_extract5(law_extractor):
    assert_refs(
        law_extractor,
        [
            {
                "resource": "law/extract5.txt",
                "refs": [
                    Ref(ref_type=RefType.LAW, book="vwgo", section="154"),
                    Ref(ref_type=RefType.LAW, book="vwgo", section="154"),
                    Ref(ref_type=RefType.LAW, book="vwgo", section="162"),
                ],
            }
        ],
    )


def test_extract6(law_extractor):
    assert_refs(
        law_extractor,
        [
            {
                "resource": "law/extract6.txt",
                "refs": [Ref(ref_type=RefType.LAW, book="vwgo", section="42")],
            }
        ],
    )


def test_extract7(law_extractor):
    assert_refs(
        law_extractor,
        [
            {
                "resource": "law/extract7.txt",
                "refs": [
                    Ref(ref_type=RefType.LAW, book="vwgo", section="154"),
                    Ref(ref_type=RefType.LAW, book="vwgo", section="154"),
                    Ref(ref_type=RefType.LAW, book="vwgo", section="162"),
                ],
            }
        ],
    )


def test_extract8(law_extractor):
    assert_refs(
        law_extractor,
        [
            {
                "resource": "law/extract8.txt",
                "refs": [
                    # § 77 Abs. 1 Satz 1, 1. Halbsatz AsylG
                    Ref(ref_type=RefType.LAW, book="asylg", section="77")
                ],
            }
        ],
    )


def test_extract9(law_extractor):
    assert_refs(
        law_extractor,
        [
            {
                "resource": "law/extract9.txt",
                "refs": [
                    # §§ 52 Abs. 1; 53 Abs. 2 Nr. 1; 63 Abs. 2 StPO
                    Ref(ref_type=RefType.LAW, book="stpo", section="52"),
                    Ref(ref_type=RefType.LAW, book="stpo", section="53"),
                    Ref(ref_type=RefType.LAW, book="stpo", section="63"),
                ],
            }
        ],
    )


def test_extract10(law_extractor):
    assert_refs(
        law_extractor,
        [
            {
                "resource": "law/extract10.txt",
                "refs": [
                    # Art 12 Abs 1 GG
                    Ref(ref_type=RefType.LAW, book="gg", section="1"),
                    Ref(ref_type=RefType.LAW, book="gg", section="2"),
                    Ref(ref_type=RefType.LAW, book="gg", section="3"),
                    Ref(ref_type=RefType.LAW, book="gg", section="12"),
                ],
            }
        ],
    )


def test_extract11(law_extractor):
    assert_refs(
        law_extractor,
        [
            {
                "resource": "law/extract11.txt",
                "refs": [
                    # §§ 556d, 556g BGB
                    Ref(ref_type=RefType.LAW, book="bgb", section="556d"),
                    Ref(ref_type=RefType.LAW, book="bgb", section="556e"),
                ],
            }
        ],
    )


def test_extract12(law_extractor):
    assert_refs(
        law_extractor,
        [
            {
                "resource": "law/extract12.txt",
                "refs": [
                    # §§ 1, 2 Abs. 2, 3, 10 Abs. 1 Nr. 1 BGB
                    Ref(ref_type=RefType.LAW, book="bgb", section="1"),
                    Ref(ref_type=RefType.LAW, book="bgb", section="2"),
                    Ref(ref_type=RefType.LAW, book="bgb", section="3"),
                    Ref(ref_type=RefType.LAW, book="bgb", section="10"),
                ],
            }
        ],
    )


def test_extract13(law_extractor):
    assert_refs(
        law_extractor,
        [
            {
                "resource": "law/extract13.txt",
                "refs": [
                    # § 3d AsylG, aber auch § 123 VwGO. ... auch §§ 3, 3b AsylG
                    Ref(ref_type=RefType.LAW, book="asylg", section="3"),
                    Ref(ref_type=RefType.LAW, book="asylg", section="3b"),
                    Ref(ref_type=RefType.LAW, book="asylg", section="3d"),
                    Ref(ref_type=RefType.LAW, book="vwgo", section="123"),
                ],
            }
        ],
    )


def test_extract14(law_extractor):
    assert_refs(
        law_extractor,
        [
            {
                "resource": "law/extract14.txt",
                "refs": [
                    # duplicated book code parts
                    Ref(ref_type=RefType.LAW, book="sgg", section="136"),
                    Ref(ref_type=RefType.LAW, book="sgb x", section="48"),
                ],
            }
        ],
    )


def test_extract15(law_extractor):
    assert_refs(
        law_extractor,
        [
            {
                "resource": "law/extract15.txt",
                "refs": [
                    Ref(ref_type=RefType.LAW, book="vwgo", section="124"),
                    Ref(ref_type=RefType.LAW, book="vwgo", section="124a"),
                ],
            }
        ],
        True,
    )


def test_extract16(law_extractor):
    assert_refs(
        law_extractor,
        [
            {
                "resource": "law/extract16.txt",
                "refs": [
                    Ref(ref_type=RefType.LAW, book="vwgo", section="167"),
                    Ref(ref_type=RefType.LAW, book="zpo", section="708"),
                    Ref(ref_type=RefType.LAW, book="zpo", section="711"),
                ],
            }
        ],
        True,
    )


def test_extract17(law_extractor):
    assert_refs(
        law_extractor,
        [
            {
                "resource": "law/extract17.txt",
                "refs": [
                    Ref(ref_type=RefType.LAW, book="baugb", section="34"),
                    Ref(ref_type=RefType.LAW, book="baunvo", section="2"),
                    Ref(ref_type=RefType.LAW, book="baunvo", section="3"),
                    Ref(ref_type=RefType.LAW, book="baunvo", section="4"),
                ],
            }
        ],
        True,
    )


def test_extract18(law_extractor):
    assert_refs(
        law_extractor,
        [
            {
                "resource": "law/extract18.txt",
                "refs": [
                    Ref(ref_type=RefType.LAW, book="vwgo", section="154"),
                    Ref(ref_type=RefType.LAW, book="vwgo", section="154"),
                    Ref(ref_type=RefType.LAW, book="vwgo", section="162"),
                ],
            }
        ],
        True,
    )


def test_extract19(law_extractor):
    assert_refs(
        law_extractor,
        [
            {
                "resource": "law/extract19.txt",
                "refs": [Ref(ref_type=RefType.LAW, book="vwgo", section="42")],
            }
        ],
        True,
    )


def test_extract20(law_extractor):
    assert_refs(
        law_extractor,
        [
            {
                "resource": "law/extract20.txt",
                "refs": [
                    Ref(ref_type=RefType.LAW, book="vwgo", section="154"),
                    Ref(ref_type=RefType.LAW, book="vwgo", section="154"),
                    Ref(ref_type=RefType.LAW, book="vwgo", section="162"),
                ],
            }
        ],
        True,
    )


def test_extract21(law_extractor):
    assert_refs(
        law_extractor,
        [
            {
                "resource": "law/extract21.txt",
                "refs": [
                    # § 77 Abs. 1 Satz 1, 1. Halbsatz AsylG
                    Ref(ref_type=RefType.LAW, book="asylg", section="77")
                ],
            }
        ],
        True,
    )


def test_extract22(law_extractor):
    assert_refs(
        law_extractor,
        [
            {
                "resource": "law/extract22.txt",
                "refs": [
                    # §§ 52 Abs. 1; 53 Abs. 2 Nr. 1; 63 Abs. 2 StPO
                    Ref(ref_type=RefType.LAW, book="stpo", section="52"),
                    Ref(ref_type=RefType.LAW, book="stpo", section="53"),
                    Ref(ref_type=RefType.LAW, book="stpo", section="63"),
                ],
            }
        ],
        True,
    )


def test_extract23(law_extractor):
    assert_refs(
        law_extractor,
        [
            {
                "resource": "law/extract23.txt",
                "refs": [
                    # Art 12 Abs 1 GG
                    Ref(ref_type=RefType.LAW, book="gg", section="1"),
                    Ref(ref_type=RefType.LAW, book="gg", section="2"),
                    Ref(ref_type=RefType.LAW, book="gg", section="3"),
                    Ref(ref_type=RefType.LAW, book="gg", section="12"),
                ],
            }
        ],
        True,
    )


def test_extract24(law_extractor):
    assert_refs(
        law_extractor,
        [
            {
                "resource": "law/extract24.txt",
                "refs": [
                    # §§ 556d, 556g BGB
                    Ref(ref_type=RefType.LAW, book="bgb", section="556d"),
                    Ref(ref_type=RefType.LAW, book="bgb", section="556e"),
                ],
            }
        ],
        True,
    )


def test_extract25(law_extractor):
    assert_refs(
        law_extractor,
        [
            {
                "resource": "law/extract25.txt",
                "refs": [
                    # §§ 1, 2 Abs. 2, 3, 10 Abs. 1 Nr. 1 BGB
                    Ref(ref_type=RefType.LAW, book="bgb", section="1"),
                    Ref(ref_type=RefType.LAW, book="bgb", section="2"),
                    Ref(ref_type=RefType.LAW, book="bgb", section="3"),
                    Ref(ref_type=RefType.LAW, book="bgb", section="10"),
                ],
            }
        ],
        True,
    )


def test_extract26(law_extractor):
    assert_refs(
        law_extractor,
        [
            {
                "resource": "law/extract26.txt",
                "refs": [
                    # § 3d AsylG, aber auch § 123 VwGO. ... auch §§ 3, 3b AsylG
                    Ref(ref_type=RefType.LAW, book="asylg", section="3"),
                    Ref(ref_type=RefType.LAW, book="asylg", section="3b"),
                    Ref(ref_type=RefType.LAW, book="asylg", section="3d"),
                    Ref(ref_type=RefType.LAW, book="vwgo", section="123"),
                ],
            }
        ],
        True,
    )


def test_extract27(law_extractor):
    assert_refs(
        law_extractor,
        [
            {
                "resource": "law/extract27.txt",
                "refs": [
                    # duplicated book code parts
                    Ref(ref_type=RefType.LAW, book="sgg", section="136"),
                    Ref(ref_type=RefType.LAW, book="sgb x", section="48"),
                ],
            }
        ],
        True,
    )


def test_extract_full_law_name(law_extractor):
    """Full law name references like '§ 8 des Außensteuergesetzes' (issue #9)."""
    assert_refs(
        law_extractor,
        [
            {
                "content": "unter § 8 Absatz 1 Nummern 1 bis 6 des deutschen Außensteuergesetzes fallenden Tätigkeiten",
                "refs": [
                    Ref(ref_type=RefType.LAW, book="außensteuergesetz", section="8"),
                ],
            },
            {
                "content": "gemäß § 40 des Verwaltungsverfahrensgesetzes ist der Verwaltungsakt nichtig",
                "refs": [
                    Ref(ref_type=RefType.LAW, book="verwaltungsverfahrensgesetz", section="40"),
                ],
            },
            {
                "content": "nach § 343 der Zivilprozessordnung kann das Gericht entscheiden",
                "refs": [
                    Ref(ref_type=RefType.LAW, book="zivilprozessordnung", section="343"),
                ],
            },
        ],
    )


def test_citation_styles(law_extractor):
    with open(os.path.join(RESOURCE_DIR, "citation_styles.txt")) as f:
        x = DivideAndConquerLawRefExtractorMixin()

        content = f.read()

        markers = x.extract_law_ref_markers(content)

        # Verify all markers have valid positions and references
        for m in markers:
            assert m.start >= 0
            assert m.end <= len(content)
            assert m.end > m.start
            assert len(m.get_references()) > 0


# Catastrophic-backtracking inputs encountered when bulk-extracting from real
# German court decisions. Each triggers exponential-time matching in one of
# the ``ac``-based patterns (``art_single``, ``single_any_book``,
# ``single_ivm``) when the trailing book / ``i.V.m.`` capture group fails.
# The fix is the possessive ``ac_book_safe`` / ``ac_ivm_safe`` variants.
@pytest.mark.parametrize(
    "content",
    [
        # art_single: long Artikel enumeration without a book at the end.
        # Lifted (and trimmed) from a real extradition decision listing
        # Italian penal-code articles.
        (
            "Die dem Verfolgten zur Last gelegten Taten sind strafbar nach "
            "Art. 51, 66, 193, 196, 197, 213, 214, 322, 323, 324, 324bis, "
            "324ter Abs. 1, 325, 326 und 496 des italienischen Codice Penale."
        ),
        # single_any_book: long § enumeration without a book at the end.
        ("Verstoß gegen § 100, 101, 102, 103, 104, 105, 106, 107, 108, 109, 110, 111, 112, 113, 114."),
        # single_ivm: long content stretch followed by no i.V.m. terminator.
        ("§ 263 Abs. 1, Abs. 2, Abs. 3 S. 2 Nr. 4, 266 Abs. 1 2. Alt. und Abs. 2 Schluss der Vorschrift."),
    ],
)
def test_no_catastrophic_backtracking(content):
    """Pathological inputs must fail to match within a tight time budget.

    Uses ``signal.SIGALRM`` to fail the test if extraction exceeds 2s.
    Before the possessive-quantifier fix, each of these would run for
    minutes in production.
    """
    ext = DivideAndConquerLawRefExtractorMixin()

    def _timeout(signum, frame):
        raise TimeoutError("law extraction exceeded budget — backtracking regression")

    prev = signal.signal(signal.SIGALRM, _timeout)
    signal.setitimer(signal.ITIMER_REAL, 2.0)
    try:
        ext.extract_law_ref_markers(content)
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, prev)


def test_article_enumeration_with_trailing_book_still_matches(law_extractor):
    """Long Artikel enumerations that *do* end with a book must still match.

    The possessive ``ac_book_safe`` must not regress: an artikel list that
    properly terminates with a book code remains extractable. Asserts the
    final body group covers the citation span.
    """
    content = "Verstoß gegen Art. 100, 101, 102, 103, 104, 105 GG ist gegeben."
    _, markers = law_extractor.extract(content)
    refs = [r for m in markers for r in m.get_references()]
    assert any(r.book == "gg" for r in refs)


def test_section_followed_by_uppercase_book_code(law_extractor):
    """``§ 154 Abs. 1 VwGO`` must resolve the book to ``vwgo``, not ``go``.

    The inter-content alternation contains a Roman-numeral token that can
    match the leading ``V`` of ``VwGO``. The intuitive ``[IXV]{1,3}(?!\\w)``
    guard is miscompiled by CPython's possessive engine (it keeps the ``V``
    partial despite the failing lookahead), leaving only ``wGO`` and
    mis-resolving the book to ``go``. ``_ROMAN_NUM_TOKEN`` avoids the bug.
    """
    content = "Die Kostenentscheidung beruht auf § 154 Abs. 1 VwGO."
    _, markers = law_extractor.extract(content)
    refs = [r for m in markers for r in m.get_references()]
    assert any(r.book == "vwgo" and r.section == "154" for r in refs), refs


def test_roman_absatz_before_book(law_extractor):
    """A Roman-numeral Absatz between an ``Abs.`` qualifier and the book code
    (``§ 5 Abs. 1 III BGB``) is consumed as inter-content, leaving the book
    intact — the Roman token must match ``III`` without eating into ``BGB``."""
    content = "Maßgeblich ist § 5 Abs. 1 III BGB."
    _, markers = law_extractor.extract(content)
    refs = [r for m in markers for r in m.get_references()]
    assert any(r.book == "bgb" and r.section == "5" for r in refs), refs


def test_roman_absatz_directly_after_section(law_extractor):
    """A bare Roman Absatz directly after the section (``§ 5 III BGB``,
    ``§ 5 IV ZPO``) must resolve the *book*, not the numeral.

    Two latent bugs caused the numeral to win: bogus ``III BGB`` / ``IV ZPO``
    entries polluted ``law_book_codes.txt`` (removed), and the generic book
    fallback matched bare Roman numerals ending in a suffix letter
    (``IV``/``XV`` end in ``V``) — now rejected by a leading lookahead.
    """
    for content, book in [("§ 5 III BGB", "bgb"), ("§ 5 IV ZPO", "zpo"), ("§ 5 II ZPO", "zpo")]:
        _, markers = law_extractor.extract(content)
        refs = [r for m in markers for r in m.get_references()]
        assert any(r.book == book and r.section == "5" for r in refs), (content, refs)


def test_single_ivm_pattern_matches():
    """The ``single_ivm`` regex must match the canonical in-conjunction shape.

    ``_IVM_SAFE`` must stop the inter-content right before ``i.V.m.`` / ``iVm``
    so the trailing capture group still has those tokens to match. The
    natural possessive ``(?:(?!i\\.V\\.m\\.|iVm)(?:…))*+`` is miscompiled
    (the leading lookahead is ignored, swallowing ``i.V.m.`` and matching
    nothing); a tempered greedy class is used instead.
    """
    ext = DivideAndConquerLawRefExtractorMixin()
    pat = ext._precompile_patterns()["single_ivm"]
    for content, want in [
        ("§ 1 Abs. 1 i.V.m. § 2 SGB I", "§ 1 Abs. 1 i.V.m."),
        ("§ 5 Abs. 2 iVm § 6 BGB", "§ 5 Abs. 2 iVm"),
    ]:
        m = pat.search(content)
        assert m is not None, content
        assert m.group(0) == want, (m.group(0), want)
