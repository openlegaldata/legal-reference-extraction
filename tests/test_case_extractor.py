import logging
import os
import re

from refex.models import Ref, RefType
from tests.conftest import RESOURCE_DIR, assert_refs

logger = logging.getLogger(__name__)


def test_regex_file_numbers(case_extractor):
    text = "(vgl. Schl.-Holst. OVG, Urteil vom 19.01.2012 - 1 LB 11/11 -, juris [Rn. 23 f.])"
    text += "(vgl. OVG NRW, Urteil vom 10.10.1996 - 7 A 4185/95 -, juris [Rn. 68])"
    text += "(vgl. BVerwG, Beschluss vom 12.11.1987 - 4 B 216/87 -, juris [Rn. 2]; VGH BW, Urteil vom 10.01.2007 - 3 S 1251/06 -, juris [Rn. 25])"
    text += "(so BVerfG in std. Rspr., vgl. z.B. BVerfG, Beschluss vom 23.07.2003 –- 2 BvR 624/01 -, juris [Rn. 16 f.])"
    text += " (vgl. OVG Berlin-Brbg., Urt. v. 17.07.2014 - OVG 7 B 40.13 -, Juris Rn. 35;)"

    expected = [
        "1 LB 11/11",
        "7 A 4185/95",
        "4 B 216/87",
        "3 S 1251/06",
        "2 BvR 624/01",
        "7 B 40.13",
    ]
    actual = []

    fns_matches = list(re.finditer(case_extractor.get_file_number_regex(), text))

    for f in fns_matches:
        actual.append(f.group())

    assert expected == actual, "Invalid file numbers extracted"


def test_regex_court_names(case_extractor):
    text = "(vgl. Schl.-Holst. OVG, Urteil vom 19.01.2012 - 1 LB 11/11 -, juris [Rn. 23 f.])"
    text += "(vgl. OVG NRW, Urteil vom 10.10.1996 - 7 A 4185/95 -, juris [Rn. 68])"
    text += "(vgl. BVerwG, Beschluss vom 12.11.1987 - 4 B 216/87 -, juris [Rn. 2]; VGH BW, Urteil vom 10.01.2007 - 3 S 1251/06 -, juris [Rn. 25])"
    text += "(so BVerfG in std. Rspr., vgl. z.B. BVerfG, Beschluss vom 23.07.2003 –- 2 BvR 624/01 -, juris [Rn. 16 f.])"

    expected = [
        "Schl.-Holst. OVG",
        "OVG NRW",
        "BVerwG",
        "VGH BW",
        "BVerfG",
        "BVerfG",
    ]
    actual = []

    fns_matches = list(re.finditer(case_extractor.get_court_name_regex(), text))

    for f in fns_matches:
        actual.append(f.group("court"))

    logger.debug(f"Actual:   {actual}")
    logger.debug(f"Expected: {expected}")

    assert sorted(actual) == sorted(expected), "Invalid court names extracted"


def test_clean_text(case_extractor):
    text = (
        "Obgleich die Baulast ein Institut des in die Kompetenz des Landesgesetzgebers fallenden bauaufsic"
        "htlichen Verfahrens ist, der deshalb auch die formellen und materiellen Voraussetzungen ihres Ent"
        "stehens und Erlöschens bestimmt, darf sich die übernommene Belastung auch auf die Nutzung des Gru"
        "ndstücks in bodenrechtlicher (bebauungsrechtlicher) Hinsicht beziehen (vgl. BVerwG, Beschluss vom"
        " 12.11.1987 - 4 B 216/87 -, juris [Rn. 2]; VGH BW, Urteil vom 10.01.2007 - 3 S 1251/06 -, juris"
        " [Rn. 25])."
    )

    assert (
        case_extractor.clean_text_for_tokenizer(text)
        == "Obgleich die Baulast ein Institut des in die Kompetenz des Landesgesetzgebers fallenden "
        "bauaufsichtlichen Verfahrens ist, der deshalb auch die formellen und materiellen Voraus"
        "setzungen ihres Entstehens und Erlöschens bestimmt, darf sich die übernommene Belastung"
        " auch auf die Nutzung des Grundstücks in bodenrechtlicher ______________________ Hinsic"
        "ht beziehen ____________________________________________________________________________________________________________________________________."
    )


def test_extract_case_refs_detail(case_extractor):
    fixtures = [
        {
            "content": "Rückwirkend zum 01.01.2014 trat das Gesetz zur Neufassung des Landesplanungsgesetzes (LaplaG) und zur Aufhebung "
            "des Landesentwicklungsgrundsätzegesetzes"
            " vom 27.01.2014 (GVOBl. 12). Das OVG Schleswig habe bereits in seinem Urteil vom 22.04.2010 (1 KN 19/09) zur "
            "im Wesentlichen gleichlautenden Vorgängervorschrift im LROP-TF 2004 festgestellt, dass dieser Vorschrift die"
            " erforderliche Bestimmtheit bzw. Bestimmbarkeit und damit die Zielqualität nicht zukomme.",
            "refs": [
                Ref(
                    ref_type=RefType.CASE,
                    court="OVG Schleswig",
                    file_number="1 KN 19/09",
                )  # , date=date(2010, 4, 22)
            ],
        }
    ]

    assert_refs(case_extractor, fixtures)


def test_get_file_number_regex(case_extractor):
    pattern = case_extractor.get_file_number_regex()

    matched = 0
    not_matched = 0

    with open(os.path.join(RESOURCE_DIR, "case/file_numbers.txt")) as f:
        for line in f.readlines():
            line = line.strip()
            if not re.search(pattern, line):
                not_matched += 1
            else:
                matched += 1


def test_extract_from_bsg_case_1(case_extractor):
    assert_refs(
        case_extractor,
        [
            {
                "resource": "bsg_2018-06-27.txt",
                "refs": [
                    Ref(
                        ref_type=RefType.CASE,
                        court="Bundessozialgericht",
                        file_number="B 6 KA 45/13 R",
                    ),
                    Ref(
                        ref_type=RefType.CASE,
                        court="BGH",
                        file_number="IX ZR 165/12",
                    ),
                    Ref(
                        ref_type=RefType.CASE,
                        court="BGH",
                        file_number="IX ZR 165/12",
                    ),
                    Ref(
                        ref_type=RefType.CASE,
                        court="BVerfG",
                        file_number="1 BvL 7/14",
                    ),
                    Ref(
                        ref_type=RefType.CASE,
                        court="LSG Nordrhein-Westfalen",
                        file_number="L 11 KA 67/10",
                    ),
                    Ref(
                        ref_type=RefType.CASE,
                        court="LSG Nordrhein-Westfalen",
                        file_number="L 24 K 120/10",
                    ),
                    Ref(
                        ref_type=RefType.CASE,
                        court="OLG Koblenz",  # ERROR: It's actually "Brandenburgische OLG"
                        file_number="7 U 199/05",
                    ),
                    Ref(
                        ref_type=RefType.CASE,
                        court="OLG Hamm",
                        file_number="19 U 98/97",
                    ),
                    Ref(
                        ref_type=RefType.CASE,
                        court="OLG Koblenz",
                        file_number="2 U 553/13",
                    ),
                    Ref(
                        ref_type=RefType.CASE,
                        court="Bundessozialgericht",
                        file_number="B 6 KA 39/17 R",
                    ),
                    Ref(
                        ref_type=RefType.CASE,
                        court="Bundessozialgericht",
                        file_number="B 6 KA 40/17 R",
                    ),
                    Ref(
                        ref_type=RefType.CASE,
                        court="OLG Koblenz",
                        file_number="IX ZR 103/14",
                    ),
                ],
            }
        ],
    )


def test_from_bsg_case_1_html(case_extractor):
    assert_refs(
        case_extractor,
        [
            {
                "resource": "bsg_2018-06-27.txt",
                "refs": [
                    Ref(
                        ref_type=RefType.CASE,
                        court="Bundessozialgericht",
                        file_number="B 6 KA 45/13 R",
                    ),
                    Ref(
                        ref_type=RefType.CASE,
                        court="BGH",
                        file_number="IX ZR 165/12",
                    ),
                    Ref(
                        ref_type=RefType.CASE,
                        court="BGH",
                        file_number="IX ZR 165/12",
                    ),
                    Ref(
                        ref_type=RefType.CASE,
                        court="BVerfG",
                        file_number="1 BvL 7/14",
                    ),
                    Ref(
                        ref_type=RefType.CASE,
                        court="LSG Nordrhein-Westfalen",
                        file_number="L 11 KA 67/10",
                    ),
                    Ref(
                        ref_type=RefType.CASE,
                        court="LSG Nordrhein-Westfalen",
                        file_number="L 24 K 120/10",
                    ),
                    Ref(
                        ref_type=RefType.CASE,
                        court="OLG Koblenz",  # ERROR: It's actually "Brandenburgische OLG"
                        file_number="7 U 199/05",
                    ),
                    Ref(
                        ref_type=RefType.CASE,
                        court="OLG Hamm",
                        file_number="19 U 98/97",
                    ),
                    Ref(
                        ref_type=RefType.CASE,
                        court="OLG Koblenz",
                        file_number="2 U 553/13",
                    ),
                    Ref(
                        ref_type=RefType.CASE,
                        court="Bundessozialgericht",
                        file_number="B 6 KA 39/17 R",
                    ),
                    Ref(
                        ref_type=RefType.CASE,
                        court="Bundessozialgericht",
                        file_number="B 6 KA 40/17 R",
                    ),
                    Ref(
                        ref_type=RefType.CASE,
                        court="OLG Koblenz",
                        file_number="IX ZR 103/14",
                    ),
                ],
            }
        ],
    )


def test_potential_false_positives_should_not_be_matched(case_extractor):
    """Those false positives with invalid case codes should not be extracted,
    see also https://github.com/openlegaldata/legal-reference-extraction/issues/4
    The case regex uses some heuristics to filter those out.
    """
    assert_refs(
        case_extractor,
        [
            {
                "content": "Ein Satz mit 2014 und 2014/20, und weiteren Sachen",
                "refs": [],
            },
            {
                "content": "Ein Satz mit 2000 bis 07/20, und weiteren Sachen",
                "refs": [],
            },
            {
                "content": "Ein Satz mit 2019 bis KW 44/20, und weiteren Sachen",
                "refs": [],
            },
            {
                "content": "Ein Satz mit 49364 Reifen 245/45, und weiteren Sachen",
                "refs": [],
            },
        ],
    )


def test_bverwg_cases(case_extractor):
    assert_refs(
        case_extractor,
        [
            {
                "content": "BVerwG 7 A 9.19 - Urteil vom 15. Oktober 2020",
                "refs": [
                    Ref(
                        ref_type=RefType.CASE,
                        court="BVerwG",
                        file_number="7 A 9.19",
                    )
                ],
            },
            {
                "content": "10 C 23.12",
                "refs": [
                    Ref(
                        ref_type=RefType.CASE,
                        court="",
                        file_number="10 C 23.12",
                    )
                ],
            },
        ],
    )


def test_get_codes(case_extractor):
    case_extractor.get_codes()


def test_codes_are_correctly_extracted(case_extractor):
    """If a code contains some extra information in brackets (e.g. 'W (pat)')
    this part is not being returned, since it is not in the 'code' capture group
    of the case regex."""
    codes = case_extractor.get_codes()
    assert "Ks" in codes
    assert "AnwSt" in codes
    assert "W" in codes
    assert "REMiet" in codes
