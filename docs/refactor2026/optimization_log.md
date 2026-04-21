# Regex Extractor Optimization Log

**Target:** make `RegexLawExtractor` + `RegexCaseExtractor` faster
without regressing F1.
**Benchmark:** `make bench-dev` → `python -m benchmarks.run
-s validation -e regex --json` on the 821-doc validation split.
**Accuracy gate:** `|Δ F1_exact| < 5e-4` and `|Δ F1_overlap| < 5e-4`
vs. baseline.  If violated, revert.
**Stop rule:** two consecutive experiments delivering <1% throughput
improvement → stop and document the plateau.

## Results

| # | Change | Tests | F1 exact | F1 overlap | docs/s | median ms | p95 ms | commit |
|---|--------|:-----:|---------:|-----------:|-------:|----------:|-------:|--------|
| baseline | regex extractor as of 2026-04-20 | ✅ | 0.7338 | 0.8151 | 389.7 | 1.3 | 8.3 | before `7d22180` |
| E0 | Add `--profile` / `--profile-output` to `benchmarks/run.py` (no hot-path change) | ✅ | 0.7338 | 0.8151 | 389.7 | 1.3 | 8.3 | `0fe847c` |
| **E1** | Pre-compile `full_name`, `art_multi`, `art_single` patterns in `law_dnc._precompile_patterns`; plain-text callsites read from the cache, HTML path still builds inline | ✅ | **0.7338** | **0.8151** | **462.3** | 1.1 | 7.1 | `4642ac5` |
| E2 | Cache reporter-pattern in `case._get_compiled_reporter_re` (code-consistency only; no measurable speed gain — Python's `re._compile` LRU already handled it) | ✅ | 0.7338 | 0.8151 | 460.6 | 1.2 | 7.1 | `76a1f3f` |
| E3 | Pre-compile `_book_pattern_re` in `__init__`; add `multi_ref_sections` to the precompiled dict; multi-ref inner loop no longer recompiles the book alternation or the section splitter per marker | ✅ | 0.7338 | 0.8151 | 466.0 | 1.1 | 7.2 | _this commit_ |

## E1 — pre-compile remaining law patterns

`src/refex/extractors/law_dnc.py` — moved three per-extract
`re.compile(...)` calls into `_precompile_patterns()`, which runs
exactly once per extractor instance on first use.  Guarded the
plain-text callsites with `if not is_html:` so the HTML path keeps
building inline patterns (it needs `section_sign = "&#167;"` and
HTML-aware `word_delimiter`).

**Δ throughput: +18.6 % (389.7 → 462.3 docs/s)**,
Δ median: 1.3 → 1.1 ms, Δ p95: 8.3 → 7.1 ms,
F1 unchanged to 4 decimal places.

## E2 — pre-compile reporter pattern

`src/refex/extractors/case.py` — mirrored the existing
`_get_compiled_court_re` / `_get_compiled_file_number_re` /
`_get_compiled_sg_re` lazy-init pattern to add
`_get_compiled_reporter_re()`.  Replaced the per-extract
`re.compile(...)` of the 33-term reporter alternation.

| | F1 exact | F1 overlap | docs/s | median ms | p95 ms |
|-|---------:|-----------:|-------:|----------:|-------:|
| E1 | 0.7338 | 0.8151 | 462.3 | 1.1 | 7.1 |
| **E2** | 0.7338 | 0.8151 | **460.6** | 1.2 | 7.1 |

**Δ throughput: −0.4 % (within noise).**  The reporter pattern is
small enough that Python's internal `re._compile` LRU (size 512)
was already handling it cheaply.  Kept the change for code
consistency (all extractor-level patterns now lazy-init through
`_get_compiled_*`) but this doesn't count toward the speedup
budget.

## E3 — cache per-marker patterns in the multi-ref loop

`src/refex/extractors/law_dnc.py` — two changes:

- Added `self._book_pattern_re = re.compile(self._book_ref_regex)` to
  `__init__` and to the `law_book_codes` setter so the 1,947-term
  alternation is compiled once per extractor instance.  Replaced the
  inline `re.finditer(book_pattern, marker_text)` at the former
  line 207 with `self._book_pattern_re.finditer(marker_text)`.
- Added `multi_ref_sections` to `_precompile_patterns()` — the
  section-splitter regex (`(§§|,|;|und|bis) + section number`) that
  was being recompiled on every multi-ref match.  Plain-text path
  reads from the cache; HTML path still builds inline.

| | F1 exact | F1 overlap | docs/s | median ms | p95 ms |
|-|---------:|-----------:|-------:|----------:|-------:|
| E2 | 0.7338 | 0.8151 | 460.6 | 1.2 | 7.1 |
| **E3** | 0.7338 | 0.8151 | **466.0** | 1.1 | 7.2 |

**Δ throughput: +1.2 %.**  Modest — confirms `search_court` is
the bigger target left (E4).

## E0 — profile-first diagnostic

Profile captured on 100 validation docs (`--profile -n 100`) and
saved to `logs/profile-regex-baseline.txt`.

Top offenders by cumulative time:

| Function | cumtime | tottime | ncalls |
|----------|--------:|--------:|-------:|
| `law_dnc.extract_law_ref_markers` | 0.232 s | 0.037 s | 100 |
| `case.extract_case_ref_markers` | 0.224 s | 0.040 s | 100 |
| `re._compile` | 0.235 s | 0.003 s | 959 |
| `re.compile` | 0.209 s | 0.000 s | 789 |
| **`case.search_court`** | **0.177 s** | **0.132 s** | **445** |
| `law_dnc._precompile_patterns` (one-shot init) | 0.106 s | — | 1 |
| `case._get_compiled_court_re` | 0.044 s | 0.000 s | 1007 |

Key signals:

1. **`search_court` is the single biggest runtime hotspot** (132 ms
   tottime out of ~500 ms total), confirming the audit's bet on E4.
2. Regex **compilation** consumes ~225 ms cumulative — 106 ms of
   that is the one-shot `_precompile_patterns` init, the rest is
   per-extract recompilation of the three law patterns + the
   reporter pattern.  E1 + E2 should claw that back.
3. The court-regex getter is called **1,007×** for 100 docs — roughly
   twice per file-number hit — which matches the three-window
   nested-search code path.

Priority order stays: **E1 → E2 → E3 → E4 → E5** with the big bet on
E4 (court search rewrite).

Ordered-by-tottime slice (top 10) also saved in
`logs/profile-regex-baseline.txt`.
