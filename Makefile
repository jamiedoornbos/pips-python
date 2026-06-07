.PHONY: format lint-fix lint

format:
	uv run ruff format pips

lint-fix:
	uv run ruff check --fix pips

lint:
	uv run ruff check pips
