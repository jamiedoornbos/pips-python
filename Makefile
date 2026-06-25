.PHONY: format lint-fix lint migration upgrade downgrade

format:
	uv run ruff format pips alembic

lint-fix:
	uv run ruff check --fix pips alembic

lint:
	uv run ruff check pips alembic

run:
	uv run fastapi dev pips/app/main.py --reload-dir pips

migration:
	@test -n "$(MESSAGE)" || (echo "Error: MESSAGE is required. Usage: make db-rev-generate MESSAGE='your message'"; exit 1)
	uv run alembic revision --autogenerate -m "$(MESSAGE)"

upgrade:
	uv run alembic upgrade head

downgrade:
	uv run alembic downgrade -1
