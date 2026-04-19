"""Output format serializers (Stream D).

D1: ``to_jsonl()`` — primary JSONL output per the benchmark spec.
"""

from __future__ import annotations

import json
from dataclasses import asdict

from refex.citations import (
    CaseCitation,
    Citation,
    CitationRelation,
    ExtractionResult,
    LawCitation,
)


def to_dict(citation: Citation) -> dict:
    """Convert a Citation to a plain dict suitable for JSON serialization."""
    d: dict = {}
    d["id"] = citation.id
    d["type"] = citation.type
    d["kind"] = citation.kind
    d["span"] = asdict(citation.span)
    d["confidence"] = citation.confidence
    d["source"] = citation.source

    if isinstance(citation, LawCitation):
        d["unit"] = citation.unit
        d["delimiter"] = citation.delimiter
        d["book"] = citation.book
        d["number"] = citation.number
        if citation.structure:
            d["structure"] = dict(citation.structure)
        if citation.range_end:
            d["range_end"] = citation.range_end
        if citation.range_extensions:
            d["range_extensions"] = list(citation.range_extensions)
        if citation.resolves_to:
            d["resolves_to"] = citation.resolves_to

    elif isinstance(citation, CaseCitation):
        if citation.court:
            d["court"] = citation.court
        if citation.file_number:
            d["file_number"] = citation.file_number
        if citation.date:
            d["date"] = citation.date
        if citation.ecli:
            d["ecli"] = citation.ecli
        if citation.decision_type:
            d["decision_type"] = citation.decision_type
        if citation.reporter:
            d["reporter"] = citation.reporter
        if citation.reporter_volume:
            d["reporter_volume"] = citation.reporter_volume
        if citation.reporter_page:
            d["reporter_page"] = citation.reporter_page

    return d


def relation_to_dict(rel: CitationRelation) -> dict:
    """Convert a CitationRelation to a plain dict."""
    d: dict = {
        "source_id": rel.source_id,
        "target_id": rel.target_id,
        "relation": rel.relation,
    }
    if rel.span:
        d["span"] = asdict(rel.span)
    return d


def to_jsonl(result: ExtractionResult, doc_id: str = "") -> str:
    """Serialize an ExtractionResult to a single JSONL line.

    The output format matches the benchmark ``annotations.jsonl`` schema:
    one JSON object with ``doc_id``, ``citations``, and ``relations``.
    """
    obj = {
        "doc_id": doc_id,
        "citations": [to_dict(c) for c in result.citations],
        "relations": [relation_to_dict(r) for r in result.relations],
    }
    return json.dumps(obj, ensure_ascii=False)


def to_json(result: ExtractionResult, doc_id: str = "", indent: int = 2) -> str:
    """Serialize an ExtractionResult to pretty-printed JSON."""
    obj = {
        "doc_id": doc_id,
        "citations": [to_dict(c) for c in result.citations],
        "relations": [relation_to_dict(r) for r in result.relations],
    }
    return json.dumps(obj, ensure_ascii=False, indent=indent)
