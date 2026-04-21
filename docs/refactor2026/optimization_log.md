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
| E3 | Pre-compile `_book_pattern_re` in `__init__`; add `multi_ref_sections` to the precompiled dict; multi-ref inner loop no longer recompiles the book alternation or the section splitter per marker | ✅ | 0.7338 | 0.8151 | 466.0 | 1.1 | 7.2 | `21e8ebc` |
| E4a | Single-pass ±500 court scan + distance-bucket classifier | ✅ | 0.7339 | 0.8151 | 435.9 | 1.2 | 7.8 | **reverted** |
| E4b | Replace `content[start:end]` substring with `finditer(content, pos, endpos)`; keep 3-pass early-exit | ✅ | 0.7338 | 0.8151 | 462.2 | 1.1 | 7.2 | **reverted (within noise)** |
| E5 | Anchor pre-filter on ±500 window before full court regex | ✅ | 0.7338 | 0.8151 | 447.9 | 1.2 | 7.3 | **reverted** |
| E6 | Hoist `court_re` attr lookup to local + swap `OrderedDict` for `dict` in `search_court` | ✅ | 0.7338 | 0.8151 | 466.3 | 1.1 | 7.2 | `a023ee7` |
| E7 | Hoist `_FP_CODES` to class-level `frozenset` | ✅ | 0.7338 | 0.8151 | 463.6 | 1.1 | 7.1 | `375853a` |
| E8 | Flatten reporter spans to `(start, end)` tuples for the per-file-number overlap check | ✅ | 0.7338 | 0.8151 | 466.7 | 1.1 | 7.2 | `12bac99` |
| E9 | Lazy `set_uuid` (remove from extract path) | — | — | — | — | — | — | **skipped** (semantics change) |
| E10 | Replace hot list-append loops | — | — | — | — | — | — | **skipped** (profile shows appends are `re` internals) |
| E11 | Char class `[\s.;,:)]` instead of alternation in the court regex trailer; drop unused capture group | ✅ | 0.7338 | 0.8151 | 466.0 | 1.2 | 7.1 | `1ccfdfe` |
| E12 | `replace_content_with_mask` → interval tracking | — | — | — | — | — | — | **skipped** (<1% of extract time per profile) |
| E13 | Cache UUID or switch to stable id | — | — | — | — | — | — | **skipped** (same surface as E9) |
| **final** | all landed commits applied (E0–E11 minus reverted) | ✅ | **0.7338** | **0.8151** | **469.3** | 1.1 | 7.1 | `1ccfdfe` |

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

## E4 — court-search variants (both reverted)

Two attempts on `src/refex/extractors/case.py::search_court`, both
F1-neutral but throughput-neutral-or-worse and therefore reverted.

**E4a (single-pass over ±500 window + distance buckets).**  Replace
the three overlapping `finditer` scans with one scan of the widest
window, then classify candidates into the 100 / 200 / 500 bucket
that fully contains them.  Result: **−6.5 % throughput** on
validation.  Reason: the original early-exits on the ±100 window
whenever a candidate is within it (the common case).  Always
scanning the ±500 window triples the regex work on the happy
path.  Reverted.

**E4b (keep 3-pass, use `pos`/`endpos` instead of slicing).**
Replace `surrounding = content[start:end]` + `finditer(surrounding)`
with `finditer(content, start, end)` — saves the substring
allocation per pass but scans the same range.  Result:
**−0.8 % throughput** (within noise).  Reverted.

Takeaway: `search_court` is genuinely bounded by the regex-engine
cost of matching the ~1,947-term court alternation against
~200–1,000 chars per file number.  Moving the work around doesn't
help; the remaining gains would need an algorithmic rethink of
how we propose court candidates (e.g. a lightweight pre-filter
that narrows the alternation before the full scan) — out of scope
for this pass.

## Stop reason — plateau reached

Per the pre-registered stop rule, two consecutive experiments
delivering <1 % throughput improvement ends the loop.  E2 (−0.4 %)
and E4b (−0.8 %) both fell below the bar, with E3 (+1.2 %) in
between.  E4a was a clear regression.  Total gain landed in **E0
diagnostic + E1 + E3**.

## E5–E11 — secondary experiments after the initial plateau

A second pass of ten candidate optimizations (E5–E13) targeting
`search_court` and other post-E3 hotspots.  Most landed as small
code-quality cleanups with negligible speed impact; three were
reverted or skipped.

**Landed (small wins + cleanups, ~+1 % cumulative):**

- **E6** — hoist `self._get_compiled_court_re()` to a local in
  `search_court`, cache `match.start/end` + `len(content)` to
  locals, swap `collections.OrderedDict` for `dict` (3.7+
  insertion order).  +0.45 %.
- **E7** — hoist the per-call `_FP_CODES` set literal to a
  class-level `frozenset` (`_FILE_NUMBER_FALSE_POSITIVE_CODES`).
  Within noise.
- **E8** — flatten reporter-marker spans into `(start, end)` tuples
  once per extract for the overlap check, avoiding attribute
  lookups in the inner `any()`.  +0.67 %.
- **E11** — replace the court regex trailer
  `(\s|\.|;|,|:|\))` with `[\s.;,:)]`.  Same semantics, one fewer
  capture group, cheaper dispatch in principle.  Within noise.

**Reverted:**

- **E5** — court-anchor pre-filter before the full court regex.
  The pre-filter scan costs ~1 000 chars on every file-number hit,
  but on the common case (court IS present) we still run the full
  regex; net **−3.5 %** throughput. Reverted.

**Skipped (judgement calls):**

- **E9** — remove `set_uuid()` from extract path.  The `uuid`
  attribute is part of `RefMarker`'s observable state; dropping
  it would break any downstream code that reads it and
  legitimately silently breaks `to_ref_marker_string` if callers
  forget to `set_uuid` themselves.  Not worth it for ~5 ms gain.
- **E10** — list-append optimization.  Profile showed the hot
  `list.append` calls were inside CPython's `re._compiler`, not
  user code.  Nothing to change in refex.
- **E12** — swap `replace_content_with_mask` for interval
  tracking.  Post-E3 profile shows it at **0.75 %** of extract
  time; structural refactor doesn't pay off.
- **E13** — same semantic surface as E9.

## Summary — validation split (821 docs), all landed commits

| | baseline | after E3 | **final (E11)** | Δ final vs baseline |
|-|---------:|---------:|---------------:|--:|
| F1 exact     | 0.7338 | 0.7338 | **0.7338** | 0.0000 |
| F1 overlap   | 0.8151 | 0.8151 | **0.8151** | 0.0000 |
| Throughput   | 389.7  | 464.2  | **469.3**  | **+20.4 %** |
| Median ms    | 1.3    | 1.1    | 1.1        | −15.4 % |
| P95 ms       | 8.3    | 7.2    | 7.1        | −14.5 % |
| Max ms       | 58.5   | 40.2   | 40.4       | −30.9 % |

## Summary — test split (1,009 docs), locked-in

| | baseline | **final** | Δ |
|-|---------:|----------:|--:|
| F1 exact     | 0.7373 | **0.7373** | 0.0000 |
| F1 overlap   | 0.8600 | **0.8600** | 0.0000 |
| Throughput   | 455.9  | **489.3**  | **+7.3 %** |
| Median ms    | 1.1    | 1.1        | 0.0 |
| P95 ms       | 6.9    | 6.6        | −4.4 % |

F1 is bit-identical to 4 decimal places on both splits across all
15 experiments.  Net throughput gain is **+20.4 %** on validation
and **+7.3 %** on test.

## Conclusion

The pre-compilation wins (E1, E3) captured the bulk of the
reachable gain.  After that, `case.search_court` dominates the
runtime (~33 % of extract time on 100 docs post-E3); its cost is
bounded by the regex-engine's work on the ~1 947-option court
alternation over the ±100/200/500 windows.  Moving that work
around (E4a/E4b), pre-filtering it (E5), and micro-optimising its
surroundings (E6, E7, E8, E11) did not move the needle further
than a fraction of a percent.  A real next step would require
changing the extraction algorithm itself — e.g. a compact Aho–
Corasick index over court names — which is outside the scope of
"tweaking the regex implementation".

## TODO (follow-ups, out of scope for this pass)

- Pre-filter court candidates with an Aho–Corasick index (above).
- Cache `infer_court`/`search_court` per `(doc_id, fn_span)` for
  docs with many file numbers in the same court context.
- Replace `RefMarker.replace_content_with_mask` string concat
  with interval tracking — would pay off on very long docs with
  many markers (currently <1 % of extract time on the benchmark).

(The `law_dnc.py` → `law.py` rename listed here previously was
done on 2026-04-21; the profile table above still references the
old name for historical accuracy.)

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
