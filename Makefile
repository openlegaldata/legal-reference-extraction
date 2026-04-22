.PHONY: help venv install install-crf install-transformers install-training install-all test test-cov lint format clean bench bench-ci bench-dev bench-test bench-quick bench-json bench-validate diagnose train-crf eval-crf bench-crf bench-transformer export-bio train-transformer-subset train-transformer eval-transformer bench-transformer-trained

PYTHON ?= python3
VENV := .venv
BIN := $(VENV)/bin

# Auto-detect: prefer uv, fall back to pip
UV := $(shell command -v uv 2>/dev/null)

ifdef UV
  VENV_CMD = uv venv $(VENV) --python $(PYTHON)
  INSTALL_CMD = uv pip install --python $(BIN)/python
else
  VENV_CMD = $(PYTHON) -m venv $(VENV) && $(BIN)/pip install --upgrade pip
  INSTALL_CMD = $(BIN)/pip install
endif

help:  ## Show this help message
	@awk 'BEGIN {FS = ":.*?## "; printf "Usage: make \033[36m<target>\033[0m\n\nTargets:\n"} /^[a-zA-Z_-]+:.*?## / {printf "  \033[36m%-20s\033[0m %s\n", $$1, $$2}' $(MAKEFILE_LIST)

venv:  ## Create virtualenv (auto-detects uv vs pip)
	$(VENV_CMD)

install: venv  ## Install package with dev dependencies (editable)
	$(INSTALL_CMD) -e ".[dev]"

install-crf: install  ## Install CRF engine extras (sklearn-crfsuite)
	$(INSTALL_CMD) -e ".[crf]"

install-transformers: install  ## Install transformer engine extras (transformers, torch)
	$(INSTALL_CMD) -e ".[transformers]"

install-training: install  ## Install training extras (CRF + transformers + wandb + seqeval + datasets + accelerate)
	$(INSTALL_CMD) -e ".[crf,transformers,training]"

install-all: venv  ## Install package with all optional dependencies
	$(INSTALL_CMD) -e ".[all]"

test: install  ## Run pytest test suite
	$(BIN)/pytest

test-cov: install  ## Run tests with coverage report (HTML + terminal)
	$(BIN)/pytest --cov --cov-report=term-missing --cov-report=html

lint: install  ## Check code with ruff (lint + format check)
	$(BIN)/ruff check src/ tests/
	$(BIN)/ruff format --check src/ tests/

format: install  ## Auto-fix lint issues and format code with ruff
	$(BIN)/ruff check --fix src/ tests/
	$(BIN)/ruff format src/ tests/

bench: install  ## Run benchmark (pass extra args via BENCH_ARGS=...)
	$(BIN)/python -m benchmarks.run $(BENCH_ARGS)

bench-ci: install  ## Run benchmark against vendored CI fixtures (no external data)
	$(BIN)/python -m benchmarks.run -d benchmarks/fixtures $(BENCH_ARGS)

bench-dev: install  ## Run benchmark against validation split (development)
	$(BIN)/python -m benchmarks.run -s validation $(BENCH_ARGS)

bench-test: install  ## Run benchmark against test split (final evaluation only)
	$(BIN)/python -m benchmarks.run -s test $(BENCH_ARGS)

bench-quick: install  ## Quick benchmark sanity check (50 validation docs)
	$(BIN)/python -m benchmarks.run -s validation -n 50

bench-json: install  ## Run benchmark with JSON output
	$(BIN)/python -m benchmarks.run --json $(BENCH_ARGS)

bench-validate: install  ## Run dataset integrity checks
	$(BIN)/python -m benchmarks.validate $(BENCH_ARGS)

diagnose: install  ## Error analysis on validation split
	$(BIN)/python -m benchmarks.diagnose --split validation $(BENCH_ARGS)

train-crf: install-crf  ## Train CRF model (pass args via CRF_ARGS=...)
	$(BIN)/python -m refex.engines.crf --train $(CRF_ARGS)

eval-crf: install-crf  ## Evaluate trained CRF model
	$(BIN)/python -m refex.engines.crf --evaluate $(CRF_ARGS)

bench-crf: install-crf  ## Benchmark regex+CRF ensemble on validation split
	$(BIN)/python -m benchmarks.run -s validation -e regex+crf $(BENCH_ARGS)

bench-transformer: install-transformers  ## Benchmark regex+transformer ensemble (downloads weights)
	$(BIN)/python -m benchmarks.run -s validation -e regex+transformer $(BENCH_ARGS)

export-bio: install-training  ## Export BIO JSONL for train/validation/test splits
	$(BIN)/python scripts/export_bio.py --split train --output data/hf_bio/train.jsonl
	$(BIN)/python scripts/export_bio.py --split validation --output data/hf_bio/validation.jsonl
	$(BIN)/python scripts/export_bio.py --split test --output data/hf_bio/test.jsonl

train-transformer-subset: install-training  ## Smoke-test training (500 docs, 2 epochs)
	$(BIN)/python scripts/train_transformer.py \
		--train data/hf_bio/train.jsonl \
		--eval data/hf_bio/validation.jsonl \
		--output models/refex-eurobert-210m-smoke \
		--device mps --epochs 2 --batch-size 16 --limit 500 \
		--wandb-run-name eurobert-210m-smoke $(TRAIN_ARGS)

train-transformer: install-training  ## Full transformer training (EuroBERT-210m, 3 epochs)
	$(BIN)/python scripts/train_transformer.py \
		--train data/hf_bio/train.jsonl \
		--eval data/hf_bio/validation.jsonl \
		--output models/refex-eurobert-210m \
		--device mps --epochs 3 --batch-size 16 \
		--wandb-run-name eurobert-210m-full-e3-b16-lr3e5 $(TRAIN_ARGS)

eval-transformer: install-transformers  ## Evaluate trained transformer on validation (full engine)
	REFEX_TRANSFORMER_MODEL=models/refex-eurobert-210m REFEX_TRANSFORMER_DEVICE=mps \
		$(BIN)/python -m benchmarks.run -s validation -e transformer --json \
		--output logs/bench-transformer-validation.json $(BENCH_ARGS)

bench-transformer-trained: install-transformers  ## Benchmark regex+trained transformer on validation
	REFEX_TRANSFORMER_MODEL=models/refex-eurobert-210m REFEX_TRANSFORMER_DEVICE=mps \
		$(BIN)/python -m benchmarks.run -s validation -e regex+transformer --json \
		--output logs/bench-regex+transformer-validation.json $(BENCH_ARGS)

clean:  ## Remove virtualenv, build artifacts, and __pycache__ directories
	rm -rf $(VENV) build/ dist/ *.egg-info src/*.egg-info
	find . -type d -name __pycache__ -exec rm -rf {} +
