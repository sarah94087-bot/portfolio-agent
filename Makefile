# Developer commands (docs/05-architecture.md, section 9). On Windows without make,
# run the command under each target directly.

PY := backend/.venv/bin/python

.PHONY: setup db migrate api web test lint

setup:
	python -m venv backend/.venv
	$(PY) -m pip install -e "backend[dev]"
	cd apps/web && npm ci

db:
	docker compose up -d --wait db

migrate: db
	DATABASE_URL=postgresql://agent:agent@localhost:5432/agent $(PY) -m portfolio_agent.migrate

api:
	cd backend && .venv/bin/python -m uvicorn portfolio_agent.main:app --reload --port 8000

web:
	cd apps/web && npm run dev

test: db
	cd backend && TEST_DATABASE_URL=postgresql://agent:agent@localhost:5432/agent .venv/bin/python -m pytest -q
	cd backend && .venv/bin/python -m pytest -q ../evals

lint:
	cd backend && .venv/bin/python -m ruff check . ../evals
	cd apps/web && npm run lint && npx tsc --noEmit
