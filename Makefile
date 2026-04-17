.PHONY: build build-multiarch push sync lock lint lint-fix format test coverage

IMAGE_NAME = iterare-llm
REGISTRY = sohonet/iterare-llm
TAG ?= latest
PLATFORMS ?= linux/amd64,linux/arm64

# Docker commands
build:
	docker build -t $(IMAGE_NAME):$(TAG) .

build-multiarch:
	docker buildx build --platform $(PLATFORMS) -t $(IMAGE_NAME):$(TAG) .

push:
	docker buildx build --platform $(PLATFORMS) \
		--tag $(REGISTRY):$(TAG) \
		--tag $(REGISTRY):latest \
		--push .

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
