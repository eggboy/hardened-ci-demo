.PHONY: build test lint

build:
	python3 -m pip install -q -e '.[dev]'

test:
	python3 -m pytest -q

lint:
	ruff check . && ruff format --check .
