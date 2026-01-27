# Legal Reference Extraction

## Project layout

- `src/refex/` — source package (src layout, installed via `pip install -e .`)
- `src/refex/data/` — bundled data files (`law_book_codes.txt`, `file_number_codes.csv`)
- `src/refex/extractors/` — law and case reference extractors
- `tests/` — pytest test suite
- `tests/resources/` — test fixture files (German legal text snippets)
- `tests/conftest.py` — shared fixtures (`extractor`, `law_extractor`, `case_extractor`) and helpers (`assert_refs`, `get_book_codes_from_file`)

## Development commands

```
make install   # create .venv, install editable + dev deps (auto-detects uv vs pip)
make test      # pytest
make lint      # ruff check + format check
make format    # ruff auto-fix + format
```

## Key conventions

- Python >=3.11. Use built-in generics (`list[]`, `tuple[]`, `X | None`) — no `typing` imports for these.
- All source imports are absolute: `from refex.xxx import yyy`.
- Data files accessed via `importlib.resources.files("refex") / "data"`, not `os.path`.
- Regex strings use raw string literals (`r"..."`) to avoid escape sequence warnings.
- Ruff rules: `E, F, I, UP, W`. Line length 120. E501 suppressed in tests (German legal text fixtures).
- No runtime dependencies. Dev deps: `pytest`, `ruff`.

## Architecture notes

- `RefExtractor` is the main entry point. It inherits from both `DivideAndConquerLawRefExtractorMixin` (law refs) and `CaseRefExtractorMixin` (case refs). Toggle via `do_law_refs` / `do_case_refs` bools.
- `extract()` returns `(content_with_markers, list[RefMarker])`. Markers wrap the matched text with `[ref=UUID]...[/ref]` tags.
- Law extraction uses a divide-and-conquer approach: first multi-refs (`§§`), then single-refs (`§`), masking matched regions to prevent double-matching.
- Case extraction finds file numbers via regex, then heuristically searches surrounding text for court names.
- `law_book_context` attribute enables within-book extraction (sections without explicit book codes).

## Testing

- 42 tests, 4 skipped (known unsupported patterns marked with `@pytest.mark.skip`).
- Tests use fixtures from `conftest.py`. The `assert_refs` helper extracts from content and compares sorted ref lists.
- Test resource files in `tests/resources/law/` and `tests/resources/case/` contain German legal text snippets.


## Git

- Before commiting run "make lint" and "make test"
- Use prefix branches: chore/, fix/, feat/

