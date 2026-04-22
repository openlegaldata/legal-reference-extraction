# Changelog

## 0.7.0 (2026-04-22) — Refactor 2026 (Final)

Closes the remaining §7 open follow-ups from the 0.6.0 refactor and
ships the first openlegaldata-trained transformer model.  Regex F1
unchanged on the validation split; transformer adds a measurable
+4.9 pp span-overlap F1 over the regex baseline.

### New Features

- **Default transformer model published** to Hugging Face Hub at
  [`openlegaldata/legal-reference-extraction-base-de`](https://huggingface.co/openlegaldata/legal-reference-extraction-base-de)
  (CC BY-NC 4.0) — an EuroBERT-210m fine-tune for German legal law /
  case citation BIO tagging.  `refex.engines.transformer.DEFAULT_MODEL`
  now points at this repo, so `TransformerExtractor()` with no args
  loads it by default.
- **`default_unit` column** in `law_book_codes.txt` (Stream E2).
  Optional tab-separated `<unit>` column (`article` / `paragraph`);
  when present, overrides the text-prefix heuristic in
  `_law_markers_to_citations`.  23 high-confidence annotations
  curated (`GG`/`EUV` = article; `BGB`/`HGB`/`StGB`/`StPO`/`ZPO`/…
  = paragraph).  New `get_unit_hint(code)` helper on the law
  extractor mixin.
- **Structure key-level accuracy metric** in `BenchmarkResult`
  (§7/#1 — A2c).  `field_accuracy['structure']` accumulates
  per-key correct / incorrect / missing_pred / missing_gold on
  exact-matched law pairs.
- **Relation-edge F1 metric** in `BenchmarkResult` (§7/#2 — A2d).
  `relation_exact: PRF` scored as `(source_span, target_span,
  relation)` triples.  Benchmark runner accepts `extract_fn`
  returning either `list[Citation]` (legacy) or `(citations,
  relations)`.
- **`REFEX_PRECISE_BOOK_REGEX` env var** (§7/#3 — B7).  Toggles
  `use_precise_book_regex` at runtime for A/B measurement of the
  precise vs generic book-code regex.  Default `True` (matches the
  exact-F1 optimization metric).

### Improvements

- **Interval-based marker masking** in `law.py` (§7/#10).  Each
  extraction phase now collects match spans and applies a single
  O(len(content)) mask pass instead of O(N × len) per-marker calls.
  +1 % throughput on the validation split; F1 unchanged.

### Breaking

- **Removed `refex.compat.to_ref_marker_string`.** Deprecated in
  0.6.0 with a ``DeprecationWarning``; it emitted the legacy
  ``[ref=UUID]…[/ref]`` inline-marker string.  Use
  ``ExtractionResult.citations`` directly and a serializer from
  ``refex.serializers`` (e.g. ``to_jsonl``, ``to_web_annotation``).
- **Removed `RefMarker.replace_content`** and the
  ``_MARKER_OPEN_FORMAT`` / ``_MARKER_CLOSE_FORMAT`` constants — only
  ``to_ref_marker_string`` called them.  ``RefMarker.set_uuid`` is
  still present for ``citations_to_ref_markers``.
- **Removed dead model surface:** `BaseRef.sentence`,
  `RefMarker.get_length` / `get_start_position` / `get_end_position`,
  `Ref.get_law_repr` / `get_case_repr`, `@total_ordering` on `Ref`
  — none had external callers.
- **Renamed `src/refex/extractors/law_dnc.py` → `law.py`.**  The
  legacy `law.py` (pre-refactor, deleted in 0.6.0 Stream B9) is
  gone; the divide-and-conquer extractor now lives at the canonical
  filename.

### Closed follow-ups (measured and rejected)

- **Aho–Corasick court-name index** (§7/#8) — pure-Python variant
  regressed throughput −35.6 % because Python's C ``re`` engine
  beats a single-pass scan on typical docs; a C-backed AC dep is
  out of scope.
- **Per-`(doc_id, fn_span)` court cache** (§7/#9) — 16.9 % same-fn
  recurrence is real, but court resolution is position-dependent;
  cache-first regresses span F1, fresh-first with cache fallback
  regresses court-field accuracy and throughput.  See
  ``docs/refactor2026/optimization_log.md`` §"§7/#8" and §"§7/#9".

### Tests & benchmarks

- **334 → 337+ tests.**  New: `test_benchmark_metrics.py` (A2c/A2d),
  `test_unit_hints.py` (E2), plus env-var and interval-mask
  coverage.  Removed: `test_law_legacy.py` (coverage merged into
  `test_law_extractor.py` / `test_edge_cases.py`), duplicate
  `test_ref_marker_replace_content_with_mask`, two perpetually
  skipped tests.

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
