"""Document model and source profile normalization (Stream J).

Replaces the ``is_html: bool`` flag with a proper input type that
carries format metadata and a canonical plain-text projection.
"""

from __future__ import annotations

import html
import re
from dataclasses import dataclass, field
from html.parser import HTMLParser
from typing import Literal

from refex.citations import Span


@dataclass
class Document:
    """Input wrapper for the extraction pipeline.

    Attributes:
        raw: Original document content (plain text, HTML, or Markdown).
        format: Declared format of ``raw``.
        source_profile: Optional normalizer profile name.
        text: Canonical plain-text projection for extraction.
              Span offsets in citations reference this field.
        offset_map: For each index ``i`` in ``text``, the corresponding
              character offset in ``raw``.  ``None`` when the mapping
              is identity (plain-text format).
    """

    raw: str
    format: Literal["plain", "html", "markdown"] = "plain"
    source_profile: str | None = None
    text: str = ""
    doc_id: str = ""
    offset_map: list[int] | None = field(default=None, repr=False)

    def __post_init__(self):
        if not self.text:
            self.text, self.offset_map = normalize_with_offsets(self.raw, self.format, self.source_profile)


def normalize(
    raw: str,
    fmt: Literal["plain", "html", "markdown"] = "plain",
    profile: str | None = None,
) -> str:
    """Normalize raw content to canonical plain text.

    Args:
        raw: The raw document content.
        fmt: The declared format.
        profile: Optional source-specific profile.

    Returns:
        Normalized plain text suitable for extraction.
    """
    text, _ = normalize_with_offsets(raw, fmt, profile)
    return text


def normalize_with_offsets(
    raw: str,
    fmt: Literal["plain", "html", "markdown"] = "plain",
    profile: str | None = None,
) -> tuple[str, list[int] | None]:
    """Normalize raw content and return (text, offset_map).

    The offset_map is ``None`` for plain text (identity mapping).
    For HTML and Markdown, it maps each index ``i`` in the returned
    text to the corresponding index in ``raw``.
    """
    if fmt == "plain":
        return _normalize_plain(raw), None
    if fmt == "html":
        return _normalize_html_with_offsets(raw, profile)
    if fmt == "markdown":
        return _normalize_markdown(raw), None
    return _normalize_plain(raw), None


def map_span_to_raw(span: Span, document: Document) -> Span:
    """Map a plain-text span back to the original ``raw`` content (J8).

    Uses the document's ``offset_map`` if available.  For plain-text
    documents (where offset_map is None), returns the span unchanged.

    Args:
        span: A span whose offsets are into ``document.text``.
        document: The document that produced the span.

    Returns:
        A new Span with offsets into ``document.raw``.
    """
    if document.offset_map is None:
        return span

    omap = document.offset_map

    if span.start >= len(omap) or span.end > len(omap):
        return span

    raw_start = omap[span.start]
    # For end: map (end - 1) and add 1 to get an exclusive end
    raw_end = omap[span.end - 1] + 1 if span.end > span.start else raw_start
    raw_text = document.raw[raw_start:raw_end]

    return Span(start=raw_start, end=raw_end, text=raw_text)


def _normalize_plain(text: str) -> str:
    """Identity normalizer for plain text."""
    return text


def _normalize_html(raw: str, profile: str | None = None) -> str:
    """Strip HTML tags, decode entities, normalize whitespace.

    Uses stdlib ``html.parser`` — no BeautifulSoup dependency.
    """
    text, _ = _normalize_html_with_offsets(raw, profile)
    return text


def _normalize_html_with_offsets(raw: str, profile: str | None = None) -> tuple[str, list[int]]:
    """Strip HTML tags, returning text and a character-level offset map.

    Uses a simple state machine to walk the raw HTML and build
    (text_char, raw_offset) pairs, handling tags, entities, and
    block-element newlines.
    """
    # Phase 1: walk raw HTML → intermediate (char, raw_offset) pairs
    inter: list[tuple[str, int]] = []
    i = 0
    n = len(raw)
    in_skip = 0  # depth inside <script>/<style>/<head>

    _skip_tags = {"script", "style", "head"}
    _block_tags = _HTMLTextExtractor._block_tags

    while i < n:
        if raw[i] == "<":
            # Find end of tag
            end = raw.find(">", i)
            if end < 0:
                end = n - 1
            tag_content = raw[i + 1 : end]

            # Parse tag name (strip / for closing tags)
            is_closing = tag_content.startswith("/")
            tag_name = tag_content.lstrip("/").split()[0].split("/")[0].lower() if tag_content.strip("/") else ""

            if tag_name in _skip_tags:
                if is_closing:
                    in_skip = max(0, in_skip - 1)
                else:
                    in_skip += 1

            if tag_name in _block_tags and in_skip == 0:
                inter.append(("\n", i))

            i = end + 1
        elif raw[i] == "&" and in_skip == 0:
            # Entity reference
            semi = raw.find(";", i, min(i + 12, n))
            if semi >= 0:
                entity = raw[i : semi + 1]
                decoded = html.unescape(entity)
                for ch in decoded:
                    inter.append((ch, i))
                i = semi + 1
            else:
                inter.append(("&", i))
                i += 1
        elif in_skip > 0:
            i += 1
        else:
            inter.append((raw[i], i))
            i += 1

    # Phase 2: collapse whitespace, tracking offsets
    result_chars: list[str] = []
    result_offsets: list[int] = []
    j = 0
    m = len(inter)

    while j < m:
        ch, off = inter[j]
        if ch in (" ", "\t"):
            result_chars.append(" ")
            result_offsets.append(off)
            while j < m and inter[j][0] in (" ", "\t"):
                j += 1
        elif ch == "\n":
            newline_start = j
            count = 0
            while j < m and inter[j][0] == "\n":
                count += 1
                j += 1
            for k in range(min(count, 2)):
                result_chars.append("\n")
                result_offsets.append(inter[newline_start + k][1])
        else:
            result_chars.append(ch)
            result_offsets.append(off)
            j += 1

    # Phase 3: strip leading/trailing whitespace
    joined = "".join(result_chars)
    strip_left = len(joined) - len(joined.lstrip())
    strip_right = len(joined) - len(joined.rstrip())
    if strip_right == 0:
        final_offsets = result_offsets[strip_left:]
    else:
        final_offsets = result_offsets[strip_left:-strip_right]

    return joined.strip(), final_offsets


def _normalize_markdown(raw: str) -> str:
    """Minimal Markdown normalizer — strip formatting markers."""
    text = raw
    # Remove headers: # ## ### etc.
    text = re.sub(r"^#{1,6}\s+", "", text, flags=re.MULTILINE)
    # Remove emphasis: **bold**, *italic*, __bold__, _italic_
    text = re.sub(r"\*{1,2}([^*]+)\*{1,2}", r"\1", text)
    text = re.sub(r"_{1,2}([^_]+)_{1,2}", r"\1", text)
    # Remove inline code
    text = re.sub(r"`([^`]+)`", r"\1", text)
    # Remove links: [text](url) → text
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)
    return text.strip()


class _HTMLTextExtractor(HTMLParser):
    """Extract plain text from HTML using stdlib parser."""

    _block_tags = frozenset(
        {
            "p",
            "div",
            "br",
            "hr",
            "h1",
            "h2",
            "h3",
            "h4",
            "h5",
            "h6",
            "li",
            "tr",
            "dt",
            "dd",
            "blockquote",
            "pre",
            "article",
            "section",
        }
    )
    _skip_tags = frozenset({"script", "style", "head"})

    def __init__(self):
        super().__init__()
        self._parts: list[str] = []
        self._skip_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in self._skip_tags:
            self._skip_depth += 1
        if tag in self._block_tags and self._skip_depth == 0:
            self._parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in self._skip_tags:
            self._skip_depth = max(0, self._skip_depth - 1)
        if tag in self._block_tags and self._skip_depth == 0:
            self._parts.append("\n")

    def handle_data(self, data: str) -> None:
        if self._skip_depth == 0:
            self._parts.append(data)

    def handle_entityref(self, name: str) -> None:
        if self._skip_depth == 0:
            char = html.unescape(f"&{name};")
            self._parts.append(char)

    def handle_charref(self, name: str) -> None:
        if self._skip_depth == 0:
            char = html.unescape(f"&#{name};")
            self._parts.append(char)

    def get_text(self) -> str:
        return "".join(self._parts)


def detect_format(content: str) -> Literal["plain", "html", "markdown"]:
    """Heuristic format detection from content.

    Checks the first 256 characters for HTML or Markdown markers.
    """
    head = content[:256]

    # HTML: starts with < or contains HTML tags
    if head.lstrip().startswith("<") or re.search(r"<[a-z]+[\s>]", head, re.IGNORECASE):
        return "html"

    # Markdown: has CommonMark headings or emphasis
    if re.search(r"^#{1,6}\s", head, re.MULTILINE) or "**" in head or "__" in head:
        return "markdown"

    return "plain"


def make_document(
    content: str,
    fmt: Literal["plain", "html", "markdown"] | None = None,
    source_profile: str | None = None,
    doc_id: str = "",
) -> Document:
    """Create a Document from raw content with optional format auto-detection.

    Args:
        content: Raw document text.
        fmt: Explicit format. If None, auto-detected.
        source_profile: Optional source-specific profile name.
        doc_id: Optional document ID.
    """
    if fmt is None:
        fmt = detect_format(content)

    return Document(
        raw=content,
        format=fmt,
        source_profile=source_profile,
        doc_id=doc_id,
    )
