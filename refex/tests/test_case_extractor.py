import logging
import os
import re
from unittest import skip

from refex.models import RefType, Ref
from refex.tests import BaseRefExTest

logger = logging.getLogger(__name__)


class CaseRefExTest(BaseRefExTest):
    def setUp(self):
        self.extractor.do_law_refs = False
        self.extractor.do_case_refs = True

    def tearDown(self):
        pass

    def test_regex_file_numbers(self):
        text = "(vgl. Schl.-Holst. OVG, Urteil vom 19.01.2012 - 1 LB 11/11 -, juris [Rn. 23 f.])"
        text += "(vgl. OVG NRW, Urteil vom 10.10.1996 - 7 A 4185/95 -, juris [Rn. 68])"
        text += "(vgl. BVerwG, Beschluss vom 12.11.1987 - 4 B 216/87 -, juris [Rn. 2]; VGH BW, Urteil vom 10.01.2007 - 3 S 1251/06 -, juris [Rn. 25])"
        text += "(so BVerfG in std. Rspr., vgl. z.B. BVerfG, Beschluss vom 23.07.2003 –- 2 BvR 624/01 -, juris [Rn. 16 f.])"
        text += " (vgl. OVG Berlin-Brbg., Urt. v. 17.07.2014 - OVG 7 B 40.13 -, Juris Rn. 35;)"  # TODO file number format

        expected = [
            "1 LB 11/11",
            "7 A 4185/95",
            "4 B 216/87",
            "3 S 1251/06",
            "2 BvR 624/01",
        ]
        actual = []

        fns_matches = list(re.finditer(self.extractor.get_file_number_regex(), text))

        for f in fns_matches:
            actual.append(f.group())

        self.assertListEqual(expected, actual, "Invalid file numbers extracted")

    def test_regex_court_names(self):
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

        fns_matches = list(re.finditer(self.extractor.get_court_name_regex(), text))

        for f in fns_matches:
            actual.append(f.group("court"))

        logger.debug("Actual:   %s" % actual)
        logger.debug("Expected: %s" % expected)

        self.assertListEqual(
            sorted(actual), sorted(expected), "Invalid court names extracted"
        )

    def test_clean_text(self):
        text = (
            "Obgleich die Baulast ein Institut des in die Kompetenz des Landesgesetzgebers fallenden bauaufsic"
            "htlichen Verfahrens ist, der deshalb auch die formellen und materiellen Voraussetzungen ihres Ent"
            "stehens und Erlöschens bestimmt, darf sich die übernommene Belastung auch auf die Nutzung des Gru"
            "ndstücks in bodenrechtlicher (bebauungsrechtlicher) Hinsicht beziehen (vgl. BVerwG, Beschluss vom"
            " 12.11.1987 - 4 B 216/87 -, juris [Rn. 2]; VGH BW, Urteil vom 10.01.2007 - 3 S 1251/06 -, juris"
            " [Rn. 25])."
        )

        # print('BEFORE = %s' % text)
        # print()
        # print(self.indexer.clean_text_for_tokenizer(text))
        #
        self.assertEqual(
            "Obgleich die Baulast ein Institut des in die Kompetenz des Landesgesetzgebers fallenden "
            "bauaufsichtlichen Verfahrens ist, der deshalb auch die formellen und materiellen Voraus"
            "setzungen ihres Entstehens und Erlöschens bestimmt, darf sich die übernommene Belastung"
            " auch auf die Nutzung des Grundstücks in bodenrechtlicher ______________________ Hinsic"
            "ht beziehen ____________________________________________________________________________________________________________________________________.",
            self.extractor.clean_text_for_tokenizer(text),
        )

    def test_extract_case_refs_detail(self):
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

        self.assert_refs(fixtures)

    def test_get_file_number_regex(self):
        pattern = self.extractor.get_file_number_regex()

        matched = 0
        not_matched = 0

        with open(os.path.join(self.resource_dir, "case/file_numbers.txt")) as f:
            for line in f.readlines():
                line = line.strip()
                if not re.search(pattern, line):
                    print(line)
                    not_matched += 1
                else:
                    matched += 1

        print("matched: %i" % matched)
        print("not_matched: %i" % not_matched)

        print(pattern)

    @skip
    def test_extract(self):
        self.assert_refs(
            [
                {
                    "resource": "bsg_2018-06-27.txt",
                    "refs": [
                        Ref(
                            ref_type=RefType.CASE, court="BGH", file_number="6 KA 45/13"
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
                            file_number="11 KA 67/10",
                        ),
                        Ref(
                            ref_type=RefType.CASE,
                            court="LSG Nordrhein-Westfalen",
                            file_number="24 K 120/10",
                        ),
                        Ref(
                            ref_type=RefType.CASE,
                            court="LSG Nordrhein-Westfalen",
                            file_number="7 U 199/05",
                        ),
                        Ref(
                            ref_type=RefType.CASE,
                            court="OLG Koblenz",
                            file_number="19 U 98/97",
                        ),
                        Ref(
                            ref_type=RefType.CASE,
                            court="OLG Koblenz",
                            file_number="2 U 553/13",
                        ),
                        Ref(
                            ref_type=RefType.CASE,
                            court="OLG Koblenz",
                            file_number="6 KA 39/17",
                        ),
                        Ref(
                            ref_type=RefType.CASE,
                            court="OLG Koblenz",
                            file_number="6 KA 40/17",
                        ),
                        Ref(
                            ref_type=RefType.CASE,
                            court="OLG Koblenz",
                            file_number="IX ZR 103/14",
                        ),
                        # Ref(ref_type=RefType.CASE, court='', file_number=''),
                        # Ref(ref_type=RefType.CASE, court='', file_number=''),
                        # Ref(ref_type=RefType.LAW, book='baunvo', section='2'),
                        # Ref(ref_type=RefType.LAW, book='baunvo', section='3'),
                        # Ref(ref_type=RefType.LAW, book='baunvo', section='4'),
                    ],
                }
            ]
        )

    @skip
    def test_extract_html(self):
        self.assert_refs(
            [
                {
                    "resource": "bsg_2018-06-27.html",
                    "refs": [
                        Ref(
                            ref_type=RefType.CASE, court="BGH", file_number="6 KA 45/13"
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
                            file_number="11 KA 67/10",
                        ),
                        Ref(
                            ref_type=RefType.CASE,
                            court="LSG Nordrhein-Westfalen",
                            file_number="24 K 120/10",
                        ),
                        Ref(
                            ref_type=RefType.CASE,
                            court="LSG Nordrhein-Westfalen",
                            file_number="7 U 199/05",
                        ),
                        Ref(
                            ref_type=RefType.CASE,
                            court="OLG Koblenz",
                            file_number="19 U 98/97",
                        ),
                        Ref(
                            ref_type=RefType.CASE,
                            court="OLG Koblenz",
                            file_number="2 U 553/13",
                        ),
                        Ref(
                            ref_type=RefType.CASE,
                            court="OLG Koblenz",
                            file_number="6 KA 39/17",
                        ),
                        Ref(
                            ref_type=RefType.CASE,
                            court="OLG Koblenz",
                            file_number="6 KA 40/17",
                        ),
                        Ref(
                            ref_type=RefType.CASE,
                            court="OLG Koblenz",
                            file_number="IX ZR 103/14",
                        ),
                    ],
                }
            ]
        )

    def test_get_codes(self):
        self.extractor.get_codes()

    def test_codes_are_correctly_extracted(self):
        """If a code contains some extra information in brackets (e.g. 'W (pat)')
        this part is not being returned, since it is not in the 'code' capture group
        of the case regex."""
        codes = self.extractor.get_codes()
        self.assertIn("Ks", codes)
        self.assertIn("AnwSt", codes)
        self.assertIn("W", codes)
        self.assertIn("REMiet", codes)
