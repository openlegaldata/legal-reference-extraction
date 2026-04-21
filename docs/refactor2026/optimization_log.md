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
| E0 | Add `--profile` / `--profile-output` to `benchmarks/run.py` (no hot-path change) | ✅ | 0.7338 | 0.8151 | 389.7 | 1.3 | 8.3 | _this commit_ |

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
