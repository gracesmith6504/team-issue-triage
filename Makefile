.PHONY: test lint build format

test:
	python3 -m pytest tests/ -v

lint:
	python3 -m ruff check app/ tests/
	python3 -m ruff format --check app/ tests/

format:
	python3 -m ruff format app/ tests/

build:
	docker build -t team-issue-triage .
