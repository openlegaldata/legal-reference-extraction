# Legal Reference Extraction

## Project layout

- `src/refex/` — source package (src layout, installed via `pip install -e .`)
- `src/refex/orchestrator.py` — `CitationExtractor` (main entry point)
- `src/refex/citations.py` — typed citation models (`LawCitation`, `CaseCitation`, `Span`)
- `src/refex/document.py` — `Document` model, HTML/Markdown normalization, offset mapping
- `src/refex/engines/regex.py` — regex-based extraction engines
- `src/refex/extractors/` — legacy law (`law_dnc.py`) and case (`case.py`) extractors (internal)
- `src/refex/serializers.py` — output format adapters (JSONL, BIO, spaCy, etc.)
- `src/refex/resolver.py` — short-form citation resolution (a.a.O., ebenda, i.V.m.)
- `src/refex/data/` — bundled data files (`law_book_codes.txt`, `file_number_codes.csv`)
- `benchmarks/` — benchmark runner, metrics, adapter, validator, fixtures
- `tests/` — pytest test suite

## Development commands

```
make install       # create .venv, install editable + dev deps (auto-detects uv vs pip)
make test          # pytest
make lint          # ruff check + format check
make format        # ruff auto-fix + format
make bench-ci      # benchmark against vendored CI fixtures
make bench-dev     # benchmark against full validation split
make bench-validate # dataset integrity checks
make diagnose      # error analysis on validation split
```

## Key conventions

- Python >=3.11. Use built-in generics (`list[]`, `tuple[]`, `X | None`) — no `typing` imports for these.
- All source imports are absolute: `from refex.xxx import yyy`.
- Data files accessed via `importlib.resources.files("refex") / "data"`, not `os.path`.
- Regex strings use raw string literals (`r"..."`) to avoid escape sequence warnings.
- Ruff rules: `E, F, I, UP, W`. Line length 120. E501 suppressed in tests (German legal text fixtures).
- No runtime dependencies. Optional extras: `[adapters]` (spaCy), `[crf]` (sklearn-crfsuite), `[transformers]` (transformers + torch), `[training]` (wandb + seqeval + datasets + accelerate, for fine-tuning).

## Architecture

- **`CitationExtractor`** (orchestrator.py) is the public API. It runs multiple `Extractor` engines and merges results.
- **`RegexLawExtractor`** + **`RegexCaseExtractor`** (engines/regex.py) wrap the legacy extractors and emit typed `LawCitation`/`CaseCitation` objects.
- **`Document`** (document.py) wraps input with format metadata. Supports plain text, HTML, and Markdown. HTML/Markdown is normalized to plain text with character-level offset maps for span round-tripping.
- **Legacy `RefExtractor`** (extractor.py) is deprecated but preserved for backward compatibility. Internally delegates to the mixin extractors which produce `RefMarker`/`Ref` objects (internal types, not public API).
- Law extraction uses divide-and-conquer: multi-refs (`§§`) first, then single-refs (`§`), masking matched regions.
- Case extraction finds file numbers via regex, then heuristically searches surrounding text for court names.

## Benchmark

- Benchmark data lives in sibling project `german-legal-references-benchmark` (HF Arrow dataset).
- CI fixtures vendored in `benchmarks/fixtures/` (plain-text, HTML, and Markdown docs).
- All optimization uses **validation split only**. Test split reserved for final evaluation.

## Testing

- Tests use fixtures from `conftest.py`. The `assert_refs` helper extracts from content and compares sorted ref lists.
- `test_format_fixtures.py` — integration tests for HTML and Markdown input with real court decision fixtures.
- `test_document.py` — Document model, normalization, offset mapping, format detection.

## Git

- Before committing run `make lint` and `make test`
- Use prefix branches: chore/, fix/, feat/
