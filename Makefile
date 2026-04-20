.PHONY: venv install install-ml test test-cov lint format clean bench bench-ci bench-dev bench-test bench-quick bench-json bench-validate diagnose train-crf eval-crf

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

venv:
	$(VENV_CMD)

install: venv
	$(INSTALL_CMD) -e ".[dev]"

install-ml: install
	$(INSTALL_CMD) -e ".[ml]"

test: install
	$(BIN)/pytest

test-cov: install
	$(BIN)/pytest --cov --cov-report=term-missing --cov-report=html

lint: install
	$(BIN)/ruff check src/ tests/
	$(BIN)/ruff format --check src/ tests/

format: install
	$(BIN)/ruff check --fix src/ tests/
	$(BIN)/ruff format src/ tests/

# Benchmark: use -s validation for development, -s test only for final eval
# bench-ci runs against vendored fixtures (no external data needed)
bench: install
	$(BIN)/python -m benchmarks.run $(BENCH_ARGS)

bench-ci: install
	$(BIN)/python -m benchmarks.run -d benchmarks/fixtures $(BENCH_ARGS)

bench-dev: install
	$(BIN)/python -m benchmarks.run -s validation $(BENCH_ARGS)

bench-test: install
	$(BIN)/python -m benchmarks.run -s test $(BENCH_ARGS)

bench-quick: install
	$(BIN)/python -m benchmarks.run -s validation -n 50

bench-json: install
	$(BIN)/python -m benchmarks.run --json $(BENCH_ARGS)

bench-validate: install
	$(BIN)/python -m benchmarks.validate $(BENCH_ARGS)

diagnose: install
	$(BIN)/python -m benchmarks.diagnose --split validation $(BENCH_ARGS)

# CRF engine (requires [ml] extra)
train-crf: install-ml
	$(BIN)/python -m refex.engines.crf --train $(CRF_ARGS)

eval-crf: install-ml
	$(BIN)/python -m refex.engines.crf --evaluate $(CRF_ARGS)

bench-crf: install-ml
	$(BIN)/python -m benchmarks.run -s validation -e regex+crf $(BENCH_ARGS)

clean:
	rm -rf $(VENV) build/ dist/ *.egg-info src/*.egg-info
	find . -type d -name __pycache__ -exec rm -rf {} +
