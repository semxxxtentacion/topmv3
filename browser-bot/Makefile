VENV := .venv
PYTHON := $(VENV)/bin/python
PIP := $(VENV)/bin/pip

# ---- Setup ----

venv:
	python3 -m venv $(VENV)
	$(PIP) install --upgrade pip

install: venv
	$(PIP) install -r requirements.txt
	$(PIP) install -r yandex-bot/requirements.txt
	$(PYTHON) -m playwright install chromium

# ---- Yandex Bot ----

bot-test:
	$(PYTHON) -m yandex-bot -k "джорданы alljordan.ru" -s alljordan.ru --headless false -w 1

bot-cli:
	$(PYTHON) -m yandex-bot --cli -w 3

bot-server:
	$(PYTHON) -m yandex-bot server

# ---- Generator ----

generate:
	$(PYTHON) -m generator --count 100 --workers 10

server:
	$(PYTHON) -m generator server

# ---- Docker ----

up:
	docker compose up -d --build

down:
	docker compose down

logs:
	docker compose logs -f app

# ---- Helpers ----

stats:
	curl -s http://localhost:8000/stats | python3 -m json.tool

clean:
	rm -rf $(VENV) __pycache__ generator/__pycache__ yandex-bot/__pycache__

.PHONY: venv install bot-test bot-cli bot-server generate server up down logs stats clean
