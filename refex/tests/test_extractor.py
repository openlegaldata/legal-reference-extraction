from unittest import skip

from refex.tests import BaseRefExTest


class RefExTest(BaseRefExTest):
    def setUp(self):
        self.extractor.do_law_refs = True
        self.extractor.do_case_refs = True

    def tearDown(self):
        pass

    def test_extract(self):
        content_html = '<h1>Hallo</h1><p>Ein Satz mit § 3 Abs. 1 Nr. 1 i.V.m. § 3b AsylG, und weiteren Sachen.</p>'
        content_html += '<p>Komplexe Zitate gibt es auch §§ 3, 3b AsylG.</p>'
        content_html += '<p>Beschluss des OLG Koblenz zurückgewiesen <em>(Beschluss vom 29.10.2015 - IX ZR 103/14)</em>; diese Entscheidung beruht jedoch auf der vom BGH beanstandeten unzureichenden Darlegung der grundsätzlichen Bedeutung. Nähere Ausführungen zur Wirksamkeit</p>'

        new_content, markers = self.extractor.extract(content_html)

        print(new_content)

        print('Markers:')
        for m in markers:
            print('- %s' % m.text)

    @skip
    def test_extract_bsg(self):

        self.assert_refs([
            {
                'resource': 'bsg_2018-06-27.txt',
                'refs': [

                ]
            }
        ])

