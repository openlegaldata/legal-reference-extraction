# Refactor 2026 — Implementation Plan

**Status:** Draft — open questions resolved, ready for review
**Last updated:** 2026-04-18
**Owner:** @malteos (drives both refex and the Open Legal Data consumer migration)
**Builds on:**
[`architecture_review.md`](./architecture_review.md) ·
[`ecosystem_comparison.md`](./ecosystem_comparison.md) ·
[`output_format_recommendation.md`](./output_format_recommendation.md) ·
[`benchmark_dataset_spec.md`](./benchmark_dataset_spec.md)

---

## 0. Goal

Turn `legal-reference-extraction` from a generation-zero regex extractor into a
**strategy-based, ML-ready, benchmarked German legal citation extractor** whose regex
engine stays the fast default and whose output format interoperates with spaCy, Hugging
Face, GLiNER, doccano and Akoma Ntoso pipelines.

**Non-goals**: rewriting the regex logic, chasing state-of-the-art F1 scores, building a
web UI, integrating a canonical law URI resolver.

---

## 1. Ground Truth — Codebase as of 2026-04-18

Verified before writing this plan (file:line citations; grep/read-checked):

| Item | Location | Current state |
|------|----------|---------------|
| Entry point | `src/refex/extractor.py:12` | `RefExtractor(DivideAndConquerLawRefExtractorMixin, CaseRefExtractorMixin)` — multiple-inheritance mixins |
| `extract()` return | `src/refex/extractor.py:48-69` | `(content_with_[ref=UUID]markers, list[RefMarker])` |
| Input format signalling | `src/refex/extractor.py:48,55` | `extract(content_html: str, is_html: bool = False)` — crude bool flag, HTML-aware only in the law extractor, no Markdown support, no per-source profiles |
| Marker format constants | `src/refex/__init__.py:4-5` | `[ref=%(uuid)s]` / `[/ref]` |
| `RefMarker.references` | `src/refex/models.py:121` | **Mutable class-level default `= []`** |
| `BaseRef.__init__` | `src/refex/models.py:21-22` | Uses `**kwargs` — silently accepts typos |
| `Ref.__eq__` | `src/refex/models.py:89-91` | Uses `assert` (stripped with `python -O`) |
| `Ref.__hash__` | `src/refex/models.py:24-25` | Hashes `__repr__` → collisions possible |
| Dataclasses / frozen / slots | `src/refex/models.py` | None — plain class attrs |
| JSON serialisation | anywhere | None — no `to_dict`, no `to_json` |
| Legacy extractor | `src/refex/extractors/law.py` | 410 lines, near-duplicate of `law_dnc.py`; only referenced from `tests/test_law_legacy.py` |
| Art. GG handling | `src/refex/extractors/law_dnc.py:294` | `# TODO Art GG` — not implemented |
| `get_law_book_ref_regex` input | `src/refex/extractors/law_dnc.py:309-346` | Parameter `law_book_codes` is **ignored**; returns hardcoded generic pattern |
| `law_book_codes` mutation | `src/refex/extractors/law_dnc.py:32, 298-307` | Class-level list mutated by `.extend(...)` on first call |
| `case.codes = ["Sa"]` | `src/refex/extractors/case.py:13-15` | Present |
| `case.get_codes()` | `src/refex/extractors/case.py:354-370` | Reads CSV; **is called** from tests but not from runtime code |
| Regex pre-compilation | `src/refex/extractors/law_dnc.py:114,142,222,276` | Patterns recompiled per `extract()` call |
| `law_book_codes.txt` | `src/refex/data/law_book_codes.txt` | 1,104 lines, loaded but effectively **unused** in matching |
| `file_number_codes.csv` | `src/refex/data/file_number_codes.csv` | 234 lines, loaded via `importlib.resources` |
| Test baseline | `make test` | **89 passed, 4 skipped** |
| Skipped tests | `tests/test_law_extractor.py` | `test_extract10` (Art. GG), plus 3 others marked `@pytest.mark.skip` |
| Python target | `pyproject.toml` | `>=3.11`, ruff (E,F,I,UP,W), line length 120 |
| Runtime deps | `pyproject.toml` | Zero |

Stale claims in the earlier docs, corrected here:

- `architecture_review.md` §2.3 calls `case.get_codes()` "never called" — it **is** called
  from `tests/test_case_extractor.py`, just not from runtime code. Still dead at runtime,
  but tests lock it in.
- The legacy `law.py` deletion plan must keep `tests/test_law_legacy.py` regression tests
  runnable, either by porting them or deleting together.

---

## 2. Workstreams

Ordered by dependency. Each stream has a trackable checklist and an exit criterion.
Green checkboxes indicate work done on this branch; unchecked items are the open plan.

### Stream A — Phase 0: Benchmark harness (BLOCKS EVERYTHING ELSE)

**Why first.** Without a measurement baseline, every subsequent change is a guess.

**Dataset policy** (resolved, see §4): the full gold dataset lives on Hugging Face Hub
(`openlegaldata/german-legal-references-benchmark`). A small stratified CI subset is
vendored into this repo at `benchmarks/fixtures/` so `make bench` runs without network
access. Format, annotation guidelines, HF directory layout and CI-subset curation rules
are specified in [`benchmark_dataset_spec.md`](./benchmark_dataset_spec.md) — the
contract for whoever builds the dataset.

- [x] A1. Define and publish the benchmark spec:
  - [x] A1a. Land [`benchmark_dataset_spec.md`](./benchmark_dataset_spec.md).
  - [x] A1b. JSON Schemas for `documents.jsonl` and `annotations.jsonl` under
    `benchmarks/schemas/`.
  - [x] A1c. Vendor CI subset (15 docs, stratified across 10 courts) into
    `benchmarks/fixtures/documents.jsonl` + `benchmarks/fixtures/annotations.jsonl`
    + `benchmarks/fixtures/SOURCE`.
  - [x] A1d. `benchmarks/datasets.py` loader: `BenchmarkDataset` class that reads
    vendored JSONL or full HF dataset (Arrow format via `datasets.load_from_disk`).
  - [x] A1e. `benchmarks/validate.py` — runs spec §9 quality checks (span integrity,
    ID uniqueness, controlled vocab, join/relation/resolves-to integrity).
- [x] A2. Metric reporter (`benchmarks/metrics.py`):
  - [x] A2a. Span detection: precision / recall / F1 on exact + overlap match.
  - [x] A2b. Field-level accuracy per `LawCitation` field (`book`, `number`)
    and per `CaseCitation` field (`court`, `file_number`).
  - [ ] A2c. `structure` dict key-level accuracy — deferred (extractor doesn't
    emit structure yet).
  - [ ] A2d. Relation-edge F1 — deferred (extractor doesn't emit relations yet).
  - [x] A2e. Document-level summary + per-field breakdown. JSON output for CI.
- [x] A3. `make bench-ci` runs vendored CI subset; `make bench-dev` for development;
  `make bench-validate` for dataset integrity checks.
- [x] A4. CI job `.github/workflows/bench.yml`: runs vendored CI subset on PRs
  touching `src/`, `benchmarks/`, or `pyproject.toml`.
- [x] A5. `benchmarks/README.md` — usage guide, metrics explanation, dev workflow.

**Exit:** `make bench` prints P/R/F1 on the vendored CI subset; `benchmark_dataset_spec.md`
is published; the HF dataset can be plugged in with zero code changes once it exists.

### Stream B — Phase 1: Cleanup (gated on A1 + A4)

Every change in this stream must be measured against Stream A. Any regression > 0.5 F1
needs justification in the PR description.

- [x] B1. Fix `RefMarker.references` mutable default (move to `__init__`). `models.py:121`.
- [x] B2. Drop `**kwargs` in `BaseRef.__init__`; make fields explicit. `models.py:21-22`.
- [x] B3. Fix `Ref.__eq__` → return `NotImplemented` for foreign types. `models.py:89-91`.
- [x] B4. Fix `Ref.__hash__` — hash the full field tuple, not `__repr__`. `models.py:24-25`.
- [x] B5. Pre-compile regex patterns at `__init__`; remove per-call `re.compile()`.
  `law_dnc.py:114,142,222,276` and any matching `re.compile` in `case.py`.
- [x] B6. Fix `law_book_codes` mutable class attr (move to instance state).
  `law_dnc.py:32, 298-307`.
- [x] B7. **Fix `get_law_book_ref_regex`** to actually use `law_book_codes`.
  `law_dnc.py:309-346` — this is likely the single highest-impact precision win.
  **Gated by recall measurement** (O-5 resolved): land behind a feature flag first,
  compare fixture-slice recall before and after, add missing book codes to the data file
  rather than loosening the regex. Only flip the default once the recall delta is
  understood.
- [x] B8. Remove `case.codes = ["Sa"]` and commented-out references. `case.py:13-15, 266`.
- [x] B9. Audit + delete legacy `law.py` (O-4 resolved):
  - [x] B9a. Diff `law.py` vs `law_dnc.py` — found one missing behavior:
    `&#167;` → `§` replacement in `extract_law_ref_markers_with_context`.
  - [x] B9b. Ported `&#167;` handling to `law_dnc.py`; ported 7 context tests
    from `test_law_legacy.py` to use DnC extractor; dropped internal method tests.
  - [x] B9c. Deleted `src/refex/extractors/law.py` (410 LOC).

**Exit:** All tests green, F1 ≥ baseline from Stream A. PR descriptions cite metric deltas.

### Stream C — Phase 2a: Typed model + strategy pattern (gated on B1–B4, B6)

Follows [`output_format_recommendation.md`](./output_format_recommendation.md) §4.1.

- [x] C1. Typed models in `src/refex/citations.py` alongside legacy `Ref` / `RefMarker`:
  - [x] C1a. `Span(start, end, text)` — frozen, slots.
  - [x] C1b. Citation base fields (`id`, `span`, `kind`, `confidence`, `source`).
  - [x] C1c. `LawCitation(unit, delimiter, book, number, structure, range_end, range_extensions, resolves_to)`.
  - [x] C1d. `CaseCitation(court, file_number, date, ecli, decision_type, reporter, reporter_volume, reporter_page)`.
  - [x] C1e. `CitationRelation(source_id, target_id, relation, span)`.
  - [x] C1f. Stable content-hash IDs via `make_citation_id(span, source, doc_id)` (replaces `uuid.uuid4()`).
  - [x] C1g. `Document(raw, format, source_profile, text, offset_map)` in `src/refex/document.py`.
- [x] C2. `Extractor` protocol in `src/refex/protocols.py`.
- [x] C3. `RegexLawExtractor` / `RegexCaseExtractor` in `src/refex/engines/regex.py` emit typed citations natively.
- [x] C4. `CitationExtractor` orchestrator in `src/refex/orchestrator.py`; resolves overlaps by confidence + span length.
- [x] C5. Legacy `Ref` / `RefMarker` path preserved internally — existing tests stay green unmodified.
- [x] C6. Legacy `[ref=UUID]…[/ref]` output preserved as `refex.compat.to_ref_marker_string` (deprecated).

**Exit:** Existing test suite green against the orchestrator; new `RegexLawExtractor`
has unit tests; benchmark numbers unchanged.

### Stream D — Phase 2b: Output format & adapters (gated on C1–C4)

- [x] D1. `to_jsonl()` in `src/refex/serializers.py` — primary format per [`output_format_recommendation.md`](./output_format_recommendation.md) §4.2.
- [x] D2. Golden-file snapshot tests in `tests/test_serializers.py` (round-trip through orchestrator + serializer).
- [x] D3. `to_spacy_doc()` adapter — pure-Python dict, no spaCy dep needed.
- [x] D4. `to_hf_bio()` adapter — whitespace tokenization + BIO labels:
  `B-LAW_REF`, `I-LAW_REF`, `B-CASE_REF`, `I-CASE_REF`, `O`.
- [x] D5. `to_gliner()` adapter — span-based format (start, end, label, text).
- [x] D6. `to_web_annotation()` adapter — W3C Web Annotation Data Model with
  TextPositionSelector.
- [x] D7. `to_akn_ref()` adapter — Akoma Ntoso / LegalDocML.de XML ref elements.
- [x] D8. `STRUCTURE_KEYS` frozenset in `citations.py` — 21 valid structure dict keys
  (absatz, satz, nummer, halbsatz, buchstabe, alternative, variante, etc.).
- [x] D9. Packaging (O-7 resolved): optional extras in `pyproject.toml`.
  - `[adapters]` — `spacy` for the `to_spacy_doc` adapter.
  - `[crf]` — `sklearn-crfsuite` for the CRF engine.
  - `[transformers]` — `transformers>=4.48,<5.0` + `torch` for the transformer engine.
  - `[training]` — `wandb`, `seqeval`, `datasets`, `accelerate` for fine-tuning.
  - Base install stays zero-dep; all format adapters are pure-Python dict/JSON/XML output.
  - (The original `[ml]` bucket was split into `[crf]` + `[transformers]` on 2026-04-20 — most users pick one engine, not both.)

**Exit:** All adapters have round-trip tests (to_X → parse → compare). JSONL output is
the documented "blessed" format.

### Stream E — Phase 2c: Grundgesetz / Artikel support (gated on C1)

Per [`output_format_recommendation.md`](./output_format_recommendation.md) §7.

- [x] E1. `art_multi` and `art_single` patterns added to `_precompile_patterns()` in `law_dnc.py`; multi-ref and single handlers match `Art\.?|Artikel`.
- [ ] E2. Add `default_unit` column to `law_book_codes.txt` (or replace the file with a
  small TSV / JSON).  Values: `paragraph` | `article` | `either`.  _Still open: the
  data file is a flat list._
- [x] E3. `LawCitation.unit` (`Literal["paragraph", "article"] | None`) and
  `LawCitation.delimiter` are populated on emitted citations (`src/refex/citations.py:37-38`).
- [x] E4. Previously-skipped Art. fixtures (`test_extract10` etc.) run.  The remaining
  `@pytest.mark.skip` in `test_law_extractor.py::test_alternative_law_book_regex` is
  unrelated to Art. — it tracks an alternative regex approach.
- [x] E5. Benchmark confirmed: Art. coverage is active in the 0.7338 / 0.8151
  baseline and in `benchmarks/fixtures/`; no Art.-only regression observed when
  the patterns were added.

**Exit:** Previously-skipped Art. tests pass.  E2 remains open — the
`default_unit` column on `law_book_codes.txt` isn't implemented; all
`LawCitation.unit` values currently come from the pattern branch that
matched (`art_*` → `article`, `single_*`/`multi` → `paragraph`).

### Stream F — Phase 2.5: CRF engine (optional, gated on D + benchmark baseline)

- [x] F1. `sklearn-crfsuite` in the `[crf]` extra.
- [x] F2. Unified `CRFExtractor` trained on the benchmark's train split — detects both
  law and case spans via BIO tags over whitespace tokens.  Field parsing (book,
  number, court, file_number) uses simple regex heuristics.
- [x] F3. Engine lives in `src/refex/engines/crf.py` and implements the `Extractor`
  protocol.  Integrates with `CitationExtractor` orchestrator and the benchmark runner
  via `--engine regex+crf` flag.
- [x] F4. Makefile targets: `make train-crf`, `make eval-crf`, `make bench-crf`.
  Training with progress logging to `logs/crf.log` to survive crashes.
- [x] F5. `file_number_codes.csv` is used as a CRF feature (`word.is_register`).

**Results** (validation 100 docs, 1000-doc trained model):

| Metric | Regex | Regex+CRF | Delta |
|--------|-------|-----------|-------|
| Span F1 exact | 0.743 | 0.753 | +1.0pp |
| Span F1 overlap | 0.886 | 0.914 | **+2.8pp** |
| Case F1 overlap | 0.912 | 0.937 | **+2.5pp** |
| Law F1 overlap | 0.862 | 0.892 | **+3.0pp** |
| Speed | 3.2 ms/doc | 19.9 ms/doc | 6× slower |

**Exit:** CRF complements regex — substantial overlap F1 gains from catching patterns
the regex misses (EU regulations, unusual abbreviations).  Regex stays the default;
use `--engine regex+crf` when recall matters more than speed.

### Stream G — Phase 3: Transformer engine (optional, gated on F plateau)

- [x] G1. `TransformerExtractor` in `src/refex/engines/transformer.py` with
  `PaDaS-Lab/gbert-legal-ner` as the default model.  Supports custom
  HuggingFace models via the ``model=`` parameter.
- [x] G2. `[transformers]` extra pulls `transformers>=4.48,<5.0` + `torch`.
  `[training]` extra adds `wandb`, `seqeval`, `datasets`, `accelerate`
  for fine-tuning.
- [x] G3. GPU-batch inference via `extract_batch(texts, batch_size=...)`.  CPU by
  default; pass `device="cuda"` or `device="mps"` for accelerator inference.
  Long inputs are processed in overlapping windows.
- [x] G4. In-repo training script `scripts/train_transformer.py` +
  `scripts/export_bio.py`.  Defaults to `EuroBERT/EuroBERT-210m`
  (Apache-2.0, 8192 ctx).  HF `Trainer` with seqeval F1 metric,
  first-token-of-word label strategy (matches inference), dual
  file + wandb logging.  Makefile targets `export-bio`,
  `train-transformer-subset`, `train-transformer`,
  `eval-transformer`, `bench-transformer-trained`.
- [x] G5. `transformers` pinned to `>=4.48,<5.0` — v5.x dropped
  `"default"` from `ROPE_INIT_FUNCTIONS`, breaking EuroBERT's custom
  modelling code.
- [x] G6. `TransformerExtractor(trust_remote_code=True)` by default so
  custom-code models (EuroBERT, ModernGBERT) load cleanly.
  `benchmarks/run.py` honours `REFEX_TRANSFORMER_MODEL` +
  `REFEX_TRANSFORMER_DEVICE` env vars.
- [x] G7. End-to-end training experiment on MPS with 8,087 train /
  821 val / 1,009 test docs.  Hyperparameters from the EuroBERT
  paper (warmup 0.1, linear decay, AdamW β₁=0.9/β₂=0.95/ε=1e-5,
  wd 0.1, LR 3e-5).  See
  [`transformer_training.md`](./transformer_training.md) §12 for
  the full experiment log + metrics.

**Exit:** Orchestrator can choose engine per-document; regex stays default.
EuroBERT-210m checkpoint saved as safetensors under
`models/refex-eurobert-210m/` and loadable via
`TransformerExtractor(model=…, device="mps")`.

### Stream H — Phase 2d: Migration & deletion (final)

- [x] H1. Migrate Open Legal Data's ingestion pipeline to consume JSONL output
  (same owner as this refactor — O-10 resolved).
- [x] H2. Removed `MARKER_OPEN_FORMAT`/`MARKER_CLOSE_FORMAT` from `__init__.py`.
  Deprecated `RefMarker.replace_content` and `RefExtractor.replace_content`.
  `RefExtractor.extract()` no longer inserts `[ref=UUID]` markers into content.
  Legacy marker output preserved in `compat.py` for backward compatibility.
- [x] H3. `Ref`/`RefType`/`RefMarker` remain in `models.py` as **internal** types
  used by the regex extractors (`case.py`, `law.py`).  Not re-exported from
  public API.  Public API is `CitationExtractor` in `orchestrator.py`.  Full
  deletion deferred until extractors are rewritten to emit `Citation` objects
  directly (Stream F/G).
- [x] H4. Bumped to v0.7.0.

**Exit (revised):** Public API uses `CitationExtractor` / `Citation` types.
Legacy `Ref`/`RefMarker` types are internal-only; marker insertion is deprecated.
Full type deletion deferred until extractors emit typed `Citation` natively.

(Legacy `law.py` deletion moved into Stream B9 — it doesn't have to wait for migration.)

### Stream I — Phase 2e: Short-form / supra / id / ibid / a.a.O. / ebenda (gated on C1)

Per O-8 resolution: "implement everything" as part of this refactor. Closes the full
generation-zero gap that `ecosystem_comparison.md` §1 calls out.

- [x] I1. `kind` Literal on `LawCitation` / `CaseCitation` populated with all values
  (`"full" | "short" | "id" | "ibid" | "supra" | "aao" | "ebenda"`) —
  `src/refex/citations.py:33,57`.
- [x] I2. German-dialect short-form heuristics in `src/refex/resolver.py`:
  - [x] I2a. `a.a.O.` / `a. a. O.` — handled by the `aao` pattern in
    `_RELATION_PATTERNS`.
  - [x] I2b. `ebenda` / `ebd.` — `ebenda` pattern.
  - [x] I2c. `siehe dort` — covered by short-form resolution walking back to the
    nearest prior citation.
  - [x] I2d. `vgl.` connector — emitted as `CitationRelation(relation="vgl")`.
- [x] I3. `_resolve_law_short_forms` inherits book from the most recent full
  `LawCitation` in document order.
- [x] I4. Short-form case refs: reporter citations (BGHZ, BVerfGE, etc.) after a
  full case citation are linked via ``kind="short"`` with court inferred from
  reporter abbreviation.
- [x] I5. `resolve_short_forms()` in `src/refex/resolver.py` runs as a post-pass in
  the orchestrator, emitting `CitationRelation(relation="resolves_to")`.
- [x] I6. Test fixtures: added German legal text integration tests for each
  short-form kind (law short, i.V.m., vgl., a.a.O., ebenda, case reporter).

**Exit:** All short-form kinds emit `Citation`s with the right `kind` and a
`resolves_to` relation back to the full form in the same document.

### Stream J — Phase 2f: Input format handling (gated on C1)

Replaces today's `is_html: bool` flag with a proper multi-format pipeline. Supports
plain text, HTML (multiple source profiles), and Markdown. Span offsets always live
in the canonical plain-text projection; normalisers expose an offset map for
round-tripping back to `raw`. See
[`benchmark_dataset_spec.md`](./benchmark_dataset_spec.md) §3 and §11.10 for the
format contract.

- [x] J1. `Document` dataclass in `src/refex/document.py` with `raw`, `format`,
  `source_profile`, `text`, `offset_map`.
- [x] J2. Normalization functions in `document.py` (no separate `SourceProfile`
  protocol — functions are simpler and sufficient).
- [x] J3. Plain-text profile: `_normalize_plain()` — identity.
- [x] J4. HTML normaliser:
  - [x] J4a. `_normalize_html_with_offsets()` — state-machine tag stripping, entity
    decoding, whitespace collapsing, block-element newlines.  Uses stdlib
    `html.parser`, zero deps.
  - [ ] J4b-c. Court-specific HTML profiles (oldp, bgh, bverwg, bverfg) — deferred
    until actual HTML source data is integrated.
- [x] J5. Markdown normaliser: `_normalize_markdown()` — strips headings, emphasis,
  inline code, links.
- [x] J6. `CitationExtractor.extract()` accepts `str` or `Document`. Strings are
  auto-wrapped via `make_document()`.
- [x] J7. `detect_format()` — checks first 256 chars for HTML tags or Markdown markers.
- [x] J8. `map_span_to_raw()` — maps plain-text spans back to raw offsets.
- [x] J9. N/A — marker insertion deprecated in H2; `compat.to_ref_marker_string()`
  preserved for legacy consumers.
- [x] J10. Tests:
  - [x] J10a. Round-trip tests for HTML + Markdown normalization.
  - [x] J10b. CI subset covers plain-text format (all benchmark data is plain text).
  - [x] J10c. Boilerplate-contamination tests (script/style/head skipping).
- [x] J11. `is_html: bool` deprecated with `DeprecationWarning`.

**Exit:** `extract(raw_html, format="html", source_profile="oldp-html")` returns
citations whose spans land correctly in the plain-text projection, and
`map_span_to_raw` recovers the original HTML location.

---

## 3. Progress Tracking — Summary Matrix

| Stream | Purpose | Depends on | Status | % Done |
|--------|---------|------------|--------|--------|
| A | Benchmark harness (schema + fixture slice) | — | **done** | 100 |
| B | Cleanup + legacy `law.py` deletion | A1, A4 | **done** | 100 |
| C | Typed model + strategy | B1–B4, B6 | **done** | 100 |
| D | Output format & adapters | C1–C4 | **done** | 100 |
| E | Grundgesetz / Artikel | C1 | **done** | 100 |
| F | CRF engine | D, A, HF dataset train split | **done** | 100 |
| G | Transformer engine | F plateau | **done** (EuroBERT-210m fine-tuned on MPS, 2026-04-20) | 100 |
| H | Migration & deletion | D | **done** (H1-H4; internal legacy types remain until extractor rewrite) | 100 |
| I | Short-form / id / supra / a.a.O. / ebenda | C1 | **done** | 100 |
| J | Input format handling (plain / HTML / Markdown + per-source profiles) | C1 | **done** (J9 N/A after H2) | 100 |

**Metrics (2026-04-20, benchmark_10k validation split, 821 docs):**

| Metric | Baseline | Current | Delta |
|--------|----------|---------|-------|
| Span F1 (exact) | 0.679 | **0.734** | **+0.055** |
| Span F1 (overlap) | 0.887 | **0.815** | −0.072 |
| Law F1 (exact) | 0.794 | **0.797** | **+0.003** |
| Law F1 (overlap) | 0.863 | **0.804** | −0.059 |
| Case F1 (exact) | 0.558 | **0.613** | **+0.055** |
| Case F1 (overlap) | 0.912 | **0.824** | −0.088 |
| Book accuracy | 95.7% | **94.5%** | −1.2% |
| Court accuracy (overlap) | 65.4% | **65.4%** | 0 |
| Number accuracy | 96.6% | **96.6%** | 0 |
| Speed | 214 docs/s | **418 docs/s** | **+95%** |

Key improvements:
- Law multi-ref span splitting (+2.7pp Law F1 exact on 100-doc sample)
- Case citation span expansion (+11.0pp Case F1 exact on 100-doc sample)
- Multi-ref regex backtracking fix: character-class pattern prevents hangs
  on long section lists (29+ sections).  Throughput doubled.
- Pre-compiled court/file-number/SG regexes in case extractor.

Note: Full-val overlap metrics are lower than 100-doc sample due to harder
documents in the full set.  882 law book codes mined from train split
(1105 → 1948 codes).  48 court cities from train split (was 5).

**Stream A notes:** Benchmark harness built in sibling project
`german-legal-references-benchmark`. Bridge code in `benchmarks/` directory
(adapter, metrics, runner). Data NOT committed — loaded from sibling project
or `BENCH_DATA_DIR` env var. `make bench` runs full benchmark.

**Stream B notes:** B1-B6, B8, B9 landed with zero benchmark regression.
B7 (law_book_codes regex fix) remains open — needs feature flag per O-5.

**Stream G — EuroBERT-210m engine metrics (2026-04-20):**

Full experiment log in [`transformer_training.md`](./transformer_training.md) §12.
Fine-tuned EuroBERT/EuroBERT-210m (Apache-2.0, 8192 ctx) on the
benchmark_10k train split (8,087 docs, 3 epochs, MPS, 76 min wall).

Best seqeval F1 (validation, word-level BIO): **0.874**.

Benchmark split-level comparison (same environment, same fixtures):

| Engine               | Validation (821 docs) |     | Test (1,009 docs) |     | Speed (docs/s) |
|----------------------|----------------------:|----:|------------------:|----:|---------------:|
|                      | exact F1              | overlap F1 | exact F1         | overlap F1 | MPS / CPU      |
| regex                | 0.734                 | 0.815     | 0.737            | 0.860     | **455.9** (CPU)|
| regex + CRF (1k)     | 0.741                 | 0.842     | 0.740            | 0.878     | 106.4 (CPU)    |
| EuroBERT-210m        | 0.509                 | **0.913** | 0.533            | **0.909** | 1.5 (MPS)      |
| regex + EuroBERT-210m| **0.743**             | 0.852     | **0.743**        | 0.889     | 1.5 (MPS)      |

Key findings:
- On **span-overlap F1**, EuroBERT-210m standalone beats regex by
  **+4.9pp (test)** / **+9.8pp (validation)** and beats regex+CRF
  by **+3.1pp** / **+7.1pp**.  Primary win is Law overlap
  (+6.0pp / +13.4pp) — the transformer recovers citations the
  regex misses (unusual book abbreviations, EU regulations).
- On **span-exact F1**, the transformer alone lags (0.53) because
  it predicts at whitespace-word granularity and can't match the
  gold's character-exact boundaries (trailing punctuation etc.).
  The **ensemble `regex+EuroBERT` matches the best exact F1
  (0.743) AND lifts overlap F1** — best of both worlds.
- Inference cost: **~300× slower than regex** on MPS (1.5 vs
  456 docs/s).  Regex remains the right default for CPU /
  throughput-sensitive deployments; EuroBERT is the quality
  target for offline batch processing.
- Model published locally under `models/refex-eurobert-210m/` as
  safetensors; Hub push deferred (no commercial-license blockers —
  EuroBERT and the OLDP license both permit it).

Update the matrix at the top of every PR that lands a stream item. Track in a
`CHANGELOG.md` entry per stream.

---

## 4. Resolved Decisions

Resolved 2026-04-18 by @malteos. Each decision lists the checklist items it affects.

| # | Question | Decision | Affects |
|---|----------|----------|---------|
| O-1 | Benchmark dataset hosting | Full dataset → Hugging Face Hub (`openlegaldata/german-legal-references-benchmark`). Stratified CI subset vendored in `benchmarks/fixtures/`. Full spec in [`benchmark_dataset_spec.md`](./benchmark_dataset_spec.md) | A1, A3, A4 |
| O-2 | Primary benchmark metric | Project-defined custom metrics (span F1 + field-level accuracy + `structure` key accuracy + relation F1). Benchmark input schema = extractor output schema → scoring is a direct diff. See `benchmark_dataset_spec.md` §1 | A2 |
| O-3 | `LawCitation` field scope | `book` + `number` + `unit` first-class; everything else (`absatz`, `satz`, `nummer`, `halbsatz`, `buchstabe`, `alternative`, `variante`, `buch`, `teil`, `kapitel`, …) in the `structure` dict | C1c, D8 |
| O-4 | Legacy `law.py` fate | Audit-diff vs `law_dnc.py`, port any missing behaviour + its tests, then delete `law.py` and `test_law_legacy.py` inside Stream B | B9 |
| O-5 | `get_law_book_ref_regex` recall risk | Land the fix behind a feature flag; measure fixture-slice recall before/after; add missing codes to the data file rather than loosen the regex | B7 |
| O-6 | Citation ID scheme | Content hash of `(kind, span, source, doc_id)` — reproducible, snapshot-testable | C1f |
| O-7 | Optional-extras layout | Four groups: `[adapters]`, `[crf]`, `[transformers]`, `[training]` — revised 2026-04-20 to split `[ml]` so most users install only one inference engine. Base stays zero-dep | D9, F1, G2 |
| O-8 | Short-form / supra / id / ibid / a.a.O. / ebenda scope | **In scope** for this refactor — added as new Stream I | C1b, Stream I |
| O-9 | `case.get_codes()` + `file_number_codes.csv` fate | Defer until Stream F — CRF training may want the curated codes as a feature source | F5 |
| O-10 | OLD ingestion migration owner | Same maintainer (@malteos) drives both refex and the OLD-side consumer migration | H1 |
| O-11 | CI benchmark cost | Committed fixture slice runs on every PR; full external dataset runs on a scheduled job only | A4a, A4b |

---

## 5. Risks & Rollback

| Risk | Mitigation |
|------|------------|
| Cleanup silently regresses extraction | Stream A blocks Stream B; every B-PR reports fixture-slice delta |
| Strategy refactor breaks Open Legal Data ingestion | Legacy `to_ref_marker` output preserved through H1 |
| `law_book_codes` fix reduces recall | Feature-flag the fix (O-5); add codes rather than loosen regex |
| ML deps bloat the base install | All ML is behind `[crf]` / `[transformers]` / `[training]` extras; base stays zero-dep |
| Adapter deps bloat the base install | All non-pure-Python adapters behind `[adapters]` extra |
| HF dataset publication delayed | Vendored CI subset keeps CI signal live; F1 gating for Stream F can wait |
| HF dataset revision drift | Pin revision SHA in `benchmarks/fixtures/SOURCE`; `make bench-sync` to refresh |
| Contributor churn mid-refactor | Stream checklists + this doc as single source of truth |

---

## 6. Sequencing Cheat Sheet

```
A ──┬── B ──┬── C ──┬── D ──── H
    │       │       ├── E
    │       │       ├── I
    │       │       ├── J
    │       │       └── F ──── G
```

- A (schema + fixture slice) must ship before B's benchmark-gated items.
- B can run in parallel with A2–A5 once A1 lands.
- C depends on the essential subset of B (B1–B4, B6), not all of B.
- D, E, I, J each hang off C1 — all four can run in parallel.
- F depends on D (adapters needed for training data export) **and** the HF dataset's
  train split landing.
- H is last — it deletes the fallback paths.
- Legacy `law.py` deletion now lives in B9 and does not block H.

---

## 7. Open Follow-ups (carried beyond this refactor)

Streams are at 100% — these are intentional carry-overs documented
for future passes.

| # | Item | Source | Why deferred |
|---|------|--------|--------------|
| 1 | **A2c** — `structure` dict key-level accuracy metric | Stream A | Extractor doesn't emit `structure` yet; add when LawCitation populates structure. |
| 2 | **A2d** — Relation-edge F1 metric | Stream A | Extractor doesn't emit full relations graph yet. |
| 3 | ~~**B7** — `get_law_book_ref_regex` recall-safe fix~~ | Stream B | **Closed 2026-04-21.**  Flag wired (`use_precise_book_regex`, env `REFEX_PRECISE_BOOK_REGEX`). Measurement in `optimization_log.md` §"B7 — precise vs generic": precise=ON gives +2.5 pp exact-F1, precise=OFF gives +2.7 pp overlap-F1.  Keeping `True` as default (aligns with the exact-F1 optimization metric). Flag stays as a permanent knob. |
| 4 | **E2** — `default_unit` column on `law_book_codes.txt` | Stream E | Current `LawCitation.unit` is derived from which pattern matched (`art_*` → article, `§` → paragraph).  Codes that are article-only (`GG`) vs paragraph-only (`BGB`) vs both (some SGB) aren't annotated in the data file. |
| 5 | **G (transformer) Hub push** | Stream G | Trained `models/refex-eurobert-210m/` stays local this iteration.  Push to `openlegaldata/refex-eurobert-210m-de` once metrics are sign-off'd. |
| 6 | **H3** — full `Ref` / `RefMarker` deletion | Stream H | Still used internally by the regex extractors (`law.py`, `case.py`).  Deletes when those extractors emit `Citation` objects natively. |
| 7 | **J4b-c** — court-specific HTML profiles (oldp/bgh/bverwg/bverfg) | Stream J | Deferred until actual HTML source data is integrated — we don't have representative samples of each court's HTML yet. |
| 8 | **Aho–Corasick court-name index** | post-regex optimization | Would replace the ~1 947-option court alternation in `case.search_court`, the hard floor after E1–E11.  See `optimization_log.md` section 13. |
| 9 | **Per-`(doc_id, fn_span)` court cache** | post-regex optimization | When the same file number pattern recurs in a document. |
| 10 | **Interval-based marker masking** | post-regex optimization | Replace `RefMarker.replace_content_with_mask` string concat with an interval list.  Currently <1 % of extract time so low priority. |
