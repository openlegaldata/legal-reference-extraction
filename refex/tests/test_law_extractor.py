from refex.models import Ref, RefType

from refex.tests import BaseRefExTest


class LawRefExTest(BaseRefExTest):

    def setUp(self):
        self.extractor.do_law_refs = True
        self.extractor.do_case_refs = False

    def tearDown(self):
        pass

    def test_extract(self):
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
        content_html = '<h1>Hallo</h1><p>Ein Satz mit § 3 Abs. 1 Nr. 1 i.V.m. § 3b AsylG, und weiteren Sachen.</p>'
        content_html += '<p>Komplexe Zitate gibt es auch §§ 3, 3b AsylG.</p>'

        new_content, markers = self.extractor.extract(content_html)

        print(new_content)
        print('Markers: %s' % markers)

    def test_with_law_book_context(self):
        """Book context is used for extracting law references from within law text, where book is not
        explicitly mentioned."""

        self.extractor.law_book_context = 'bgb'

        text = '<P>(2) Der Vorsitzende kann einen solchen Vertreter auch bestellen,' \
               ' wenn in den Fällen des § 20 eine nicht prozessfähige Person bei dem ' \
               'Gericht ihres Aufenthaltsortes verklagt werden soll..</P>'

        new_content, markers = self.extractor.extract(text)

        self.assertEqual(1, len(markers), 'Invalid marker count')
        self.assertEqual('20', markers[0].references[0].section, 'Invalid section')


    def test_handle_multiple_law_refs(self):
        ref_str = '§§ 10000 Abs. 3 ZPO, 151, 153 VwGO'

        actual = self.extractor.handle_multiple_law_refs(ref_str, [])
        expected = [
            Ref(ref_type=RefType.LAW, book='vwgo', section='153'),
            Ref(ref_type=RefType.LAW, book='vwgo', section='151'),
            Ref(ref_type=RefType.LAW, book='zpo', section='10000')]

        # print(actual)
        # print(expected)
        # self.assertNotEqual(Ref(ref_type=RefType.LAW, book='vwgo', section='153'), Ref(ref_type=RefType.LAW, book='vwgo', section='153x'))
        self.assertListEqual(expected, actual, 'Invalid references')

    def test_timeout_ref(self):
        expected = [
            {
                'content': ' Auslandsaufenthalt mit beachtlicher Wahrscheinlichkeit aufgrund eines ihm (zugeschriebenen) Verfolgungsgrundes '
                           'im Sinne des § 3 Abs. 1 AsylG, insbesondere einer regimekritischen politischen Überzeugung, erfolgen würden. '
                           'Nach der Rechtsprechung des schleswig-holsteinischen Oberverwaltungsgerichtes (Urteil vom 23.11.2016, - 3 LB 17/16 -, juris), '
                           'der sich die Kammer anschließt, besteht nach der gegenwärtigen Erkenntnislage keine hinreichende'
                           ' Grundlage für die Annahme, dass der totalitäre syrische Staat jeden Rückkehrer pauschal unter eine '
                           'Art Generalsverdacht stellt, der Opposition anzugehören (so auch OVG Saarland, '
                           'Urteil vom 2.2.2017, - 2 A 515/16 -; OVG Rheinland-Pfalz, Urteil vom 16.12.2016, -1A 10922/16 -; Bayrischer VGH, '
                           'Urteil vom 12.12.16, - 21 B 16.30364; OVG Nordrhein-Westfalen,',
                'refs': [
                    Ref(ref_type=RefType.LAW, book='asylg', section='3'),
                ]
            }
        ]

        self.assert_refs(expected)



    def test_extract_law_refs_detailed(self):

        expected = [
            {
                'content': 'Die Zulassung der Berufung folgt aus §§ 124 Abs. 2 Nr. 3, 124 a Abs. 1 Satz 1 VwGO wegen grundsätzlicher Bedeutung.',
                'refs': [
                    Ref(ref_type=RefType.LAW, book='vwgo', section='124a'),
                    Ref(ref_type=RefType.LAW, book='vwgo', section='124'),
                ]
            },
            {
                'content': 'Die Entscheidung über die vorläufige Vollstreckbarkeit folgt '
                           'aus § 167 VwGO i.V.m. §§ 708 Nr. 11, 711 ZPO.',
                'refs': [
                    # '§ 167 VwGO',
                    # '§§ 708 Nr. 11, 711 ZPO'
                    Ref(ref_type=RefType.LAW, book='vwgo', section='167'),
                    Ref(ref_type=RefType.LAW, book='zpo', section='711'),
                    Ref(ref_type=RefType.LAW, book='zpo', section='708'),
                ]
            },
            {
                'content': 'Die Kostenentscheidung beruht auf § 154 Abs. 1 VwGO. Die außergerichtlichen Kosten des '
                           'beigeladenen Ministeriums waren für erstattungsfähig zu erklären, da dieses einen '
                           'Sachantrag gestellt hat und damit ein Kostenrisiko eingegangen ist '
                           '(vgl. §§ 162 Abs. 3 ZPO, 151, 153 VwGO).',
                'refs': [
                    Ref(ref_type=RefType.LAW, book='vwgo', section='154'),
                    Ref(ref_type=RefType.LAW, book='vwgo', section='153'),
                    Ref(ref_type=RefType.LAW, book='vwgo', section='151'),
                    Ref(ref_type=RefType.LAW, book='zpo', section='162'),
                ]
            },
            {
                'content': 'Dies gilt grundsätzlich für die planerisch ausgewiesenen und die faktischen '
                           '(§ 34 Abs. 2 BauGB) Baugebiete nach §§ 2 bis 4 BauNVO, die Ergebnis eines typisierenden '
                           'Ausgleichs möglicher Nutzungskonflikte sind. Setzt die Gemeinde einen entsprechenden Gebietstyp fest',
                'refs': [
                    Ref(ref_type=RefType.LAW, book='baugb', section='34'),
                    Ref(ref_type=RefType.LAW, book='baunvo', section='4'),
                    Ref(ref_type=RefType.LAW, book='baunvo', section='3'),
                    Ref(ref_type=RefType.LAW, book='baunvo', section='2'),
                ]
            },
            {
                'content': 'Die Kostenentscheidung beruht auf § 154 Abs. 1 VwGO. Die außergerichtlichen Kosten des'
                           ' beigeladenen Ministeriums waren für erstattungsfähig zu erklären, da dieses einen '
                           'Sachantrag gestellt hat und damit ein Kostenrisiko eingegangen ist '
                           '(vgl. §§ 162 Abs. 3, 154 Abs. 3 VwGO).',
                # 'content': 'Die Kostenentscheidung beruht auf § 154 Abs. 1 VwGO. ',
                # 'content': '(vgl. §§ 162 Abs. 3, 154 Abs. 3 VwGO).',
                'refs': [ # TODO main regex not working for §§ 162 Abs. 3, 154 Abs. 3 VwG
                    Ref(ref_type=RefType.LAW, book='vwgo', section='154'),
                    Ref(ref_type=RefType.LAW, book='vwgo', section='154'),
                    Ref(ref_type=RefType.LAW, book='vwgo', section='162'),
                ]
            },
            {
                'content': '2. Der Klagantrag zu 2. ist unzulässig. Es handelt sich um einen Anfechtungsantrag '
                           'nach § 42 Abs. 1 Alt. 1 VwGO bezüglich der seitens des beigeladenen Ministeriums '
                           'getroffenen ergänzenden Abweichungsentscheidung vom 13.05.2016 in Gestalt des'
                           ' Widerspruchsbescheides vom 14.08.2016.',
                'refs': [
                    Ref(ref_type=RefType.LAW, book='vwgo', section='42'),
                ]
            }
        ]

        self.assert_refs(expected)
