"""Backward-compatibility adapters (C5, C6).

Converts between the new typed ``Citation`` objects and the legacy
``Ref`` / ``RefMarker`` types.  This keeps the old API working while
the new API is preferred for new consumers.
"""

from __future__ import annotations

import warnings

from refex.citations import CaseCitation, Citation, ExtractionResult, LawCitation
from refex.models import Ref, RefMarker, RefType


def citations_to_ref_markers(result: ExtractionResult) -> list[RefMarker]:
    """Convert an ``ExtractionResult`` to legacy ``RefMarker`` objects (C5).

    This allows the old ``replace_content`` / ``[ref=UUID]...[/ref]``
    pipeline to keep working on results from the new typed API.
    """
    markers: list[RefMarker] = []

    for cit in result.citations:
        marker = RefMarker(
            text=cit.span.text,
            start=cit.span.start,
            end=cit.span.end,
        )
        marker.set_uuid()

        ref = _citation_to_ref(cit)
        marker.set_references([ref])
        markers.append(marker)

    return markers


def _citation_to_ref(cit: Citation) -> Ref:
    """Convert a single typed Citation to a legacy Ref."""
    if isinstance(cit, LawCitation):
        return Ref(
            ref_type=RefType.LAW,
            book=cit.book or "",
            section=cit.number or "",
        )

    if isinstance(cit, CaseCitation):
        return Ref(
            ref_type=RefType.CASE,
            court=cit.court or "",
            file_number=cit.file_number or "",
            date=cit.date or "",
            ecli=cit.ecli or "",
        )

    msg = f"Unknown citation type: {type(cit)}"
    raise TypeError(msg)


def to_ref_marker_string(result: ExtractionResult, content: str) -> str:
    """Produce the legacy ``[ref=UUID]...[/ref]`` marked-up string (C6).

    .. deprecated::
        Use ``ExtractionResult.citations`` directly.  This method exists
        only for backward compatibility with Open Legal Data's pipeline.
    """
    warnings.warn(
        "to_ref_marker_string is deprecated; use ExtractionResult.citations directly",
        DeprecationWarning,
        stacklevel=2,
    )
    markers = citations_to_ref_markers(result)
    sorted_markers = sorted(markers, key=lambda m: m.get_start_position())

    marker_offset = 0
    output = content

    for marker in sorted_markers:
        output, marker_offset = marker.replace_content(output, marker_offset)

    return output
