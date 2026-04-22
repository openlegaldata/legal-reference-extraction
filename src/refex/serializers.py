"""Output format serializers and adapters (Stream D).

D1: ``to_jsonl()`` — primary JSONL output per the benchmark spec.
D3: ``to_spacy_doc()`` — spaCy Doc-compatible dict.
D4: ``to_hf_bio()`` — token-level BIO tags for HuggingFace NER.
D5: ``to_gliner()`` — GLiNER span-based format.
D6: ``to_web_annotation()`` — W3C Web Annotation Data Model.
D7: ``to_akn_ref()`` — Akoma Ntoso / LegalDocML.de XML.

All adapters are pure Python with zero external dependencies.
"""

from __future__ import annotations

import json
import re
from dataclasses import asdict
from xml.sax.saxutils import escape as xml_escape

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


def to_spacy_doc(
    result: ExtractionResult,
    text: str,
) -> dict:
    """Convert citations to a spaCy Doc-compatible dict (D3).

    Returns a dict that can be loaded via ``spacy.tokens.Doc.from_json()``.
    Whitespace tokenization is applied; each citation becomes a span
    in the ``"spans"`` dict under the key ``"citations"``.

    No spaCy dependency required — the output is a plain dict.
    """
    tokens, char_to_token = _whitespace_tokenize(text)
    spans = []

    for cit in result.citations:
        start_tok = char_to_token.get(cit.span.start)
        # Find the token containing (end - 1)
        end_char = max(cit.span.start, cit.span.end - 1)
        end_tok = char_to_token.get(end_char)

        if start_tok is None or end_tok is None:
            continue

        spans.append(
            {
                "start_token": start_tok,
                "end_token": end_tok + 1,  # exclusive
                "label": cit.type.upper() + "_REF",
                "kb_id": cit.id,
            }
        )

    return {
        "text": text,
        "tokens": tokens,
        "spans": {"citations": spans},
    }


def _whitespace_tokenize(text: str) -> tuple[list[dict], dict[int, int]]:
    """Simple whitespace tokenizer returning spaCy-compatible token dicts.

    Returns:
        (tokens, char_to_token) where char_to_token maps char offsets
        to token indices.
    """
    tokens: list[dict] = []
    char_to_token: dict[int, int] = {}
    idx = 0

    for tok_match in re.finditer(r"\S+", text):
        start = tok_match.start()
        end = tok_match.end()
        ws = text[end : end + 1] if end < len(text) else ""
        tokens.append(
            {
                "orth": tok_match.group(),
                "space": ws in (" ", "\t"),
            }
        )
        for j in range(start, end):
            char_to_token[j] = idx
        idx += 1

    return tokens, char_to_token


def to_hf_bio(
    result: ExtractionResult,
    text: str,
) -> dict:
    """Convert citations to HuggingFace token-classification BIO format (D4).

    Uses whitespace tokenization. Each token gets a BIO label:
    ``B-LAW_REF``, ``I-LAW_REF``, ``B-CASE_REF``, ``I-CASE_REF``, or ``O``.

    Returns a dict with ``"tokens"`` and ``"ner_tags"`` lists.
    """
    token_spans: list[tuple[int, int, str]] = []
    for tok_match in re.finditer(r"\S+", text):
        token_spans.append((tok_match.start(), tok_match.end(), tok_match.group()))

    labels = ["O"] * len(token_spans)

    for cit in result.citations:
        label = cit.type.upper() + "_REF"
        first = True
        for i, (ts, te, _) in enumerate(token_spans):
            if te <= cit.span.start:
                continue
            if ts >= cit.span.end:
                break
            labels[i] = f"B-{label}" if first else f"I-{label}"
            first = False

    return {
        "tokens": [t[2] for t in token_spans],
        "ner_tags": labels,
    }


def to_gliner(result: ExtractionResult) -> list[dict]:
    """Convert citations to GLiNER span format (D5).

    Returns a list of span dicts with ``start``, ``end``, ``label``,
    and ``text`` keys — the format expected by GLiNER for evaluation
    and training.
    """
    spans = []
    for cit in result.citations:
        spans.append(
            {
                "start": cit.span.start,
                "end": cit.span.end,
                "label": cit.type.upper() + "_REF",
                "text": cit.span.text,
            }
        )
    return spans


def to_web_annotation(
    result: ExtractionResult,
    source_uri: str = "",
) -> list[dict]:
    """Convert citations to W3C Web Annotation Data Model dicts (D6).

    Each citation becomes an annotation with a ``TextPositionSelector``.
    The ``source_uri`` identifies the annotated document.

    Returns a list of JSON-LD-compatible dicts.
    """
    annotations = []
    for cit in result.citations:
        body: dict = {
            "type": "TextualBody",
            "purpose": "tagging",
            "value": cit.type.upper() + "_REF",
        }
        # Add structured metadata
        body["properties"] = to_dict(cit)

        annotation: dict = {
            "@context": "http://www.w3.org/ns/anno.jsonld",
            "id": f"urn:refex:{cit.id}",
            "type": "Annotation",
            "motivation": "classifying",
            "body": body,
            "target": {
                "source": source_uri,
                "selector": {
                    "type": "TextPositionSelector",
                    "start": cit.span.start,
                    "end": cit.span.end,
                },
            },
        }
        annotations.append(annotation)

    return annotations


def to_akn_ref(
    result: ExtractionResult,
    text: str,
) -> str:
    """Convert citations to Akoma Ntoso / LegalDocML XML fragment (D7).

    Returns the document text with citation spans wrapped in ``<ref>``
    elements.  Each ``<ref>`` has an ``eId`` attribute and, for law
    citations, an ``href`` attribute pointing to the law book + section.

    The output is a well-formed XML fragment (not a full AKN document).
    """
    sorted_cits = sorted(result.citations, key=lambda c: c.span.start, reverse=True)

    output = text
    for cit in sorted_cits:
        href = _build_akn_href(cit)
        escaped_text = xml_escape(output[cit.span.start : cit.span.end])
        ref_elem = f'<ref eId="{xml_escape(cit.id)}" href="{xml_escape(href)}">{escaped_text}</ref>'
        output = output[: cit.span.start] + ref_elem + output[cit.span.end :]

    return output


def _build_akn_href(cit: Citation) -> str:
    """Build an Akoma Ntoso-style URI for a citation."""
    if isinstance(cit, LawCitation):
        book = cit.book or ""
        number = cit.number or ""
        return f"/akn/de/act/{book}/~{number}"
    if isinstance(cit, CaseCitation):
        court = cit.court or ""
        fn = cit.file_number or ""
        return f"/akn/de/judgment/{court}/{fn}"
    return ""
