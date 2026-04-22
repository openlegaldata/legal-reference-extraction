"""Tests for Document model, source profiles, and format detection (Stream J)."""

from refex.citations import CaseCitation, LawCitation, Span
from refex.document import (
    Document,
    detect_format,
    make_document,
    map_span_to_raw,
    normalize,
)
from refex.orchestrator import CitationExtractor


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


class TestDetectFormat:
    def test_html(self):
        assert detect_format("<html><body>text</body></html>") == "html"
        assert detect_format("  <div>content</div>") == "html"

    def test_markdown(self):
        assert detect_format("# Title\n\nBody") == "markdown"
        assert detect_format("This is **bold** text") == "markdown"

    def test_plain(self):
        assert detect_format("Gemäß § 433 BGB ist der Käufer verpflichtet.") == "plain"


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


class TestOffsetMap:
    def test_plain_text_has_no_offset_map(self):
        doc = Document(raw="Gemäß § 433 BGB")
        assert doc.offset_map is None

    def test_html_has_offset_map(self):
        doc = Document(raw="<p>§ 433 BGB</p>", format="html")
        assert doc.offset_map is not None
        assert len(doc.offset_map) == len(doc.text)

    def test_html_offset_map_identity_for_text_chars(self):
        raw = "<p>Gemäß § 433 BGB</p>"
        doc = Document(raw=raw, format="html")
        # Each offset should point to a valid position in raw
        for i, off in enumerate(doc.offset_map):
            assert 0 <= off < len(raw), f"offset_map[{i}]={off} out of range"

    def test_html_entity_offset_mapping(self):
        doc = Document(raw="<p>&#167; 433 BGB</p>", format="html")
        assert doc.text == "§ 433 BGB"
        # § should map to the start of &#167;
        assert doc.offset_map[0] == doc.raw.index("&")
        # The space after the entity should map to the space in raw
        assert doc.raw[doc.offset_map[1]] == " "

    def test_map_span_to_raw_plain(self):
        doc = Document(raw="Gemäß § 433 BGB")
        span = Span(start=6, end=15, text="§ 433 BGB")
        raw_span = map_span_to_raw(span, doc)
        assert raw_span == span  # Identity

    def test_map_span_to_raw_html(self):
        raw = "<p>Gemäß § 433 BGB</p>"
        doc = Document(raw=raw, format="html")
        # Find where "§ 433 BGB" appears in text
        idx = doc.text.index("§ 433 BGB")
        span = Span(start=idx, end=idx + 9, text="§ 433 BGB")
        raw_span = map_span_to_raw(span, doc)
        assert raw[raw_span.start : raw_span.end] == "§ 433 BGB"

    def test_map_span_to_raw_with_entity(self):
        raw = "<p>&#167; 433 BGB</p>"
        doc = Document(raw=raw, format="html")
        span = Span(start=0, end=9, text="§ 433 BGB")
        raw_span = map_span_to_raw(span, doc)
        assert "433 BGB" in raw_span.text  # The raw span includes the entity
        assert raw_span.text.endswith("BGB")

    def test_round_trip_html_extraction(self):
        """Extract citations from HTML, map spans back to raw."""
        raw = "<div><p>Die Regelung in <b>§ 433 BGB</b> ist entscheidend.</p></div>"
        doc = Document(raw=raw, format="html")
        ext = CitationExtractor()
        result = ext.extract(doc)

        for cit in result.citations:
            # Span works in text
            assert doc.text[cit.span.start : cit.span.end] == cit.span.text
            # Map back to raw
            raw_span = map_span_to_raw(cit.span, doc)
            # The raw span should contain the citation text
            assert cit.span.text.replace(" ", "") in raw_span.text.replace(" ", "").replace("<b>", "").replace(
                "</b>", ""
            )


class TestBoilerplateContamination:
    def test_script_content_not_extracted(self):
        raw = '<p>§ 433 BGB</p><script>var x = "§ 999 StGB";</script>'
        doc = Document(raw=raw, format="html")
        ext = CitationExtractor()
        result = ext.extract(doc)
        # Should not find the citation inside <script>
        assert all("999" not in c.span.text for c in result.citations)

    def test_style_content_not_extracted(self):
        raw = "<style>.sec { content: '§ 123 ZPO'; }</style><p>§ 433 BGB</p>"
        doc = Document(raw=raw, format="html")
        ext = CitationExtractor()
        result = ext.extract(doc)
        assert all("123" not in c.span.text for c in result.citations)

    def test_citations_in_body_only(self):
        raw = "<head><title>§ 1 GG</title></head><p>Laut § 154 VwGO sind die Kosten zu tragen.</p>"
        doc = Document(raw=raw, format="html")
        ext = CitationExtractor()
        result = ext.extract(doc)
        # Only body citations should be found
        law_cits = [c for c in result.citations if isinstance(c, LawCitation)]
        assert len(law_cits) >= 1
        assert all("154" in c.span.text or "VwGO" in c.span.text for c in law_cits)


class TestHtmlExtractionIntegration:
    """End-to-end tests: HTML in → citations out → spans round-trip to raw."""

    def test_html_entities_section_sign(self):
        """HTML-encoded § (&sect; / &#167;) must be decoded for extraction."""
        raw = "<p>Gem&auml;&szlig; &sect; 433 Abs. 1 BGB schuldet der Verk&auml;ufer.</p>"
        ext = CitationExtractor()
        result = ext.extract(raw, fmt="html")
        law_cits = [c for c in result.citations if isinstance(c, LawCitation)]
        assert len(law_cits) == 1
        assert law_cits[0].book == "bgb"
        assert law_cits[0].number == "433"

    def test_html_entity_section_sign_single(self):
        """HTML numeric entity &#167; decodes to § for extraction."""
        raw = "<p>Gem&auml;&szlig; &#167; 154 Abs. 1 VwGO ist dies so.</p>"
        ext = CitationExtractor()
        result = ext.extract(raw, fmt="html")
        law_cits = [c for c in result.citations if isinstance(c, LawCitation)]
        assert len(law_cits) >= 1
        assert law_cits[0].book == "vwgo"

    def test_html_case_citation_with_dash_entity(self):
        """Case citations with HTML dash entities (ndash) must work."""
        raw = "<p>BGH, Urteil vom 12.03.2020 &ndash; VIII ZR 295/01.</p>"
        ext = CitationExtractor()
        result = ext.extract(raw, fmt="html")
        case_cits = [c for c in result.citations if isinstance(c, CaseCitation)]
        assert len(case_cits) >= 1
        assert any("295/01" in c.file_number for c in case_cits if c.file_number)

    def test_html_spans_reference_text_not_raw(self):
        """All span offsets must index into doc.text, not raw HTML."""
        raw = (
            "<div><h4>Gr&uuml;nde</h4></div>"
            "<div><p>Die Kostenentscheidung beruht auf "
            "<a>&#167; 154 Abs. 1 VwGO</a>.</p></div>"
        )
        doc = Document(raw=raw, format="html")
        ext = CitationExtractor()
        result = ext.extract(doc)
        for cit in result.citations:
            actual = doc.text[cit.span.start : cit.span.end]
            assert actual == cit.span.text

    def test_html_offset_round_trip_with_entities(self):
        """map_span_to_raw must recover a valid substring of raw HTML."""
        raw = "<p>&#167; 433 Abs. 1 BGB ist ma&szlig;geblich.</p>"
        doc = Document(raw=raw, format="html")
        ext = CitationExtractor()
        result = ext.extract(doc)
        for cit in result.citations:
            raw_span = map_span_to_raw(cit.span, doc)
            assert raw_span.start < raw_span.end
            assert raw_span.end <= len(raw)
            # Raw span must contain the key part of the citation
            assert "433" in raw_span.text

    def test_html_nested_tags_preserved(self):
        """Citations inside nested tags (em, b, a) are extracted."""
        raw = "<p>Gemäß <em><b>§ 433 BGB</b></em> ist dies so.</p>"
        ext = CitationExtractor()
        result = ext.extract(raw, fmt="html")
        law_cits = [c for c in result.citations if isinstance(c, LawCitation)]
        assert len(law_cits) == 1
        assert law_cits[0].book == "bgb"

    def test_html_multiple_paragraphs(self):
        """Citations across multiple <p> tags are all found."""
        raw = (
            "<p>Die Berufung ist gemäß §§ 511, 513 ZPO zulässig.</p>"
            "<p>Der Kläger hat gem. § 433 Abs. 1 BGB einen Anspruch.</p>"
        )
        ext = CitationExtractor()
        result = ext.extract(raw, fmt="html")
        law_cits = [c for c in result.citations if isinstance(c, LawCitation)]
        books = {c.book for c in law_cits}
        assert "zpo" in books
        assert "bgb" in books


class TestMarkdownExtractionIntegration:
    """End-to-end tests: Markdown in → citations out → spans round-trip."""

    def test_md_bold_emphasis_stripped(self):
        """Citations inside **bold** markers are extracted."""
        md = "Gemäß **§ 433 Abs. 1 BGB** schuldet der Verkäufer."
        ext = CitationExtractor()
        result = ext.extract(md, fmt="markdown")
        law_cits = [c for c in result.citations if isinstance(c, LawCitation)]
        assert len(law_cits) == 1
        assert law_cits[0].book == "bgb"

    def test_md_heading_stripped(self):
        """Headings are stripped but don't interfere with extraction."""
        md = "# Urteil\n\nDie Kosten folgen aus § 154 Abs. 1 VwGO."
        ext = CitationExtractor()
        result = ext.extract(md, fmt="markdown")
        law_cits = [c for c in result.citations if isinstance(c, LawCitation)]
        assert len(law_cits) == 1
        assert law_cits[0].book == "vwgo"

    def test_md_link_stripped(self):
        """Link syntax is stripped, keeping the visible text for extraction."""
        md = "Siehe [§ 154 VwGO](https://example.com/vwgo/154)."
        ext = CitationExtractor()
        result = ext.extract(md, fmt="markdown")
        law_cits = [c for c in result.citations if isinstance(c, LawCitation)]
        assert len(law_cits) == 1

    def test_md_offset_round_trip(self):
        """Markdown span offsets round-trip back to raw via offset map."""
        md = "Gemäß **§ 433 BGB** ist dies so."
        doc = make_document(md, fmt="markdown")
        assert doc.offset_map is not None  # Markdown has offset map
        ext = CitationExtractor()
        result = ext.extract(doc)
        for cit in result.citations:
            # Span indexes into text
            assert doc.text[cit.span.start : cit.span.end] == cit.span.text
            # Round-trip to raw
            raw_span = map_span_to_raw(cit.span, doc)
            assert raw_span.start < raw_span.end
            assert "433" in raw_span.text
            assert "BGB" in raw_span.text

    def test_md_case_citation(self):
        """Case citations in Markdown are extracted."""
        md = "Vgl. BGH, Urteil vom 12.03.2020 - VIII ZR 295/01."
        ext = CitationExtractor()
        result = ext.extract(md, fmt="markdown")
        case_cits = [c for c in result.citations if isinstance(c, CaseCitation)]
        assert len(case_cits) >= 1

    def test_md_inline_code_stripped(self):
        """Inline code markers are stripped for extraction."""
        md = "Der Anspruch ergibt sich aus `§ 433 BGB`."
        ext = CitationExtractor()
        result = ext.extract(md, fmt="markdown")
        law_cits = [c for c in result.citations if isinstance(c, LawCitation)]
        assert len(law_cits) == 1

    def test_md_mixed_formatting(self):
        """Multiple formatting types in one document."""
        md = (
            "# BGH-Urteil\n\n"
            "Die Kosten folgen aus **§ 154 VwGO** i.V.m. "
            "[§§ 708, 711 ZPO](https://example.com).\n\n"
            "Vgl. *BGH, VIII ZR 295/01*."
        )
        ext = CitationExtractor()
        result = ext.extract(md, fmt="markdown")
        assert len(result.citations) >= 2  # at least law + case


class TestAutoDetectIntegration:
    """Verify format auto-detection works end-to-end."""

    def test_auto_detect_html_and_extract(self):
        html = "<p>Gemäß § 433 BGB ist der Käufer verpflichtet.</p>"
        ext = CitationExtractor()
        result = ext.extract(html)  # no fmt= → auto-detect
        assert len(result.citations) >= 1

    def test_auto_detect_markdown_and_extract(self):
        md = "# Urteil\n\nGemäß **§ 433 BGB** ist der Käufer verpflichtet."
        ext = CitationExtractor()
        result = ext.extract(md)  # no fmt= → auto-detect
        assert len(result.citations) >= 1

    def test_auto_detect_plain_and_extract(self):
        text = "Gemäß § 433 BGB ist der Käufer verpflichtet."
        ext = CitationExtractor()
        result = ext.extract(text)  # no fmt= → auto-detect
        assert len(result.citations) >= 1
