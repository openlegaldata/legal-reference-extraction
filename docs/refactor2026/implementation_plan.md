# Refactor 2026 — Implementation Plan

**Status:** Draft — not yet approved for execution
**Last updated:** 2026-04-18
**Owners:** tbd
**Builds on:**
[`architecture_review.md`](./architecture_review.md) ·
[`ecosystem_comparison.md`](./ecosystem_comparison.md) ·
[`output_format_recommendation.md`](./output_format_recommendation.md)

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

- [ ] A1. Add a `benchmarks/` package with `datasets.py` loaders for:
  - [ ] A1a. Darji 2023 `PaDaS-Lab/legal-reference-annotations` (HF datasets) → law refs
  - [ ] A1b. Leitner 2020 `elenanereiss/Legal-Entity-Recognition` → case-ref detection
- [ ] A2. Add metric reporter: per-document precision / recall / F1 on span exact-match +
  partial-match + field-match for law refs (`book`, `section/number`, `absatz`, `satz`).
- [ ] A3. Wire `make bench` target (dev-dep only; not in runtime extras).
- [ ] A4. CI job `bench.yml` that runs on every PR and posts the scores as a comment.
  Floor: none on first run. First run *is* the baseline.
- [ ] A5. Document: `benchmarks/README.md` with how to reproduce.

**Exit:** `make bench` prints P/R/F1 against both datasets. CI posts the numbers.
**Open questions:** O-1, O-2, O-3.

### Stream B — Phase 1: Cleanup (gated on A1 + A4)

Every change in this stream must be measured against Stream A. Any regression > 0.5 F1
needs justification in the PR description.

- [ ] B1. Fix `RefMarker.references` mutable default (move to `__init__`). `models.py:121`.
- [ ] B2. Drop `**kwargs` in `BaseRef.__init__`; make fields explicit. `models.py:21-22`.
- [ ] B3. Fix `Ref.__eq__` → return `NotImplemented` for foreign types. `models.py:89-91`.
- [ ] B4. Fix `Ref.__hash__` — hash the full field tuple, not `__repr__`. `models.py:24-25`.
- [ ] B5. Pre-compile regex patterns at `__init__`; remove per-call `re.compile()`.
  `law_dnc.py:114,142,222,276` and any matching `re.compile` in `case.py`.
- [ ] B6. Fix `law_book_codes` mutable class attr (move to instance state).
  `law_dnc.py:32, 298-307`.
- [ ] B7. **Fix `get_law_book_ref_regex`** to actually use `law_book_codes`.
  `law_dnc.py:309-346` — this is likely the single highest-impact precision win.
- [ ] B8. Remove `case.codes = ["Sa"]` and commented-out references. `case.py:13-15, 266`.
- [ ] B9. Decide fate of `law.py` (see O-4) and `test_law_legacy.py`.

**Exit:** All tests green, F1 ≥ baseline from Stream A. PR descriptions cite metric deltas.

### Stream C — Phase 2a: Typed model + strategy pattern (gated on B1–B4, B6)

Follows [`output_format_recommendation.md`](./output_format_recommendation.md) §4.1.

- [ ] C1. Add new models in `src/refex/models.py` **alongside** existing `Ref` / `RefMarker`:
  - [ ] C1a. `Span(start, end, text)` — frozen, slots
  - [ ] C1b. `Citation` base — frozen, slots, with `id, span, kind, confidence, source`
  - [ ] C1c. `LawCitation(unit, delimiter, book, number, structure, range_end, range_extensions)`
  - [ ] C1d. `CaseCitation(court, file_number, file_number_parts, date, decision_type, ecli, reporter, reporter_volume, reporter_page, reporter_marginal, parallel_citations)`
  - [ ] C1e. `CitationRelation(source_id, target_id, relation, span)`
  - [ ] C1f. Stable content-hash IDs (replace `uuid.uuid4()`).
- [ ] C2. Define `Extractor` protocol in `src/refex/protocols.py`:
  `def extract(self, text: str) -> tuple[list[Citation], list[CitationRelation]]:`
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
- [ ] D3. `to_spacy_doc()` adapter (optional extra: `pip install legal-reference-extraction[spacy]`).
- [ ] D4. `to_hf_bio()` adapter — labels `LAW_REF`, `CASE_REF`, `FILE_NUMBER`, `COURT`,
  `ECLI`, `REPORTER`, `RELATION_IVM`.
- [ ] D5. `to_gliner()` adapter.
- [ ] D6. `to_web_annotation()` adapter.
- [ ] D7. `to_akn_ref()` adapter (Akoma Ntoso / LegalDocML.de).
- [ ] D8. Pin down the exact `structure` dict key set as constants in `models.py`;
  document against Darji 2023's 21 properties.

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

- [ ] F1. Add `sklearn-crfsuite` as an optional dep: `[crf]` extra.
- [ ] F2. `CRFLawExtractor` trained on Darji 2023 split.
- [ ] F3. `CRFCaseExtractor` trained on Leitner 2020 split (detection only; case parsing
  still falls through to the regex parser).
- [ ] F4. Document retraining command in `benchmarks/README.md`.

**Exit:** CRF engine reports F1 ≥ regex baseline on the Darji dev set.

### Stream G — Phase 3: Transformer engine (optional, gated on F plateau)

- [ ] G1. `TransformerLawExtractor` using `PaDaS-Lab/gbert-legal-ner` as default weights.
- [ ] G2. Optional extra: `pip install legal-reference-extraction[ml]`.
- [ ] G3. GPU-batch inference path for Open Legal Data's batch ingestion.

**Exit:** Orchestrator can choose engine per-document; regex stays default.

### Stream H — Phase 2d: Migration & deletion (final)

- [ ] H1. Migrate Open Legal Data's ingestion pipeline to consume JSONL output.
- [ ] H2. Drop `RefMarker.replace_content`, `MARKER_OPEN`/`MARKER_CLOSE` constants.
- [ ] H3. Drop `Ref` union class and the `RefType` enum.
- [ ] H4. Delete `law.py` legacy extractor and `tests/test_law_legacy.py`
  (or port the regression cases into `tests/test_law_extractor.py`).
- [ ] H5. Bump minor version; update `CHANGELOG.md` and `README.md` examples.

**Exit:** Zero references to the old model types in `src/` and `tests/`.

---

## 3. Progress Tracking — Summary Matrix

| Stream | Purpose | Depends on | Status | % Done |
|--------|---------|------------|--------|--------|
| A | Benchmark harness | — | not started | 0 |
| B | Cleanup | A1, A4 | not started | 0 |
| C | Typed model + strategy | B1–B4, B6 | not started | 0 |
| D | Output format & adapters | C1–C4 | not started | 0 |
| E | Grundgesetz / Artikel | C1 | not started | 0 |
| F | CRF engine | D, A | not started | 0 |
| G | Transformer engine | F plateau | not started | 0 |
| H | Migration & deletion | D, H1 (OLD consumer) | not started | 0 |

Update the matrix at the top of every PR that lands a stream item. Track in a
`CHANGELOG.md` entry per stream.

---

## 4. Open Questions

Each question must have an owner and an answer before the gated stream can start.

- **O-1.** Benchmark licensing — can we vendor a cached copy of the Darji HF dataset
  inside `benchmarks/fixtures/`, or must we always fetch at runtime? Affects air-gapped CI.
  *Blocks A1a.*
- **O-2.** Partial-match metric: is token-level F1 or character-span IoU the right
  primary metric for law-ref detection? Darji's paper reports property-level F1; we
  should match unless there's reason not to. *Blocks A2.*
- **O-3.** Which of the 21 Darji properties are in-scope for the core schema vs.
  structure-dict? Current proposal: book + number + unit are first-class; the rest go in
  `structure`. Need sign-off before C1c. *Blocks C1c.*
- **O-4.** Fate of `src/refex/extractors/law.py`: delete now (H4), or port first and then
  delete? Risk: `test_law_legacy.py` encodes behaviour that may or may not have been
  intentionally preserved. Audit before deletion. *Blocks B9 and H4.*
- **O-5.** `get_law_book_ref_regex` fix (B7) may reduce recall by rejecting valid-but-
  unlisted book codes currently matched by the permissive regex. Quantify before landing.
  *Blocks B7 merge.*
- **O-6.** Should citation IDs be content-hashes (reproducible, small) or
  `ulid`-style sortable IDs (stable ordering across documents)? Proposal: content hash
  of `(kind, span, source, doc_id)`. *Blocks C1f.*
- **O-7.** Adapter extras strategy — one extra per adapter (`[spacy]`, `[hf]`, `[ml]`)
  or one `[adapters]` meta-extra? The more granular path keeps installs small but
  increases maintenance. *Blocks D3 packaging decision.*
- **O-8.** Short-form / `a.a.O.` / `ebenda` / `vgl.` extractors — in scope for this
  refactor or deferred to a later phase? Recommended: reserve the `kind` field now,
  implement later. *Affects C1b field set.*
- **O-9.** Should `RegexCaseExtractor.get_codes()` (currently CSV-loading, only called
  from tests) be promoted to runtime use, or is its runtime replacement the regex in
  `get_file_number_regex()` good enough? Audit needed. *Affects B8 scope.*
- **O-10.** Open Legal Data ingestion owner — who runs the migration in H1? Timing
  coordinates with the deletion work in H2–H4.
- **O-11.** CI benchmark cost — running Darji + Leitner on every PR may be slow. Do we
  sample, cache by content hash, or run only on scheduled jobs? *Affects A4.*

---

## 5. Risks & Rollback

| Risk | Mitigation |
|------|------------|
| Cleanup silently regresses extraction | Stream A blocks Stream B; every B-PR reports P/R/F1 delta |
| Strategy refactor breaks Open Legal Data ingestion | Legacy `to_ref_marker` output preserved through H1 |
| `law_book_codes` fix reduces recall | Measure against benchmark first (O-5); add codes rather than loosen regex |
| ML deps bloat the base install | All ML is behind extras (`[crf]`, `[ml]`); zero-dep base install preserved |
| Darji / Leitner datasets change upstream | Pin dataset revisions in `benchmarks/datasets.py` |
| Contributor churn mid-refactor | Stream checklists + this doc as the single source of truth |

---

## 6. Sequencing Cheat Sheet

```
A ──┬── B ──┬── C ──┬── D ──┬── H
    │       │       │       │
    └───────┴───────┼── E   │
                    │       │
                    └── F ──┴── G
```

- A must ship before anything else is measured.
- B can run in parallel with A2–A5 once A1 lands.
- C depends on the essential subset of B (B1–B4, B6), not all of B.
- D, E, F each hang off different parts of C; can run in parallel.
- H is last — it deletes the fallback paths.
