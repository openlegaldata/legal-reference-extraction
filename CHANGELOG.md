# Changelog

## Unreleased

### Breaking

- **Removed `refex.compat.to_ref_marker_string`.** Deprecated in 0.6.0
  with a ``DeprecationWarning``; it emitted the legacy
  ``[ref=UUID]…[/ref]`` inline-marker string.  Use
  ``ExtractionResult.citations`` directly and a serializer from
  ``refex.serializers`` (e.g. ``to_jsonl``, ``to_web_annotation``) for
  persistence / round-tripping.
- **Removed `RefMarker.replace_content`** and the
  ``_MARKER_OPEN_FORMAT`` / ``_MARKER_CLOSE_FORMAT`` constants — only
  ``to_ref_marker_string`` called them.  ``RefMarker.set_uuid`` is
  still present for ``citations_to_ref_markers``.

### Cleanup

- Removed dead ``BaseRef.sentence`` attribute — never set or read
  externally; it was part of the hash/eq tuple but otherwise inert.

## 0.6.0 (2026-04-19) — Refactor 2026

Major refactoring of the extraction pipeline. The regex extraction logic is
unchanged; this release adds a typed API layer, multiple output adapters, and
short-form citation resolution.

### New Features

- **Typed citation models** (Stream C): `LawCitation`, `CaseCitation`, `Span`,
  `CitationRelation`, `ExtractionResult` — frozen dataclasses with slots.
- **Strategy-based orchestrator** (Stream C): `CitationExtractor` with pluggable
  `Extractor` engines. Default uses `RegexLawExtractor` + `RegexCaseExtractor`.
- **Output adapters** (Stream D):
  - `to_jsonl()` / `to_json()` — primary JSONL output matching the benchmark spec.
  - `to_spacy_doc()` — spaCy Doc-compatible dict (no spaCy dep required).
  - `to_hf_bio()` — HuggingFace BIO token-classification format.
  - `to_gliner()` — GLiNER span format.
  - `to_web_annotation()` — W3C Web Annotation Data Model.
  - `to_akn_ref()` — Akoma Ntoso / LegalDocML.de XML fragments.
- **Artikel / Grundgesetz support** (Stream E): `Art.` / `Artikel` patterns for
  German constitutional and EU law citations.
- **Short-form resolution** (Stream I): bare `§ 5` inherits book from prior
  `§ 3 BGB`; reporter citations (BGHZ, BVerfGE, etc.) linked to prior full
  case citations.
- **Relation detection** (Stream I): `i.V.m.`, `vgl.`, `a.a.O.`, `ebenda`,
  `siehe dort` detected between adjacent citations.
- **Input format handling** (Stream J): `Document` model with format-aware
  normalization (plain/HTML/Markdown), offset maps for span round-tripping.
- **Reporter citation extraction**: `BGHZ 132, 105`, `NJW 2003, 1234`, etc.
  — ~40 German legal reporter abbreviations recognized.
- **`STRUCTURE_KEYS`**: frozenset of 21 valid structure dict keys for
  `LawCitation.structure`.

### Improvements

- **Precise law book regex** (B7): 1,105 law book codes loaded from bundled
  data file, sorted longest-first with generic fallback.
- **Pre-compiled regex patterns** (B5): patterns compiled once at init, not
  per call.
- **Fixed mutable class defaults** (B1, B6): `RefMarker.references` and
  `law_book_codes` are now instance-level.
- **Fixed `Ref.__eq__`** (B3): returns `NotImplemented` for foreign types.
- **Fixed `Ref.__hash__`** (B4): hashes full field tuple, not `__repr__`.
- **Deleted legacy `law.py`** (B9): 410-line near-duplicate removed; unique
  behaviors ported to `law_dnc.py`.

### Deprecations

- `RefExtractor.extract(is_html=True)` emits a `DeprecationWarning`. Use
  `CitationExtractor().extract(text, fmt="html")` instead.
- The `[ref=UUID]...[/ref]` marker format is deprecated. Use JSONL output via
  `to_jsonl()` for new integrations.

### Backward Compatibility

- `RefExtractor` is preserved and works as before.
- `RefExtractor.extract_citations()` bridges to the new typed API.
- All legacy tests remain green.

### Metrics (preview_1000 benchmark)

| Metric | Before | After | Delta |
|--------|--------|-------|-------|
| Span F1 (exact) | 0.541 | 0.656 | +21.3% |
| Law F1 (exact) | 0.700 | 0.755 | +7.9% |
| Case F1 (exact) | 0.175 | 0.464 | +165% |

## 0.5.0 (2026-04-18)

- Stream H partial: wired legacy `RefExtractor` to new orchestrator.

## 0.4.2

- Previous release.
