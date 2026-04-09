# ========================
# CONFIG
# ========================

APP=backend.main:app
PYTHON=python
UVICORN=uvicorn

DOCKER_COMPOSE=docker compose
BACKEND_CONTAINER=backend-api-1

# ========================
# DEVELOPMENT
# ========================


dev:
	DB_HOST=localhost BOT_INTERNAL_URL=http://localhost:8081/internal/notify uvicorn backend.main:app --reload --host 0.0.0.0 --port 8080

prod:
	$(DOCKER_COMPOSE) up -d --build


down:
	$(DOCKER_COMPOSE) down
# ========================
# MIGRATIONS
# ========================
up:
	docker compose up -d --build
migrate:
	DB_HOST=localhost PYTHONPATH=. python backend/migrate.py

migrate-prod:
	PYTHONPATH=. DB_HOST=localhost python backend/migrate.py

update:
	git pull origin master
	docker compose down backend && docker compose up -d --build backend