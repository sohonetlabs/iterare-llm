.PHONY: build-base build sync lock lint lint-fix format test coverage

BASE_TAG ?= latest
BASE_IMAGE_NAME = iterare-base

IMAGE_NAME = iterare-llm
TAG ?= latest

# Docker commands
build-base:
	docker build -t $(BASE_IMAGE_NAME):$(BASE_TAG) -f claude-code/.devcontainer/Dockerfile claude-code/.devcontainer/

build:
	docker build -t $(IMAGE_NAME):$(TAG) .

# Development commands
sync:
	uv sync --all-groups

lock:
	uv lock

lint:
	uv run ruff check .

lint-fix:
	uv run ruff check --fix .

format:
	uv run ruff format .

test:
	uv run pytest tests/

coverage:
	uv run pytest --cov=src --cov-report=term-missing --cov-report=html tests/
