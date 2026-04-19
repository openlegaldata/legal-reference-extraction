"""Tests for Document model, source profiles, and format detection (Stream J)."""

from refex.citations import LawCitation
from refex.document import (
    Document,
    detect_format,
    make_document,
    normalize,
)
from refex.orchestrator import CitationExtractor

# --- normalize ---


class TestNormalizePlain:
    def test_identity(self):
        assert normalize("hello world") == "hello world"

    def test_preserves_section_sign(self):
        text = "Gemäß § 433 BGB"
        assert normalize(text) == text


class TestNormalizeHtml:
    def test_strips_tags(self):
        assert "hello" in normalize("<p>hello</p>", fmt="html")

    def test_decodes_entities(self):
        result = normalize("&#167; 433 BGB", fmt="html")
        assert "§ 433 BGB" in result

    def test_block_tags_produce_newlines(self):
        result = normalize("<p>first</p><p>second</p>", fmt="html")
        assert "\n" in result

    def test_skips_script_content(self):
        result = normalize("<p>text</p><script>evil()</script><p>more</p>", fmt="html")
        assert "evil" not in result
        assert "text" in result
        assert "more" in result

    def test_skips_style_content(self):
        result = normalize("<style>.foo{color:red}</style><p>content</p>", fmt="html")
        assert "color" not in result
        assert "content" in result

    def test_collapses_whitespace(self):
        result = normalize("<p>hello    world</p>", fmt="html")
        assert "hello world" in result

    def test_real_legal_html(self):
        html_content = (
            "<div><h4>Gründe</h4></div>"
            "<div><p>Die Kostenentscheidung beruht auf "
            "<a>&#167; 154 Abs. 1 VwGO</a>.</p></div>"
        )
        result = normalize(html_content, fmt="html")
        assert "§ 154 Abs. 1 VwGO" in result
        assert "<" not in result


class TestNormalizeMarkdown:
    def test_strips_headers(self):
        result = normalize("# Title\n\nBody text", fmt="markdown")
        assert "Title" in result
        assert "#" not in result

    def test_strips_bold(self):
        result = normalize("This is **bold** text", fmt="markdown")
        assert "bold" in result
        assert "**" not in result

    def test_strips_links(self):
        result = normalize("[click here](http://example.com)", fmt="markdown")
        assert "click here" in result
        assert "http" not in result


# --- detect_format ---


class TestDetectFormat:
    def test_html(self):
        assert detect_format("<html><body>text</body></html>") == "html"
        assert detect_format("  <div>content</div>") == "html"

    def test_markdown(self):
        assert detect_format("# Title\n\nBody") == "markdown"
        assert detect_format("This is **bold** text") == "markdown"

    def test_plain(self):
        assert detect_format("Gemäß § 433 BGB ist der Käufer verpflichtet.") == "plain"


# --- Document ---


class TestDocument:
    def test_plain_text_auto_normalizes(self):
        doc = Document(raw="hello world")
        assert doc.text == "hello world"

    def test_html_auto_normalizes(self):
        doc = Document(raw="<p>§ 433 BGB</p>", format="html")
        assert "§ 433 BGB" in doc.text
        assert "<" not in doc.text

    def test_explicit_text_not_overwritten(self):
        doc = Document(raw="<p>html</p>", format="html", text="custom text")
        assert doc.text == "custom text"

    def test_doc_id(self):
        doc = Document(raw="text", doc_id="test_123")
        assert doc.doc_id == "test_123"


# --- make_document ---


class TestMakeDocument:
    def test_auto_detect_plain(self):
        doc = make_document("Gemäß § 433 BGB ist dies so.")
        assert doc.format == "plain"
        assert doc.text == "Gemäß § 433 BGB ist dies so."

    def test_auto_detect_html(self):
        doc = make_document("<p>§ 433 BGB</p>")
        assert doc.format == "html"
        assert "§ 433 BGB" in doc.text

    def test_explicit_format(self):
        doc = make_document("plain text", fmt="plain")
        assert doc.format == "plain"

    def test_with_profile(self):
        doc = make_document("<p>text</p>", fmt="html", source_profile="oldp-html")
        assert doc.source_profile == "oldp-html"


# --- Integration: CitationExtractor with Document ---


class TestExtractorWithDocument:
    def test_extract_from_string(self):
        ext = CitationExtractor()
        result = ext.extract("Gemäß § 433 BGB ist dies so.")
        assert len(result.citations) >= 1

    def test_extract_from_document(self):
        ext = CitationExtractor()
        doc = Document(raw="Gemäß § 433 BGB ist dies so.")
        result = ext.extract(doc)
        assert len(result.citations) >= 1

    def test_extract_from_html_string(self):
        ext = CitationExtractor()
        html_content = "<p>Gemäß &#167; 433 BGB ist dies so.</p>"
        result = ext.extract(html_content, fmt="html")
        law_cits = [c for c in result.citations if isinstance(c, LawCitation)]
        assert len(law_cits) >= 1
        assert any(c.book == "bgb" for c in law_cits)

    def test_extract_from_html_document(self):
        ext = CitationExtractor()
        doc = Document(raw="<p>Kosten nach § 154 Abs. 1 VwGO.</p>", format="html")
        result = ext.extract(doc)
        law_cits = [c for c in result.citations if isinstance(c, LawCitation)]
        assert len(law_cits) >= 1

    def test_span_offsets_into_text_not_raw(self):
        ext = CitationExtractor()
        doc = Document(raw="<p>Gemäß § 433 BGB ist dies so.</p>", format="html")
        result = ext.extract(doc)
        for c in result.citations:
            actual = doc.text[c.span.start : c.span.end]
            assert actual == c.span.text, f"Span into text: {actual!r} != {c.span.text!r}"
