"""Backward-compatibility adapter: typed Citation → legacy RefMarker.

Kept for Open Legal Data's internal pipeline which still consumes
``RefMarker`` objects.  New consumers should work with
``ExtractionResult.citations`` directly.
"""

from __future__ import annotations

from refex.citations import CaseCitation, Citation, ExtractionResult, LawCitation
from refex.models import Ref, RefMarker, RefType


def citations_to_ref_markers(result: ExtractionResult) -> list[RefMarker]:
    """Convert an ``ExtractionResult`` to legacy ``RefMarker`` objects."""
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
