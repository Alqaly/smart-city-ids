.PHONY: help check db-migrate start ids-api-venv test docs-check smoke-test

help:
	@echo "Available targets: check db-migrate start ids-api-venv test docs-check smoke-test"

check:
	@bash scripts/check-setup.sh

db-migrate:
	@bash scripts/db/run_migrations.sh

start:
	@bash scripts/start-everything.sh

ids-api-venv:
	@cd services/ids-api/src && python -m venv venv && . venv/bin/activate && pip install -r requirements.txt

test:
	@npm run -s test || pytest -q

docs-check:
	@bash scripts/docs/check-docs.sh

smoke-test:
	@OPENAI_API_KEY=test GROQ_API_KEY=test pytest -q tests/smoke
