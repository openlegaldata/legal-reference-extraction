from refex.models import Ref, RefMarker, RefType


def test_replace_content():
    text = "§ 123 ABC"
    marker = RefMarker(text, 0, len(text))
    marker.uuid = "foo"
    marker.references = [Ref(ref_type=RefType.LAW, book="abc", section=123)]

    content = text + " and other text..."

    assert marker.replace_content(content, 0)[0] == "[ref=foo]§ 123 ABC[/ref] and other text...", "Invalid content"
