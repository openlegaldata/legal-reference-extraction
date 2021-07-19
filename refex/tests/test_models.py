from unittest import TestCase

from refex.models import Ref, RefType, RefMarker


class RefExModelsTest(TestCase):
    def setUp(self):
        pass

    def tearDown(self):
        pass

    def test_replace_content(self):
        text = "§ 123 ABC"
        marker = RefMarker(text, 0, len(text))
        marker.uuid = "foo"
        marker.references = [Ref(ref_type=RefType.LAW, book="abc", section=123)]

        content = text + " and other text..."

        self.assertEqual(
            "[ref=foo]§ 123 ABC[/ref] and other text...",
            marker.replace_content(content, 0)[0],
            "Invalid content",
        )
