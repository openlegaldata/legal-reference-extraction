from refex.models import Ref, RefMarker, RefType


def test_ref_marker_basics():
    """RefMarker stores text, position, and references."""
    text = "§ 123 ABC"
    marker = RefMarker(text, 0, len(text))
    marker.set_uuid()
    marker.set_references([Ref(ref_type=RefType.LAW, book="abc", section="123")])

    assert marker.text == text
    assert marker.start == 0
    assert marker.end == len(text)
    assert marker.end - marker.start == len(text)
    assert len(marker.get_references()) == 1
    assert marker.get_references()[0].book == "abc"


def test_ref_marker_replace_content_with_mask():
    """replace_content_with_mask replaces the span with underscores."""
    content = "Foo § 123 ABC bar"
    marker = RefMarker("§ 123 ABC", 4, 13)
    result = marker.replace_content_with_mask(content)
    assert result == "Foo _________ bar"
