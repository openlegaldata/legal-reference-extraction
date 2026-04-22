# Changelog

## 0.5.0 — Refactor 2026

Major refactoring of the extraction pipeline.  Adds a typed API
layer, multiple output adapters, short-form citation resolution,
format-aware input handling (plain / HTML / Markdown), optional
CRF and transformer inference engines, and a published
German-legal-citation fine-tune on Hugging Face Hub.

Regex F1 unchanged on the validation split; the transformer engine
adds a measurable +4.9 pp span-overlap F1 over the regex baseline.

### New Features

- **Typed citation models** (Stream C): `LawCitation`, `CaseCitation`,
  `Span`, `CitationRelation`, `ExtractionResult` — frozen dataclasses
  with `__slots__`.
- **Strategy-based orchestrator** (Stream C): `CitationExtractor` with
  pluggable `Extractor` engines; default uses `RegexLawExtractor` +
  `RegexCaseExtractor`.
- **Output adapters** (Stream D):
  - `to_jsonl()` / `to_json()` — primary JSONL output matching the
    benchmark spec.
  - `to_spacy_doc()` — spaCy Doc-compatible dict (no spaCy dep
    required).
  - `to_hf_bio()` — HuggingFace BIO token-classification format.
  - `to_gliner()` — GLiNER span format.
  - `to_web_annotation()` — W3C Web Annotation Data Model.
  - `to_akn_ref()` — Akoma Ntoso / LegalDocML.de XML fragments.
- **Artikel / Grundgesetz support** (Stream E): `Art.` / `Artikel`
  patterns for German constitutional and EU law citations.
- **Short-form resolution** (Stream I): bare `§ 5` inherits the book
  from a prior `§ 3 BGB`; reporter citations (BGHZ, BVerfGE, …)
  linked to their prior full case citations.
- **Relation detection** (Stream I): `i.V.m.`, `vgl.`, `a.a.O.`,
  `ebenda`, `siehe dort` detected between adjacent citations.
- **Input format handling** (Stream J): `Document` model with
  format-aware normalization (plain / HTML / Markdown), offset maps
  for span round-tripping.
- **Reporter citation extraction**: `BGHZ 132, 105`, `NJW 2003, 1234`,
  etc. — ~40 German legal reporter abbreviations recognized.
- **`STRUCTURE_KEYS`**: frozenset of 21 valid structure dict keys
  for `LawCitation.structure`.
- **CRF inference engine** (Stream F): `RegexCRFExtractor` with
  `sklearn-crfsuite` feature extractor + streaming trainer.
- **Transformer inference engine** (Stream G): `TransformerExtractor`
  with sliding-window tokenisation, first-token-of-word aggregation,
  CPU / CUDA / MPS inference, and batched `extract_batch(...)`.
- **Published default transformer model**:
  [`openlegaldata/legal-reference-extraction-base-de`](https://huggingface.co/openlegaldata/legal-reference-extraction-base-de)
  (CC BY-NC 4.0) — a fine-tune of `EuroBERT/EuroBERT-210m` for
  German legal law / case citation BIO tagging.
  `refex.engines.transformer.DEFAULT_MODEL` points at this repo, so
  `TransformerExtractor()` with no args loads it by default.
- **`default_unit` column** in `law_book_codes.txt`.  Optional
  tab-separated `<unit>` column (`article` / `paragraph`); when
  present, overrides the text-prefix heuristic in
  `_law_markers_to_citations`.  23 high-confidence annotations
  curated (`GG` / `EUV` = article; `BGB` / `HGB` / `StGB` / `StPO` /
  `ZPO` / … = paragraph).  New `get_unit_hint(code)` helper on the
  law extractor mixin.
- **Structure key-level accuracy metric** in `BenchmarkResult`
  (A2c).  `field_accuracy['structure']` accumulates per-key
  `correct` / `incorrect` / `missing_pred` / `missing_gold` on
  exact-matched law pairs.
- **Relation-edge F1 metric** in `BenchmarkResult` (A2d).
  `relation_exact: PRF` scored as `(source_span, target_span,
  relation)` triples.  Benchmark runner accepts `extract_fn`
  returning either `list[Citation]` (legacy) or `(citations,
  relations)`.
- **`REFEX_PRECISE_BOOK_REGEX` env var**.  Toggles
  `use_precise_book_regex` at runtime for A/B measurement of the
  precise vs generic book-code regex.  Default `True` (matches the
  exact-F1 optimization metric).

### Improvements

- **Precise law book regex** (B7): 1,948 law book codes loaded from
  the bundled data file, sorted longest-first with a generic
  fallback.
- **Pre-compiled regex patterns** (B5): all patterns compiled once
  at init instead of per call.
- **Fixed mutable class defaults** (B1, B6): `RefMarker.references`
  and `law_book_codes` are now instance-level.
- **Fixed `Ref.__eq__`** (B3): returns `NotImplemented` for foreign
  types.
- **Fixed `Ref.__hash__`** (B4): hashes the full field tuple, not
  `__repr__`.
- **Interval-based marker masking** in `law.py`.  Each extraction
  phase now collects match spans and applies a single
  O(len(content)) mask pass at the end of the phase instead of
  O(N × len) per-marker calls.  +1 % throughput; F1 unchanged.

### Breaking

- **Removed `refex.compat.to_ref_marker_string`.**  It emitted the
  legacy ``[ref=UUID]…[/ref]`` inline-marker string.  Use
  `ExtractionResult.citations` directly and a serializer from
  `refex.serializers` (e.g. `to_jsonl`, `to_web_annotation`) for
  persistence / round-tripping.
- **Removed `RefMarker.replace_content`** and the
  `_MARKER_OPEN_FORMAT` / `_MARKER_CLOSE_FORMAT` constants — only
  `to_ref_marker_string` called them.  `RefMarker.set_uuid` is still
  present for `citations_to_ref_markers`.
- **Removed dead model surface:** `BaseRef.sentence`,
  `RefMarker.get_length` / `get_start_position` / `get_end_position`,
  `Ref.get_law_repr` / `get_case_repr`, `@total_ordering` on `Ref`
  — none had external callers.
- **Deleted legacy `src/refex/extractors/law.py`** (410 LOC,
  pre-refactor) and **renamed `law_dnc.py` → `law.py`**; the
  divide-and-conquer extractor now lives at the canonical filename.

### Deprecations

- `RefExtractor.extract(is_html=True)` emits a `DeprecationWarning`.
  Use `CitationExtractor().extract(text, fmt="html")` instead.
- The `[ref=UUID]...[/ref]` marker format is deprecated.  Use JSONL
  output via `to_jsonl()` for new integrations.

### Backward Compatibility

- `RefExtractor` is preserved and works as before.
- `RefExtractor.extract_citations()` bridges to the new typed API.
- `refex.compat.citations_to_ref_markers()` converts typed
  `ExtractionResult` → legacy `list[RefMarker]` for Open Legal
  Data's internal pipeline.
- All legacy tests remain green.

### Closed follow-ups (measured and rejected)

- **Aho–Corasick court-name index** — pure-Python variant regressed
  throughput −35.6 % because Python's C ``re`` engine beats a
  single-pass scan on typical docs; a C-backed AC dep is out of
  scope.
- **Per-`(doc_id, fn_span)` court cache** — 16.9 % same-fn
  recurrence is real, but court resolution is position-dependent;
  cache-first regresses span F1, fresh-first with cache fallback
  regresses court-field accuracy and throughput.  See
  `docs/refactor2026/optimization_log.md` §"§7/#8" and §"§7/#9".

### Metrics (benchmark validation split, 821 docs)

| Engine                     | span F1 (exact) | span F1 (overlap) | Throughput |
|----------------------------|----------------:|------------------:|-----------:|
| Regex baseline (CPU)       |           0.734 |             0.815 |  ~470 docs/s |
| Regex + CRF (CPU)          |           0.741 |             0.842 |   ~90 docs/s |
| Transformer EuroBERT (MPS) |           0.509 |         **0.913** |  ~1.5 docs/s |
| Regex + Transformer (MPS)  |       **0.743** |             0.852 |  ~1.5 docs/s |

### Tests & benchmarks

- **~347 tests** covering the new typed API, engines, adapters,
  document normalization, benchmark metrics (including the new
  structure and relation-edge metrics), law / case extractor edge
  cases, and the regex interval-masking / env-var / default-model
  internals.

## 0.4.2

- Previous release.
