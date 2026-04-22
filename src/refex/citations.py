"""Typed citation models for the new extraction API (Stream C).

These exist alongside the legacy ``Ref`` / ``RefMarker`` classes.
The old types stay in ``models.py`` for backward compatibility;
these are the forward-looking replacements.

All citation classes are frozen dataclasses with ``__slots__``.
Span offsets are always into the plain-text ``Document.text`` field.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from typing import Literal


@dataclass(frozen=True, slots=True)
class Span:
    """Character-offset span into ``Document.text``."""

    start: int
    end: int
    text: str


@dataclass(frozen=True, slots=True)
class LawCitation:
    """A citation of a law section (§, Art.)."""

    span: Span
    id: str = ""
    kind: Literal["full", "short", "id", "ibid", "supra", "aao", "ebenda"] = "full"
    confidence: float = 1.0
    source: str = "regex"

    unit: Literal["paragraph", "article"] | None = None
    delimiter: str | None = None
    book: str | None = None
    number: str | None = None
    structure: tuple[tuple[str, str], ...] = ()
    range_end: str | None = None
    range_extensions: tuple[str, ...] = ()
    resolves_to: str | None = None

    @property
    def type(self) -> str:
        return "law"


@dataclass(frozen=True, slots=True)
class CaseCitation:
    """A citation of a court decision."""

    span: Span
    id: str = ""
    kind: Literal["full", "short", "id", "ibid", "supra", "aao", "ebenda"] = "full"
    confidence: float = 1.0
    source: str = "regex"

    court: str | None = None
    file_number: str | None = None
    date: str | None = None
    ecli: str | None = None
    decision_type: str | None = None
    reporter: str | None = None
    reporter_volume: str | None = None
    reporter_page: str | None = None

    @property
    def type(self) -> str:
        return "case"


# Union type for type-narrowing
Citation = LawCitation | CaseCitation


@dataclass(frozen=True, slots=True)
class CitationRelation:
    """A directed relation between two citations in the same document."""

    source_id: str
    target_id: str
    relation: Literal["ivm", "vgl", "aao", "ebenda", "siehe", "resolves_to", "parallel"]
    span: Span | None = None


@dataclass(slots=True)
class ExtractionResult:
    """Result of running one or more extractors on a document."""

    citations: list[Citation] = field(default_factory=list)
    relations: list[CitationRelation] = field(default_factory=list)


# D8: Valid keys for the ``structure`` dict on ``LawCitation``.
# These correspond to the hierarchical sub-units of a German law section.
# Cf. Darji 2023's property taxonomy for German legal citations.
STRUCTURE_KEYS: frozenset[str] = frozenset(
    {
        "absatz",  # Absatz (paragraph within a section)
        "satz",  # Satz (sentence)
        "nummer",  # Nummer (number/item)
        "halbsatz",  # Halbsatz (half-sentence)
        "buchstabe",  # Buchstabe (letter)
        "alternative",  # Alternative
        "variante",  # Variante (variant)
        "buch",  # Buch (book, for codes like SGB)
        "teil",  # Teil (part)
        "kapitel",  # Kapitel (chapter)
        "abschnitt",  # Abschnitt (section/division)
        "unterabschnitt",  # Unterabschnitt (sub-section)
        "titel",  # Titel (title)
        "untertitel",  # Untertitel (subtitle)
        "anlage",  # Anlage (annex/appendix)
        "anhang",  # Anhang (appendix)
        "stufe",  # Stufe (level)
        "spiegelstrich",  # Spiegelstrich (dash/bullet)
        "doppelbuchstabe",  # Doppelbuchstabe (double letter)
        "tabelle",  # Tabelle (table)
        "ziffer",  # Ziffer (digit/numeral)
    }
)


def make_citation_id(span: Span, source: str, doc_id: str = "") -> str:
    """Generate a stable content-hash citation ID (C1f).

    Deterministic: same input always produces the same ID.
    """
    raw = f"{doc_id}|{span.start}|{span.end}|{span.text}|{source}"
    return hashlib.sha256(raw.encode()).hexdigest()[:12]
