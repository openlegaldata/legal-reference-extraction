import os
import re

import pytest

from refex.extractors.law_dnc import DivideAndConquerLawRefExtractorMixin
from refex.models import Ref, RefType
from tests.conftest import RESOURCE_DIR, assert_refs, get_book_codes_from_file


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


@pytest.mark.skip
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


@pytest.mark.skip
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

        law_extractor.replace_content(content, markers)


@pytest.mark.skip
def test_alternative_law_book_regex(law_extractor):
    pattern = re.compile(r"([A-ZÄÜÖ][-ÄÜÖäüöA-Za-z]*)(V|G|O|B)")
    for code in get_book_codes_from_file() + ["SGB X", "SGG", "SGB IV"]:
        if not pattern.search(code):
            pass
