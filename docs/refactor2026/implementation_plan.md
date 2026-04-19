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
  - [ ] A1a. Land [`benchmark_dataset_spec.md`](./benchmark_dataset_spec.md) (done on
    this PR).
  - [ ] A1b. Commit JSON Schemas for `documents.jsonl` and `annotations.jsonl` under
    `benchmarks/schemas/` — single source of truth for validators on both sides.
  - [ ] A1c. Vendor CI subset (~10–20 docs, stratified per spec §6) into
    `benchmarks/fixtures/documents.jsonl` + `benchmarks/fixtures/annotations.jsonl`.
    Pin the HF revision SHA in `benchmarks/fixtures/SOURCE`.
  - [ ] A1d. `benchmarks/datasets.py` loader: `BenchmarkDataset` class that can read
    either the vendored fixture set or the full HF dataset (via `datasets.load_dataset`
    when the `[adapters]` extra is installed).
  - [ ] A1e. `benchmarks/validate.py` — runs the spec §9 quality checks against a
    fixture/dataset path.
- [ ] A2. Metric reporter (`benchmarks/metrics.py`) — custom, project-defined (O-2
  resolved):
  - [ ] A2a. Span detection: precision / recall / F1 on exact character-span match.
  - [ ] A2b. Field-level accuracy per `LawCitation` field (`book`, `number`, `unit`)
    and per `CaseCitation` field (`court`, `file_number`, `ecli`, `date`).
  - [ ] A2c. `structure` dict key-level accuracy (absatz, satz, nummer, halbsatz, …).
  - [ ] A2d. Relation-edge F1 for `CitationRelation`s (i.V.m., a.a.O., …).
  - [ ] A2e. Document-level summary + per-field breakdown. JSON output for CI ingestion.
- [ ] A3. Wire `make bench` target (dev-dep only; not in runtime extras):
  - Default runs against the vendored CI subset.
  - `make bench DATASET=hf` pulls the full dataset from Hugging Face.
  - `make bench-sync` re-downloads the CI subset from HF and rewrites
    `benchmarks/fixtures/` + `SOURCE`.
- [ ] A4. CI job `bench.yml`:
  - [ ] A4a. On every PR: run the vendored CI subset; post delta-to-baseline as a PR
    comment.
  - [ ] A4b. Scheduled (nightly or weekly): run against the full HF dataset; post to a
    tracking issue.
- [ ] A5. Document: `benchmarks/README.md` — how to run the benchmark, how to refresh
  the CI subset, where the full dataset lives, how to contribute annotations upstream.

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

- [ ] C1. Add new models in `src/refex/models.py` **alongside** existing `Ref` / `RefMarker`:
  - [ ] C1a. `Span(start, end, text)` — frozen, slots. Offsets always into `Document.text`, never `raw`.
  - [ ] C1b. `Citation` base — frozen, slots, with `id, span, kind, confidence, source`
  - [ ] C1c. `LawCitation(unit, delimiter, book, number, structure, range_end, range_extensions)`
  - [ ] C1d. `CaseCitation(court, file_number, file_number_parts, date, decision_type, ecli, reporter, reporter_volume, reporter_page, reporter_marginal, parallel_citations)`
  - [ ] C1e. `CitationRelation(source_id, target_id, relation, span)`
  - [ ] C1f. Stable content-hash IDs (replace `uuid.uuid4()`).
  - [ ] C1g. `Document(raw, format, source_profile, text, offset_map)` — input wrapper
    consumed by extractors; see Stream J for how it's built.
- [ ] C2. Define `Extractor` protocol in `src/refex/protocols.py`:
  `def extract(self, doc: Document) -> tuple[list[Citation], list[CitationRelation]]:`
- [ ] C3. Wrap existing regex logic as `RegexLawExtractor` and `RegexCaseExtractor`
  emitting the new types natively.
- [ ] C4. Rewrite `RefExtractor` as an **orchestrator** that accepts
  `extractors: list[Extractor]`, resolves overlaps by confidence, and exposes
  `extract(text) -> ExtractionResult`.
- [ ] C5. Keep the old `RefMarker` / `Ref` path wired up to the new types via an
  internal adapter — existing tests stay green without modification.
- [ ] C6. Add `ExtractionResult.to_ref_marker()` for the legacy `[ref=UUID]…[/ref]`
  string output. Mark it deprecated but keep it for Open Legal Data's pipeline.

**Exit:** Existing test suite green against the orchestrator; new `RegexLawExtractor`
has unit tests; benchmark numbers unchanged.

### Stream D — Phase 2b: Output format & adapters (gated on C1–C4)

- [ ] D1. `to_jsonl()` — primary format per [`output_format_recommendation.md`](./output_format_recommendation.md) §4.2.
- [ ] D2. Golden-file snapshot tests: for every existing fixture, snapshot the JSONL
  output as a regression net.
- [x] D3. `to_spacy_doc()` adapter — pure-Python dict, no spaCy dep needed.
- [x] D4. `to_hf_bio()` adapter — whitespace tokenization + BIO labels:
  `B-LAW_REF`, `I-LAW_REF`, `B-CASE_REF`, `I-CASE_REF`, `O`.
- [x] D5. `to_gliner()` adapter — span-based format (start, end, label, text).
- [x] D6. `to_web_annotation()` adapter — W3C Web Annotation Data Model with
  TextPositionSelector.
- [x] D7. `to_akn_ref()` adapter — Akoma Ntoso / LegalDocML.de XML ref elements.
- [x] D8. `STRUCTURE_KEYS` frozenset in `citations.py` — 21 valid structure dict keys
  (absatz, satz, nummer, halbsatz, buchstabe, alternative, variante, etc.).
- [x] D9. Packaging (O-7 resolved): two extras groups in `pyproject.toml`.
  - `[adapters]` — pulls `spacy` + any optional deps needed by the format adapters.
  - `[ml]` — pulls `sklearn-crfsuite`, `transformers`, `torch` for Streams F + G.
  - Base install stays zero-dep; all adapters are pure-Python dict/JSON/XML output.

**Exit:** All adapters have round-trip tests (to_X → parse → compare). JSONL output is
the documented "blessed" format.

### Stream E — Phase 2c: Grundgesetz / Artikel support (gated on C1)

Per [`output_format_recommendation.md`](./output_format_recommendation.md) §7.

- [ ] E1. Extend delimiter regex in single-ref and multi-ref handlers to include
  `Art\.?|Artikel`. Sites: `law_dnc.py:114, 142, 222, 276`.
- [ ] E2. Add `default_unit` column to `law_book_codes.txt` (or replace the file with a
  small TSV / JSON). Values: `paragraph` | `article` | `either`.
- [ ] E3. Populate `unit` and `delimiter` on emitted `LawCitation`s.
- [ ] E4. Un-skip `tests/test_law_extractor.py::test_extract10` and the other
  three currently-skipped Art. fixtures; add EU-directive form
  `Art. 3 II Buchst. c RL 2001/29/EG` from `de_notes.md`.
- [ ] E5. Benchmark delta: does Art. coverage increase the Darji F1 materially?

**Exit:** All four previously-skipped tests pass. Benchmark F1 reported before/after.

### Stream F — Phase 2.5: CRF engine (optional, gated on D + benchmark baseline)

- [ ] F1. Add `sklearn-crfsuite` under the `[ml]` extra.
- [ ] F2. `CRFLawExtractor` trained on the external benchmark's train split.
- [ ] F3. `CRFCaseExtractor` for case-ref detection; case parsing still falls through to
  the regex parser.
- [ ] F4. Document retraining command in `benchmarks/README.md`.
- [ ] F5. Decide fate of `case.get_codes()` + `file_number_codes.csv` (O-9 resolved,
  deferred to here): either use the curated codes as a CRF feature source, or delete
  the method and move the CSV under `benchmarks/` / `tools/` if CRF training doesn't
  need it.

**Exit:** CRF engine reports F1 ≥ regex baseline on the benchmark's dev split.

### Stream G — Phase 3: Transformer engine (optional, gated on F plateau)

- [ ] G1. `TransformerLawExtractor` using `PaDaS-Lab/gbert-legal-ner` as default weights.
- [ ] G2. Pulled in by the same `[ml]` extra as Stream F.
- [ ] G3. GPU-batch inference path for Open Legal Data's batch ingestion.

**Exit:** Orchestrator can choose engine per-document; regex stays default.

### Stream H — Phase 2d: Migration & deletion (final)

- [ ] H1. Migrate Open Legal Data's ingestion pipeline to consume JSONL output
  (same owner as this refactor — O-10 resolved).
- [ ] H2. Drop `RefMarker.replace_content`, `MARKER_OPEN`/`MARKER_CLOSE` constants.
- [ ] H3. Drop `Ref` union class and the `RefType` enum.
- [ ] H4. Bump minor version; update `CHANGELOG.md` and `README.md` examples.

**Exit:** Zero references to the old model types in `src/` and `tests/`.

(Legacy `law.py` deletion moved into Stream B9 — it doesn't have to wait for migration.)

### Stream I — Phase 2e: Short-form / supra / id / ibid / a.a.O. / ebenda (gated on C1)

Per O-8 resolution: "implement everything" as part of this refactor. Closes the full
generation-zero gap that `ecosystem_comparison.md` §1 calls out.

- [ ] I1. Extend the `kind` Literal on `Citation` to `"full" | "short" | "id" | "ibid" |
  "supra" | "aao" | "ebenda"` (already reserved in C1b; populate now).
- [ ] I2. German-dialect short-form heuristics:
  - [ ] I2a. `a.a.O.` / `a. a. O.` — "am angegebenen Ort" (= ibid/id). Resolves to the
    nearest prior same-kind citation.
  - [ ] I2b. `ebenda` / `ebd.` — same resolution.
  - [ ] I2c. `siehe dort` — same resolution.
  - [ ] I2d. `vgl.` connector — becomes a `CitationRelation(kind="vgl")`, not a new
    citation.
- [ ] I3. Short-form law refs: bare `§ 5` after a fully-qualified `§ 3 BGB` inherits
  book from the most recent full LawCitation in context.
- [x] I4. Short-form case refs: reporter citations (BGHZ, BVerfGE, etc.) after a
  full case citation are linked via ``kind="short"`` with court inferred from
  reporter abbreviation.
- [ ] I5. Resolver post-pass: after extraction, walk citations in document order, fill
  in `short`/`id`/`supra` references from prior context. Emitted as `CitationRelation`s
  (`relation="resolves_to"`).
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

- [ ] J1. `Document` dataclass in `src/refex/models.py`:
  - `raw: str`, `format: Literal["plain", "html", "markdown"]`,
  - `source_profile: str | None`, `text: str`,
  - `offset_map: Sequence[int]` — for each index `i` in `text`, the corresponding
    offset in `raw` (enough to round-trip spans back).
- [ ] J2. `SourceProfile` protocol in `src/refex/sources/__init__.py`:
  `def normalise(raw: str) -> tuple[str, Sequence[int]]:`. Pure-Python; no runtime
  deps for the default profiles.
- [ ] J3. Plain-text profile (`plain`): identity normaliser.
- [ ] J4. HTML normalisers:
  - [ ] J4a. `html-generic` default — strip tags, decode entities, collapse whitespace
    conservatively, preserve paragraph breaks as `\n`. Use stdlib `html.parser`; no
    `beautifulsoup4` dep in base install (belongs behind `[adapters]`).
  - [ ] J4b. `oldp-html` profile — Open Legal Data dump-specific boilerplate stripping
    (nav, breadcrumbs, metadata tables).
  - [ ] J4c. `bgh-html`, `bverwg-html`, `bverfg-html` profiles as separate modules;
    register additional profiles over time as new sources appear.
- [ ] J5. Markdown normaliser (`commonmark-markdown`): parse with a pure-Python
  CommonMark lib (optional dep under `[adapters]`) or a minimal inline handler for
  emphasis + code markers.
- [ ] J6. `RefExtractor.extract()` accepts either a `str` (auto-detects format via
  content sniffing + `format=` kwarg override) or a `Document`. The raw string path
  builds a `Document` internally.
- [ ] J7. Format detection heuristic: HTML if the input starts with `<` or contains
  `<[a-z]+[ >]` in the first 256 chars; Markdown if it has CommonMark-style
  headings / emphasis; else plain.
- [x] J8. Offset-map utilities: `map_span_to_raw(span, document) -> Span` for
  consumers that need to render markers back into the original HTML / Markdown.
  State-machine HTML walker builds char-level offset map, handles entities.
- [ ] J9. Per-profile adapters for the legacy `to_ref_marker` output: re-insert
  `[ref=UUID]...[/ref]` into `raw` at the mapped-back offsets. Preserves HTML
  validity (no tag-crossing markers) by splitting the marker at tag boundaries.
- [x] J10. Tests:
  - [x] J10a. Round-trip tests: for each profile, `normalise(raw)` reproduces
    `Document.text` byte-for-byte, and `map_span_to_raw(span)` recovers a valid
    substring of `raw`.
  - [ ] J10b. Benchmark coverage: CI subset fixture includes at least one document
    per format and two distinct HTML profiles.
  - [x] J10c. Boilerplate-contamination tests: an HTML document with script/style/head
    must not emit citations from those sections.
- [x] J11. Deprecate `is_html: bool` kwarg with a DeprecationWarning; remove in
  Stream H.

**Exit:** `extract(raw_html, format="html", source_profile="oldp-html")` returns
citations whose spans land correctly in the plain-text projection, and
`map_span_to_raw` recovers the original HTML location.

---

## 3. Progress Tracking — Summary Matrix

| Stream | Purpose | Depends on | Status | % Done |
|--------|---------|------------|--------|--------|
| A | Benchmark harness (schema + fixture slice) | — | **done** (preview) | 90 |
| B | Cleanup + legacy `law.py` deletion | A1, A4 | **done** | 100 |
| C | Typed model + strategy | B1–B4, B6 | **done** | 100 |
| D | Output format & adapters | C1–C4 | **done** | 100 |
| E | Grundgesetz / Artikel | C1 | **done** | 100 |
| F | CRF engine | D, A, HF dataset train split | not started | 0 |
| G | Transformer engine | F plateau | not started | 0 |
| H | Migration & deletion | D | **partial** (H1 done, H4 done; H2-H3 deferred) | 60 |
| I | Short-form / id / supra / a.a.O. / ebenda | C1 | **done** | 100 |
| J | Input format handling (plain / HTML / Markdown + per-source profiles) | C1 | **done** (J1-J8,J10-J11; J9 deferred) | 95 |

**Metrics (2026-04-19, benchmark_10k test split, 1009 docs):**

| Metric | Baseline | Current | Delta |
|--------|----------|---------|-------|
| Span F1 (exact) | 0.635 | **0.651** | **+0.016** |
| Span F1 (overlap) | 0.841 | **0.850** | **+0.009** |
| Law F1 (exact) | 0.757 | **0.778** | **+0.021** |
| Law F1 (overlap) | — | **0.873** | — |
| Case F1 (exact) | 0.378 | **0.379** | **+0.001** |
| Case F1 (overlap) | — | **0.793** | — |
| Book accuracy | 95.6% | **95.8%** | +0.2% |
| Court accuracy (overlap) | — | **55.8%** | — |
| Number accuracy | 94.9% | **95.1%** | +0.2% |

Note: baseline was measured on 10k test split before book code expansion and
court list improvements. The "overlap" metrics account for span boundary
differences between gold (full citation context) and predicted (file number /
section reference only). 882 law book codes were mined from the benchmark
train split and added to the code list (1105 → 1948 codes).

**Stream A notes:** Benchmark harness built in sibling project
`german-legal-references-benchmark`. Bridge code in `benchmarks/` directory
(adapter, metrics, runner). Data NOT committed — loaded from sibling project
or `BENCH_DATA_DIR` env var. `make bench` runs full benchmark.

**Stream B notes:** B1-B6, B8 landed with zero benchmark regression.
B7 (law_book_codes regex fix) deferred — needs feature flag per O-5.
B9 (legacy law.py deletion) deferred — needs audit-diff + test migration.

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
| O-7 | Optional-extras layout | Two groups: `[adapters]` (format converters) and `[ml]` (CRF + transformer engines). Base install stays zero-dep | D9, F1, G2 |
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
| ML deps bloat the base install | All ML is behind `[ml]` extra; base stays zero-dep |
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
