"""Adapt refex extractor output (RefMarker/Ref) to benchmark Citation format.

This is the bridge between the legacy refex output and the benchmark schema.
It converts ``list[RefMarker]`` → ``list[Citation]`` so that the metrics module
can compare predicted citations against gold annotations.

Two span-correction passes improve exact-match alignment with gold annotations:

1. **Law multi-ref splitting** — Gold annotates each section separately in
   ``§§ 91, 708 Nr. 11, 711 ZPO``; refex emits one combined span.  We split
   the marker text into per-section sub-spans.

2. **Case span expansion** — Gold annotates full citation context like
   ``BGH, Urt. v. 06.04.2000 - IX ZR 422/98``; refex marks only the file
   number ``IX ZR 422/98``.  We expand backward to include the court + date
   prefix when the court name is found directly before the file number.
"""

from __future__ import annotations

import re

from benchmarks.datasets import Citation, Span
from refex.models import Ref, RefMarker, RefType


def refmarkers_to_citations(
    markers: list[RefMarker],
    content: str | None = None,
) -> list[Citation]:
    """Convert a list of RefMarker objects to benchmark Citation objects.

    Each RefMarker may contain multiple Ref objects (e.g., ``§§ 12-14 BGB``
    produces one marker with two law refs).  We emit one Citation per Ref.

    Args:
        markers: Extracted RefMarker objects from the extractor.
        content: Original document text, used for case span expansion.
            If None, case spans are not expanded.
    """
    citations: list[Citation] = []
    cit_idx = 0

    for marker in markers:
        refs = marker.get_references()

        if not refs:
            # Marker with no parsed refs — emit as unknown
            cit_idx += 1
            citations.append(
                Citation(
                    id=f"p_{cit_idx:03d}",
                    type="unknown",
                    kind="full",
                    span=Span(start=marker.start, end=marker.end, text=marker.text),
                )
            )
            continue

        # Split multi-ref law markers into per-section sub-spans
        is_multi_law = len(refs) > 1 and all(r.ref_type == RefType.LAW for r in refs)
        sub_spans = _split_law_multi_ref_spans(marker, refs) if is_multi_law else None

        for i, ref in enumerate(refs):
            cit_idx += 1

            if sub_spans is not None:
                span = sub_spans[i]
            elif ref.ref_type == RefType.CASE and content:
                span = _expand_case_span(marker, ref, content)
            else:
                span = Span(start=marker.start, end=marker.end, text=marker.text)

            cit = _ref_to_citation(ref, span, cit_idx)
            citations.append(cit)

    return citations


# ---------------------------------------------------------------------------
# Law multi-ref span splitting
# ---------------------------------------------------------------------------


def _split_law_multi_ref_spans(marker: RefMarker, refs: list[Ref]) -> list[Span] | None:
    """Split a multi-ref marker's text into per-section sub-spans.

    Only splits at *section boundaries* (preceded by ``§§``, ``,``, or ``;``),
    not at ``und``/``bis`` which join structure qualifiers within a single
    section (e.g., ``S. 1 und 2`` stays together).

    Returns a list of Span objects (one per ref), or None if splitting cannot
    be performed reliably.
    """
    text = marker.text
    n = len(refs)

    # Locate each ref's section number and classify the preceding separator.
    found: list[tuple[int, int, bool]] = []  # (text_offset, ref_index, is_boundary)
    search_from = 0

    for i, ref in enumerate(refs):
        section = ref.section
        if not section:
            return None

        pat = re.compile(r"(?<![0-9])" + re.escape(section) + r"(?![0-9])")
        m = pat.search(text, search_from)
        if m:
            # A section boundary exists at §§, comma, or semicolon — NOT at
            # "und" or "bis" (those join structure qualifiers within a section).
            before = text[: m.start()].rstrip()
            is_boundary = before.endswith("§") or before.endswith(",") or before.endswith(";") or m.start() == 0
            found.append((m.start(), i, is_boundary))
            search_from = m.end()

    # Only keep section boundaries for splitting
    boundaries = [(pos, idx) for pos, idx, is_bnd in found if is_bnd]

    if len(boundaries) < 2:
        return None

    # Build per-boundary spans
    spans: list[Span | None] = [None] * n

    for fi, (pos, ref_idx) in enumerate(boundaries):
        start = 0 if fi == 0 else pos

        if fi == len(boundaries) - 1:
            end = len(text)
        else:
            end = boundaries[fi + 1][0]
            while end > start and text[end - 1] in " ,;":
                end -= 1

        span = Span(
            start=marker.start + start,
            end=marker.start + end,
            text=text[start:end],
        )

        # Assign to this ref and all subsequent refs until the next boundary
        next_bnd_idx = boundaries[fi + 1][1] if fi < len(boundaries) - 1 else n
        for j in range(ref_idx, next_bnd_idx):
            spans[j] = span

    # Fill any remaining None slots (refs before the first boundary)
    for i in range(n):
        if spans[i] is None:
            if boundaries:
                spans[i] = spans[boundaries[0][1]]
            else:
                return None

    return spans


# ---------------------------------------------------------------------------
# Case citation span expansion
# ---------------------------------------------------------------------------

# Patterns that indicate citation context between a court name and file number
_CITATION_CONTEXT_RE = re.compile(
    r"(?:"
    r"Urteil|Urt\.?|Beschluss|Beschl\.?"
    r"|Gerichtsbescheid|Vorlagebeschluss|Zwischenurteil"
    r"|vom|v\."
    r"|[-–]"
    r"|\d{1,2}\.\s*(?:Januar|Februar|März|April|Mai|Juni|Juli|August"
    r"|September|Oktober|November|Dezember)"
    r"|\d{1,2}[./]\d{1,2}[./]\d{2,4}"
    r"|\d{4}-\d{2}-\d{2}"
    r")",
    re.IGNORECASE,
)

# Another file number in the between-text means the court belongs to a
# different citation, not this one.
_FILE_NUMBER_RE = re.compile(r"\d+\s+[A-Z][A-Za-z]{0,4}\s+\d+[/.]")


def _expand_case_span(marker: RefMarker, ref: Ref, content: str) -> Span:
    """Expand a case citation span backward to include court + date context.

    Guards against over-expansion:
    - Max 60 chars between court and file number
    - No unmatched parentheses (parenthetical refs stay narrow)
    - No other file numbers in between text (wrong court association)
    """
    default = Span(start=marker.start, end=marker.end, text=marker.text)

    court = ref.court
    if not court:
        return default

    # Look backward from the file number for the court name.
    # Word boundary on the right prevents matching inside reporter
    # abbreviations (e.g., "BGH" must not match inside "BGHZ").
    search_start = max(0, marker.start - 100)
    prefix = content[search_start : marker.start]

    court_re = re.compile(re.escape(court) + r"(?![A-Za-zÄÖÜäöüß])")
    matches = list(court_re.finditer(prefix))
    if not matches:
        return default
    court_pos = matches[-1].start()  # rightmost (closest to file number)

    new_start = search_start + court_pos
    between = content[new_start + len(court) : marker.start]

    # Guard 1: between text must be short (citation context, not narrative)
    if len(between) > 60:
        return default

    # Guard 2: no unmatched parentheses — "BGH (Beschl. v. ..." is
    # a parenthetical reference where gold only annotates the file number
    if "(" in between and ")" not in between:
        return default

    # Guard 3: no other file number in between text — means the court
    # belongs to a different citation
    if _FILE_NUMBER_RE.search(between):
        return default

    # Guard 4: between text must contain citation context markers
    has_context = bool(_CITATION_CONTEXT_RE.search(between))
    between_stripped = between.strip(" ,;.:-–")

    if not has_context and len(between_stripped) > 3:
        return default

    new_text = content[new_start : marker.end]
    return Span(start=new_start, end=marker.end, text=new_text)


# ---------------------------------------------------------------------------
# Ref → Citation conversion
# ---------------------------------------------------------------------------


def _ref_to_citation(ref: Ref, span: Span, idx: int) -> Citation:
    """Convert a single Ref to a Citation with the given span."""
    if ref.ref_type == RefType.LAW:
        return Citation(
            id=f"p_{idx:03d}",
            type="law",
            kind="full",
            span=span,
            book=ref.book if ref.book else None,
            number=ref.section if ref.section else None,
        )

    if ref.ref_type == RefType.CASE:
        return Citation(
            id=f"p_{idx:03d}",
            type="case",
            kind="full",
            span=span,
            court=ref.court if ref.court else None,
            file_number=ref.file_number if ref.file_number else None,
            date=ref.date if ref.date else None,
        )

    return Citation(
        id=f"p_{idx:03d}",
        type="unknown",
        kind="full",
        span=span,
    )
