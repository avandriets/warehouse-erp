PYTHON := .venv/bin/python
PIP := .venv/bin/pip
ALEMBIC := .venv/bin/alembic
PYTEST := .venv/bin/pytest
RUFF := .venv/bin/ruff
UVICORN := .venv/bin/uvicorn
PRE_COMMIT := .venv/bin/pre-commit

.PHONY: init migrate run test lint format check pre-commit

init:
	python3 -m venv .venv
	$(PYTHON) -m pip install --upgrade pip
	$(PIP) install -e '.[dev]'
	test -f .env || cp .env.example .env

migrate:
	$(ALEMBIC) upgrade head

run:
	$(PYTHON) -m warehouse_erp.run

test:
	$(PYTEST)

lint:
	$(RUFF) check .
	$(RUFF) format --check .

format:
	$(RUFF) check --fix .
	$(RUFF) format .

check: lint test

pre-commit:
	$(PRE_COMMIT) install
