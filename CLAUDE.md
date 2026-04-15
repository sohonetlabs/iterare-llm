# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

`iterare` is an automation tool for **unattended execution of Claude Code prompts in isolated Docker containers**. It creates git worktrees, launches containerized Claude Code instances with dangerous permissions enabled, and maintains safety through network firewalls and isolation.

**Key concept**: This enables "agentic loops" where Claude Code can autonomously modify codebases without human confirmation, while maintaining security through containerization.

## Development Commands

### Package Management
This project uses `uv` for Python dependency management:
```bash
make sync          # Sync dependencies (uv sync --all-groups)
make lock          # Update lock file (uv lock)
```

### Code Quality
```bash
make lint          # Check code style with ruff
make lint-fix      # Auto-fix style issues
make format        # Format code with ruff
```

### Testing
```bash
make test          # Run all tests
make coverage      # Run tests with coverage report

# Run specific test file
uv run pytest tests/test_docker.py

# Run specific test
uv run pytest tests/test_docker.py::test_image_exists -v

# Run with verbose output
uv run pytest -v tests/
```

### Docker Images
```bash
make build-base    # Build base iterare-base image (prerequisite)
make build         # Build iterare-llm image
```

### Running the Tool
```bash
# Initialize a project
uv run iterare init

# Execute a prompt (creates worktree and launches container)
uv run iterare execute <prompt-name>

# Pass environment variables to the container
uv run iterare execute <prompt-name> --env PIP_INDEX_URL --env CUSTOM_VAR

# Start interactive session
uv run iterare interactive

# Start interactive session with environment variables
uv run iterare interactive --env PIP_INDEX_URL --env NPM_REGISTRY

# Monitor execution
docker logs -f it-<workspace-name>
```

## Architecture

### Execution Flow

The `execute` command orchestrates this workflow (see `src/iterare_llm/commands/execute.py:274`):

1. **Load configuration** from `.iterare/config.toml`
2. **Parse prompt** file (supports YAML frontmatter for metadata)
3. **Create git worktree** at `workspaces/<workspace-name>` on branch `worktree/<workspace-name>`
4. **Prepare workspace** by writing `.claude-auto-config.json` and `.claude-prompt.md`
5. **Launch Docker container** with:
   - Worktree mounted at `/workspace`
   - Credentials mounted from `~/.iterare/.credentials.json`
   - Firewall configured with allowed domains
   - Claude Code running in dangerous mode (no user prompts)
6. **Container executes** autonomously until completion

### Key Modules

**Core orchestration:**
- `commands/execute.py` - Main execution orchestrator (11-step workflow)
- `commands/init.py` - Project initialization with templates

**Domain modules:**
- `git.py` - Git worktree lifecycle (create/remove/list)
- `docker.py` - Docker container management, volume mounts, configuration
- `config.py` - TOML config parsing with dataclass validation
- `prompt.py` - Prompt file parsing with YAML frontmatter support

**Infrastructure:**
- `logging.py` - Centralized logging with debug/info/error levels
- `exceptions.py` - Custom exception hierarchy (all inherit from `IterareError`)

### Docker Architecture

Three-layer architecture:

1. **Base image** (`iterare-base:latest`): Claude Code Node.js application
2. **Agentic loop image** (`iterare-llm:latest`): Adds `uv`, `jq`, firewall scripts, entrypoint
3. **Runtime container**: Mounts worktree, credentials, runs with `NET_ADMIN` capability for firewall

**Entrypoint sequence** (`docker/entrypoint.sh`):
1. Verify credentials mounted correctly
2. Initialize firewall whitelist (`docker/init-firewall.sh`)
3. Launch Claude Code with prompt

### Network Security (Firewall)

The firewall implements **whitelist-based isolation** using iptables:

- **Default allowed**: `api.anthropic.com`, GitHub APIs, npm registry, VS Code marketplace
- **Configurable**: Add domains in `config.toml` under `[firewall] allowed_domains`
- **Mechanism**: Uses ipsets to allow only whitelisted IPs, blocks everything else
- **Purpose**: Prevents autonomous agent from exfiltrating code or installing malicious packages

Example configuration for Python projects:
```toml
[firewall]
allowed_domains = [
    "pypi.org",
    "files.pythonhosted.org",
]
```

## Testing Guidelines

### Test Organization
- Each module has corresponding test file: `src/iterare_llm/foo.py` → `tests/test_foo.py`
- Use pytest fixtures for common setup (see `tests/conftest.py` if it exists)
- Mock Docker/git operations to avoid side effects

### Resource Cleanup
Always clean up in tests:
```python
def test_something():
    resource = create_resource()
    try:
        # Test logic
        assert resource.works()
    finally:
        resource.cleanup()  # Always runs
```

### Running Tests
- **Always run full test suite** before committing: `make coverage`
- Check that coverage doesn't decrease
- Tests must pass with no warnings

## Configuration

### Project Structure After Init
```
.iterare/
├── config.toml           # Main configuration
├── prompts/              # Prompt files (.md)
│   └── example.md
└── Dockerfile            # Custom Docker image (optional)

workspaces/               # Git worktrees (gitignored)
└── <workspace-name>/     # Created per execution
```

### Config File Format (`config.toml`)

```toml
[docker]
image = "iterare-llm:latest"

[credentials]
claude_path = "~/.iterare/.credentials.json"

[firewall]
allowed_domains = [
    "pypi.org",
    "files.pythonhosted.org",
]
```

### Prompt File Format

Prompts support YAML frontmatter for metadata:

```markdown
---
workspace: my-feature
branch: main
---

# Task Description

Implement feature X by doing Y and Z.
```

Frontmatter fields:
- `workspace`: Worktree directory name (defaults to prompt filename stem)
- `branch`: Base branch for worktree (defaults to current branch)

### Environment Variables

Pass environment variables from your host to the container using the `--env` / `-e` flag. This works for both `execute` and `interactive` commands:

```bash
# Execute mode: Pass a single variable
iterare execute my-prompt --env PIP_INDEX_URL

# Execute mode: Pass multiple variables
iterare execute my-prompt --env PIP_INDEX_URL --env CUSTOM_VAR --env API_KEY

# Interactive mode: Pass environment variables
iterare interactive --env PIP_INDEX_URL --env GITHUB_TOKEN
```

**How it works:**
- The `--env` flag accepts the *name* of an environment variable (not the value)
- `iterare` reads the value from your current shell environment
- The variable and its value are passed to the Docker container
- If a specified variable is not set in your environment, execution fails with an error

**Common use cases:**
- Custom package indexes: `--env PIP_INDEX_URL` for Python projects
- API keys and tokens: `--env GITHUB_TOKEN` for accessing private repositories
- Build configuration: `--env NODE_ENV` for Node.js builds

**Example:**
```bash
# Set environment variables in your shell
export PIP_INDEX_URL="https://pypi.company.internal/simple"
export NPM_REGISTRY="https://npm.company.internal"

# Execute mode: Pass them to the container
iterare execute install-deps --env PIP_INDEX_URL --env NPM_REGISTRY

# Interactive mode: Pass them to the container
iterare interactive --env PIP_INDEX_URL --env NPM_REGISTRY
```

## Common Issues

### Image Not Found
If `iterare execute` fails with "Docker image not found":
1. Build base image first: `make build-base`
2. Build agentic loop image: `make build`

### Container Already Running
If execution fails with "Container already running":
```bash
docker stop iterare-<workspace-name>
docker rm iterare-<workspace-name>
```

### Credentials Not Found
Ensure Claude Code credentials exist:
```bash
ls ~/.iterare/.credentials.json
ls ~/.iterare/.claude.json
```

### Network Blocked
If container can't access required domains, add them to `config.toml`:
```toml
[firewall]
allowed_domains = ["example.com"]
```

## Code Style Notes

- This project follows PEP 8 and uses `ruff` for linting/formatting
- All public functions have numpy-style docstrings
- Type hints are used throughout
- Prefer dataclasses for configuration objects (see `config.py`)
- Use pathlib `Path` objects, not string paths
- Log at appropriate levels: `logger.debug()` for details, `logger.info()` for milestones, `logger.error()` for failures

## Virtual Environment

This project uses `uv` which automatically manages virtual environments. If you need to activate manually:
```bash
source .venv/bin/activate  # Unix
.venv\Scripts\activate     # Windows
```
