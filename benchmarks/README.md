# Benchmark Suite

Measures the citation extractor against gold-annotated German legal documents.

## Quick Start

```bash
# Run against vendored CI subset (no external data needed)
make bench-ci

# Run against full 10k HF dataset (validation split)
make bench-dev

# Quick check (50 docs)
make bench-quick

# Validate dataset integrity
make bench-validate
```

## Data Layout

The benchmark uses two JSONL files per split:

- **`documents.jsonl`** — one JSON object per document with `doc_id`, `text`, metadata
- **`annotations.jsonl`** — one JSON object per document with `doc_id`, `citations[]`, `relations[]`

Schemas are in `benchmarks/schemas/`.

### Data Sources

| Source | Location | Usage |
|--------|----------|-------|
| CI subset | `benchmarks/fixtures/` | Vendored, runs on every PR |
| Full dataset | Sibling project or `BENCH_DATA_DIR` | Development and final eval |

The full 10k dataset lives at `../german-legal-references-benchmark/data/benchmark_10k_hf/`
(HF Arrow format with train/validation/test splits). Override with:

```bash
export BENCH_DATA_DIR=/path/to/dataset
make bench-dev
```

## Metrics

### Span Detection
- **Exact match** — predicted span `(start, end)` must match gold exactly
- **Overlap match** — predicted and gold spans must overlap (any intersection)

### Per-Type F1
Separate precision/recall/F1 for `law` and `case` citation types.

### Field Accuracy
On matched citation pairs, measures accuracy of extracted fields:
- **Law**: `book`, `number`
- **Case**: `court`, `file_number`

## CLI Options

```bash
python -m benchmarks.run [OPTIONS]

  -d, --data-dir PATH    Dataset directory (default: auto-detect)
  -s, --split SPLIT      train / validation / test (default: test)
  -n, --limit N          Process at most N documents
  --json                 Output results as JSON
  -o, --output FILE      Write output to file
  -v, --verbose          Show per-document errors
```

### Error Diagnosis

```bash
python -m benchmarks.diagnose --split validation --limit 100
```

Shows false negatives/positives by type, missing book codes, overlap mismatches,
and file number pattern analysis.

### Dataset Validation

```bash
python -m benchmarks.validate -d benchmarks/fixtures
```

Runs integrity checks: span consistency, ID uniqueness, controlled vocabulary,
join integrity, and relation validity. Exit code 0 = all pass.

## Makefile Targets

| Target | Description |
|--------|-------------|
| `bench` | Run benchmark (default: test split of full dataset) |
| `bench-ci` | Run against vendored CI fixtures |
| `bench-dev` | Run against validation split |
| `bench-test` | Run against test split (final eval only) |
| `bench-quick` | 50 docs on validation split |
| `bench-json` | JSON output |
| `bench-validate` | Run dataset integrity checks |
| `diagnose` | Error analysis on validation split |

## CI Integration

The `bench.yml` workflow runs on every PR that touches `src/`, `benchmarks/`,
or `pyproject.toml`. It validates the CI fixtures and runs the benchmark,
uploading results as an artifact.

## Development Workflow

1. Make changes to the extractor in `src/refex/`
2. Run `make bench-quick` to check impact on 50 docs
3. Run `make bench-dev` for full validation split
4. Run `make diagnose` to understand error patterns
5. **Never** use `make bench-test` during development (reserved for final eval)

All optimization decisions must use the **validation split** only. The test
split is reserved for one-shot final evaluation to avoid train-test leakage.
