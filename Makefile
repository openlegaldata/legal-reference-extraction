.PHONY: venv install test test-cov lint format clean

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

clean:
	rm -rf $(VENV) build/ dist/ *.egg-info src/*.egg-info
	find . -type d -name __pycache__ -exec rm -rf {} +
