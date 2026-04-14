# Architecture Review: legal-reference-extraction

**Date:** 2026-04-13
**Scope:** Full project review — architecture, reusability, efficiency, future ML readiness

## Executive Summary

The project is a ~1,300 LOC regex-based extractor for German legal references. It works, has
solid test coverage (90%+), zero runtime dependencies, and solves its specific problem.
**It does not need a full rewrite**, but it does need targeted refactoring if you want to
extend it — especially toward ML/transformer-based extraction. The current architecture would
actively resist that extension.

---

## 1. What Works Well

- **Zero dependencies.** Pure Python, stdlib only. Easy to install, no version conflicts.
- **Divide-and-conquer masking.** The `law_dnc.py` approach of masking matched regions with
  underscores to prevent double-matching is pragmatic and effective.
- **Separation of law vs. case extraction.** Each is an independent mixin — toggled with booleans.
- **Good test coverage.** 42 tests, 90% threshold enforced in CI, real German legal text fixtures.
- **Clean build.** Modern `pyproject.toml`, src layout, ruff linting, matrix CI (Python 3.11-3.13).

---

## 2. Structural Problems

### 2.1 Mixin Inheritance is the Wrong Abstraction

```python
class RefExtractor(DivideAndConquerLawRefExtractorMixin, CaseRefExtractorMixin):
```

Uses multiple inheritance to compose behavior, but the "mixins" are full extractors with state
(`law_book_context`, `law_book_codes`, `court_context`, `codes`). They share no common interface.

**Problems:**
- Adding a new extractor type means modifying `RefExtractor`'s inheritance chain.
- A transformer-based law extractor can't be swapped in without replacing the mixin.
- State leaks across mixins via `self`.
- The legacy `LawRefExtractorMixin` in `law.py` duplicates `extract_law_ref_markers_with_context`
  nearly verbatim (~110 lines copy-pasted).

**Better:** A strategy/plugin pattern:

```python
class Extractor(Protocol):
    def extract(self, content: str) -> list[RefMarker]: ...

class RefExtractor:
    def __init__(self, extractors: list[Extractor]): ...
```

### 2.2 Models Have Design Issues

- **Mutable class-level defaults:** `RefMarker.references: list[Ref] = []` is shared across all
  instances if `set_references()` is never called.
- **`BaseRef.__init__` uses `**kwargs`:** Typos like `Ref(boook="bgb")` are silently accepted.
- **`Ref.__eq__` uses `assert`:** Stripped with `python -O`. Should return `NotImplemented`.
- **`Ref.__hash__` depends on `__repr__`:** Different refs can collide since repr omits fields.

### 2.3 Dead Code and Duplication

| Issue | Location |
|-------|----------|
| `law.py` (legacy extractor) | 411 lines, unused by default |
| `extract_law_ref_markers_with_context` | Nearly identical in `law.py` and `law_dnc.py` |
| `get_law_book_codes` / `get_law_book_ref_regex` | Duplicated across both law extractors |
| `CaseRefExtractorMixin.get_codes()` | Reads CSV — never called anywhere |
| `CaseRefExtractorMixin.codes = ["Sa"]` | Class attribute never used |
| Commented-out code | ~30 lines of debug prints, old regex attempts |

### 2.4 Regex Not Pre-compiled

Every `extract()` call rebuilds pattern strings and compiles regex from scratch.
`re.compile()` inside `re.finditer()` is also redundant. Patterns are static per config
and should be compiled once at init time.

### 2.5 `get_law_book_ref_regex` Ignores Its Input (law_dnc.py)

```python
def get_law_book_ref_regex(self, law_book_codes, ...):
    # Parameter law_book_codes is never used!
    return r"([A-ZÄÜÖ][-ÄÜÖäüöA-Za-z]{,20})(V|G|O|B)(?:\s([XIV]{1,5}))?"
```

The `default_law_book_codes` list is populated but never used for matching. Any string
matching the generic pattern is accepted — leading to false positives.

### 2.6 State Mutation on Class Attributes

```python
class DivideAndConquerLawRefExtractorMixin:
    law_book_codes: list[str] = []  # Class-level mutable!

    def get_law_book_codes(self):
        if len(self.law_book_codes) < 1:
            self.law_book_codes.extend(...)  # Mutates class attr!
```

First call mutates the class-level list. All future instances share the extended list.

---

## 3. Efficiency Analysis

For single-document extraction, performance is adequate. Clear inefficiencies:

| Issue | Impact |
|-------|--------|
| Regex recompilation every `extract()` call | Wasted compile cost |
| `get_court_name_regex()` rebuilds ~300-option alternation per call | Cartesian product recomputed |
| Masking via string slicing | O(n*m) for n markers in m-length content |
| 4 sequential single-ref patterns | Could be merged or applied in one pass |
| `search_court()` 3 expanding window scans | Up to 3 overlapping regex scans |

None are showstoppers for single documents. Would matter for batch processing.

---

## 4. Future-Proofing for Neural/Transformer Models

### What a transformer model gives you
- End-to-end extraction: raw text in, structured references out.
- No handcrafted regex — learns from annotated data.
- Handles ambiguity, abbreviation variants, novel citation formats.
- Can jointly extract entity type + span + relations.

### What the current architecture assumes
- Extraction == regex matching.
- Output positions map 1:1 to character offsets.
- Masking (replacing text with `_`) coordinates between passes.
- `RefMarker` bakes in string-manipulation methods.

### What would need to change

1. **Separate "extraction" from "marking."** Currently, the extractor both finds references and
   inserts tags. A transformer returns spans and labels — tag insertion should be downstream.

2. **Define an extractor interface:**
   ```python
   @dataclass
   class ExtractedRef:
       start: int
       end: int
       text: str
       ref_type: RefType
       attributes: dict[str, str]

   class Extractor(Protocol):
       def extract(self, text: str) -> list[ExtractedRef]: ...
   ```

3. **Handle overlapping results.** When running both regex and transformer, results may overlap.
   Need confidence-based resolution, not exceptions.

---

## 5. Recommendation: Refactor, Don't Rewrite

The regex logic is battle-tested against real German legal text. That domain knowledge is hard
to re-derive.

### Phase 1 — Clean up (low risk, high value)
1. Delete `law.py` (legacy extractor). Unused, maintenance trap.
2. Fix mutable class defaults on `RefMarker` and mixin classes. Move to `__init__`.
3. Remove dead code: `get_codes()`, `codes = ["Sa"]`, commented-out lines.
4. Fix `Ref.__eq__` to return `NotImplemented` instead of asserting.
5. Pre-compile regex patterns at init time.

### Phase 2 — Introduce extractor interface (medium risk, enables ML)
1. Define an `Extractor` protocol with `extract(text) -> list[ExtractedRef]`.
2. Wrap existing regex logic in `RegexLawExtractor` and `RegexCaseExtractor`.
3. Make `RefExtractor` an orchestrator accepting a list of extractors.
4. Move tag insertion into a separate `Marker` utility, out of `RefMarker`.

### Phase 3 — Add transformer support (when needed)
1. Create `TransformerLawExtractor` implementing the same protocol.
2. Optional install: `pip install legal-reference-extraction[ml]`.
3. Confidence-based overlap resolution in orchestrator.
4. Existing test fixtures become the regression suite.

---

## 6. Trade-offs Summary

| Decision | Current | Alternative | Recommendation |
|----------|---------|-------------|----------------|
| Engine | Regex only | Regex + ML hybrid | Keep regex default, add ML optional |
| Composition | Multiple inheritance | Strategy/plugin | **Refactor to strategy** |
| Dependencies | Zero | torch optional | Keep zero for base, extras for ML |
| Book code matching | Generic regex | Explicit code list | **Use the code list** — fewer false positives |
| Regex compilation | Per-call | Pre-compiled at init | **Pre-compile** |
| Legacy extractor | Kept unused | Delete | **Delete** |
| Overlap handling | Exception | Confidence resolution | **Add resolution** when ML introduced |

The regex approach remains valuable even with transformers — it's deterministic, explainable,
fast, and zero-dependency. The right architecture treats it as one strategy among several.

---

## 7. Production Context (Addendum)

This library is **first-party code for the Open Legal Data production pipeline** — not a
third-party library serving external consumers. Confirmed constraints:

- **Usage:** Batch processing of court decisions during ingestion. No real-time latency
  requirements.
- **Output format:** `[ref=UUID]...[/ref]` markers are **not load-bearing** — format can be
  changed. No external consumer lock-in.
- **Quality baseline:** **Unknown.** No precision/recall numbers exist for the current
  extractor.
- **Research collaboration:** No existing engagement with PaDaS-Lab / Darji research group,
  despite their work being built on Open Legal Data corpus.

These facts reorder the recommendations significantly.

### 7.1 Phase 0 (Prerequisite): Establish a Benchmark

**This is the highest-priority item.** Without quality numbers:

- Phase 1 cleanup could silently regress extraction quality — no way to tell.
- Phase 2/2.5/3 ML investment can't be justified without a baseline to improve on.
- Architectural bugs (unused `law_book_codes` list, overly-permissive
  `[A-Z]...V|G|O|B` book pattern) may already be causing significant false positives in the
  published 444k citation dataset — but you wouldn't know.

Recommended:

1. Import Darji 2023 law-reference annotations as the **law extractor benchmark**.
   Special value: Darji's annotations were made on Open Legal Data's own corpus, so it's a
   closed-loop benchmark on home-field data.
2. Import Leitner 2020 NER dataset as the **case extractor detection benchmark**.
   (Parsing Aktenzeichen into fields isn't covered; benchmarks span detection only.)
3. Wire both into CI as precision / recall / F1 reports. No floor required on first run —
   whatever comes out is the new ground truth.
4. The existing test suite is a **regression suite**, not a benchmark — keep it, but add
   metrics reporting.

This turns the rest of the plan from guessing into measurement.

### 7.2 Refined Phase 1: Audit Before Cleanup

Before deleting `law.py`, before fixing regex compilation, before any refactoring:

1. Run the Phase 0 benchmark on the current extractor.
2. Specifically measure: does the generic `[A-Z]...V|G|O|B` book pattern produce false
   positives the curated `law_book_codes` list would have caught? (Strong hypothesis: yes.)
3. Measure the `i.V.m.` waiting-marker cross-reference mechanism's accuracy.
4. Measure the court-search distance heuristic's court-attribution accuracy.

Then clean up. Anything that changes behavior should be justified by benchmark delta.

### 7.3 Phase 2: Output Format Migration

Format flexibility confirmed — so:

- Emit structured output (dataclass / JSON) as **primary** format.
- Align schema with Darji's 21 properties (Buch, Teil, Titel, Untertitel, section text, etc.)
  for direct benchmark compatibility.
- Provide `[ref=UUID]` rendering as a downgrade/legacy helper for any remaining consumers,
  drop when safe.

### 7.4 Batch Processing Shifts Performance Priorities

Since throughput matters, latency doesn't:

- **Pre-compiling regex at init time** is still the highest-value perf fix (amortized over
  every document in a batch run).
- **String-slicing masking** (O(n×m) per document) is acceptable — each document is a
  single-threaded unit, and individual documents aren't pathologically long.
- **GPU batch inference for ML engines** is very viable. No latency budget to worry about.
  Phase 3 (transformers) can run as a batch post-process over ingestion, not inline.
- **Multiprocessing** for document-parallel extraction is straightforward to add at the
  orchestration layer — no changes needed inside the extractor.

### 7.5 Actionable Items Specific to Open Legal Data Context

1. **Reach out to PaDaS-Lab (Passau).** Harshil Darji / Michael Granitzer's research line is
   built on your data. Collaboration could produce: validated annotations without annotation
   cost, a published German legal NER baseline, and joint research output. Low-cost,
   high-upside.
2. **Audit the 444k citation dataset** for false positives from the generic book pattern
   before publishing new releases. This is likely the most immediate quality win.
3. **Consider a shared `de-legal-codes` data package** across the openlegaldata org only if
   other repos (oldp-backend etc.) duplicate the book/court code lists. If not, the cost of
   splitting the package outweighs the benefit — keep the data bundled.
4. **Track Darji's BERT model** (`PaDaS-Lab/gbert-legal-ner` on HuggingFace) as the
   off-the-shelf transformer baseline for Phase 3. No need to train from scratch.

### 7.6 Revised Phase Order (Production Context)

Ordered by ROI given the above:

| Phase | Content | Gated by |
|-------|---------|----------|
| **0** | Establish benchmark (Darji + Leitner) in CI | — |
| **1a** | Audit current extractor against benchmark | Phase 0 |
| **1b** | Cleanup (delete legacy, fix mutable state, pre-compile regex), measured against benchmark | Phase 1a |
| **1c** | Fix the generic book pattern → use curated code list | Phase 1a (false positive rate) |
| **2** | Strategy pattern + structured output (Darji schema) | Phase 1 stable |
| **2.5** | CRF extractor trained on Darji + Leitner | Phase 2 |
| **3** | Transformer extractor (start from `PaDaS-Lab/gbert-legal-ner`) | Optional, gated on 2.5 plateau |

The critical insight: **Phase 0 is blocking for everything else.** Without it, every
subsequent decision is uninformed.
