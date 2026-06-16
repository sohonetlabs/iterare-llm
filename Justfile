image_name := "iterare-llm"
registry := "sohonet/iterare-llm"
platforms := "linux/amd64,linux/arm64"
default_version := `cat VERSION`

# List available recipes
default:
    @just --list

# Docker commands

# Build single-arch image tagged with version (and `latest` unless latest=false)
build version=default_version latest="true":
    docker build \
        -t {{image_name}}:{{version}} \
        {{ if latest == "true" { "-t " + image_name + ":latest" } else { "" } }} \
        .

# Build multi-arch image locally tagged with version (and `latest` unless latest=false)
build-multiarch version=default_version latest="true":
    docker buildx build --platform {{platforms}} \
        -t {{image_name}}:{{version}} \
        {{ if latest == "true" { "-t " + image_name + ":latest" } else { "" } }} \
        .

# Build multi-arch and push to registry tagged with version (and `latest` unless latest=false)
push version=default_version latest="true":
    docker buildx build --no-cache --platform {{platforms}} \
        --tag {{registry}}:{{version}} \
        {{ if latest == "true" { "--tag " + registry + ":latest" } else { "" } }} \
        --push .

# Development commands

# Sync dependencies including dev groups
sync:
    uv sync --all-groups

# Update lock file
lock:
    uv lock

# Check code style
lint:
    uv run ruff check .

# Auto-fix style issues
lint-fix:
    uv run ruff check --fix .

# Format code
format:
    uv run ruff format .

# Run test suite
test:
    uv run pytest tests/

# Run tests with coverage report
coverage:
    uv run pytest --cov=src --cov-report=term-missing --cov-report=html tests/

# Packaging commands

# Build wheel and sdist into dist/
build-pkg:
    uv build

# Publish built artifacts in dist/ to PyPI (uses UV_PUBLISH_TOKEN if set)
publish:
    uv publish
