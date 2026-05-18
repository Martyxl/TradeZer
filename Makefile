.PHONY: dev dev-api dev-web seed test test-api test-web migrate install

# Spustí backend + frontend concurrently
dev:
	@echo "Spouštím Tradezer (backend + frontend)..."
	@start cmd /k "cd api && python -m uvicorn app.main:app --reload --port 8000"
	@start cmd /k "cd web && npm run dev"
	@echo "Backend: http://localhost:8000/docs"
	@echo "Frontend: http://localhost:3000"

dev-api:
	cd api && python -m uvicorn app.main:app --reload --port 8000

dev-web:
	cd web && npm run dev

seed:
	cd api && python -m app.db.seed

migrate:
	cd api && alembic upgrade head

install:
	cd api && pip install -r requirements.txt
	cd web && npm install

test:
	$(MAKE) test-api
	$(MAKE) test-web

test-api:
	cd api && python -m pytest tests/ -v --tb=short

test-web:
	cd web && npm test
