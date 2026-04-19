"""Document model and source profile normalization (Stream J).

Replaces the ``is_html: bool`` flag with a proper input type that
carries format metadata and a canonical plain-text projection.
"""

from __future__ import annotations

import html
import re
from dataclasses import dataclass
from html.parser import HTMLParser
from typing import Literal


@dataclass
class Document:
    """Input wrapper for the extraction pipeline.

    Attributes:
        raw: Original document content (plain text, HTML, or Markdown).
        format: Declared format of ``raw``.
        source_profile: Optional normalizer profile name.
        text: Canonical plain-text projection for extraction.
              Span offsets in citations reference this field.
    """

    raw: str
    format: Literal["plain", "html", "markdown"] = "plain"
    source_profile: str | None = None
    text: str = ""
    doc_id: str = ""

    def __post_init__(self):
        if not self.text:
            self.text = normalize(self.raw, self.format, self.source_profile)


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
    if fmt == "plain":
        return _normalize_plain(raw)
    if fmt == "html":
        return _normalize_html(raw, profile)
    if fmt == "markdown":
        return _normalize_markdown(raw)
    return _normalize_plain(raw)


def _normalize_plain(text: str) -> str:
    """Identity normalizer for plain text."""
    return text


def _normalize_html(raw: str, profile: str | None = None) -> str:
    """Strip HTML tags, decode entities, normalize whitespace.

    Uses stdlib ``html.parser`` — no BeautifulSoup dependency.
    """
    stripper = _HTMLTextExtractor()
    stripper.feed(raw)
    text = stripper.get_text()

    # Decode remaining HTML entities
    text = html.unescape(text)

    # Collapse whitespace
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)

    return text.strip()


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
