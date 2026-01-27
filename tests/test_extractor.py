import pytest

from refex.models import Ref, RefType
from tests.conftest import assert_refs, get_book_codes_from_file


def test_extract(extractor):
    content_html = "<h1>Hallo</h1><p>Ein Satz mit § 3 Abs. 1 Nr. 1 i.V.m. § 3b AsylG, und weiteren Sachen.</p>"
    content_html += "<p>Komplexe Zitate gibt es auch §§ 3, 3b AsylG.</p>"
    content_html += "<p>Beschluss des OLG Koblenz zurückgewiesen <em>(Beschluss vom 29.10.2015 - IX ZR 103/14)</em>; diese Entscheidung beruht jedoch auf der vom BGH beanstandeten unzureichenden Darlegung der grundsätzlichen Bedeutung. Nähere Ausführungen zur Wirksamkeit</p>"

    new_content, markers = extractor.extract(content_html)


@pytest.mark.skip
def test_extract_bsg(extractor):
    assert_refs(extractor, [{"resource": "bsg_2018-06-27.txt", "refs": []}])


def test_catastrophic_backtracking(extractor):
    extractor.law_book_codes = get_book_codes_from_file()
    assert_refs(
        extractor,
        [
            {
                "resource": "bgh_2018-08-16.html",
                "refs": [
                    # catastrophic_backtracking
                    Ref(ref_type=RefType.LAW, book="zpo", section="253"),
                    # Ref(ref_type=RefType.CASE, file_number='III ZR 126/15')
                ],
            }
        ],
    )
