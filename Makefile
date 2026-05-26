.PHONY: help install run test lint smoke clean docker docker-run

help:
	@echo "make install   - crea .venv e instala deps de desarrollo"
	@echo "make run       - arranca el bot (polling Telegram)"
	@echo "make test      - corre pytest"
	@echo "make smoke     - clasifica 4 leads de ejemplo contra el LLM real"
	@echo "make lint      - ruff check + ruff format --check"
	@echo "make docker    - construye la imagen Docker"
	@echo "make docker-run- arranca con docker compose"

install:
	python3.11 -m venv .venv 2>/dev/null || PYENV_VERSION=3.11.12 python -m venv .venv
	.venv/bin/pip install -U pip
	.venv/bin/pip install -e ".[dev]"

run:
	.venv/bin/python -m app.main

test:
	.venv/bin/python -m pytest -q

smoke:
	.venv/bin/python scripts/smoke_classify.py

lint:
	.venv/bin/ruff check app tests scripts
	.venv/bin/ruff format --check app tests scripts

clean:
	rm -rf .venv .pytest_cache .ruff_cache .mypy_cache **/__pycache__ leads.db

docker:
	docker build -t orbyn-lead-qualifier:latest .

docker-run:
	docker compose up -d --build
