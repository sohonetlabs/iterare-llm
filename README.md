# Iterare

Automated Claude Code execution in isolated Docker containers.

`iterare` creates git worktrees, launches containerised Claude Code instances with autonomous permissions, and
maintains safety through network firewalls and container isolation. This enables "agentic loops" where Claude
Code can modify codebases without human confirmation while being restricted to whitelisted network access and
mounted files.

_**Warning – This does not fully protect from malicious code execution or data exfiltration. It simply raises the 
barriers to these things happening. Use at your own risk.**_

## Prerequisites

- Python 3.13+
- [uv](https://docs.astral.sh/uv/) for dependency management
- Docker
- A Claude Code API key

## Installation

```bash
# Install via pypi
pip install iterare-llm

# Create global config directories
iterare install

# Fetch Claude Code credentials (interactive Docker session)
iterare credentials
```

## Quick Start

The easiest way to get started is to use the interactive mode. This launches a Claude Code session in a Docker
container, mounts your current project directory, and allows you to drive Claude Code yourself.

```bash
# Initialize a project
cd /path/to/your/project
iterare init

# Launch in interactive mode
iterare interactive
```

Alternatively, you can create a prompt file and execute it. This (by default) creates a git worktree, and branches
off of the current branch. It then launches Claude Code in a Docker container, mounts the worktree directory, and
passes the prompt to Claude Code which will then execute the prompt until it's done. This is fantastic for autonomous
development.

```bash
# Initialize a project
cd /path/to/your/project
iterare init

# Create a prompt
cat > .iterare/prompts/refactor.md << 'EOF'
---
workspace: refactor-auth
branch: main
---

Refactor the authentication module to use JWT tokens.
Add tests for the new implementation.
EOF

# Execute the prompt
iterare execute refactor

# Monitor progress
iterare log -f

# When done, merge changes back
iterare merge

# Clean up the worktree
iterare cleanup -y
```

## Commands

### `iterare init [PATH]`

Initialise a project for iterare. Creates the `.iterare/` directory with configuration files and
a `workspaces/` directory for git worktrees.

```bash
iterare init                    # Initialize current directory
iterare init /path/to/project   # Initialize specific directory
iterare init --force            # Overwrite existing configuration
```

### `iterare install`

Create global configuration directories for credentials and logs.

```bash
iterare install
```

### `iterare credentials`

Fetch Claude Code credentials via an interactive Docker session. Launches a container where you can log in, 
then extracts the credential files.

```bash
iterare credentials             # First-time setup
iterare credentials --force     # Re-authenticate
iterare credentials --image my-image:latest  # Use custom image
```

### `iterare execute <prompt>`

Execute a prompt in an isolated Docker container. Creates a git worktree, mounts it in a container, and launches 
Claude Code in autonomous mode.

```bash
# By prompt name (looks in .iterare/prompts/)
iterare execute refactor

# By file path
iterare execute .iterare/prompts/task.md

# Reuse an existing workspace
iterare execute refactor --reuse refactor-abc12345

# Pass environment variables to the container
iterare execute refactor --env PIP_INDEX_URL --env GITHUB_TOKEN
```

### `iterare interactive`

Launch an interactive Claude Code session in a container. By default runs in the project directory without
creating a worktree.

```bash
# Default: run in project directory
iterare interactive

# Create a worktree for isolation
iterare interactive --worktree

# Name the workspace
iterare interactive --worktree --workspace my-feature

# Base on a specific branch
iterare interactive --worktree --branch main

# Reuse an existing workspace
iterare interactive --worktree --reuse my-feature-abc12345

# Pass environment variables
iterare interactive --env PIP_INDEX_URL
```

### `iterare log [RUN_NAME]`

View execution logs for a run.

```bash
iterare log                     # Most recent run
iterare log refactor-abc12345   # Specific run
iterare log -f                  # Follow live output
iterare log --raw               # Raw JSON output
iterare log -v 0                # Minimal (text responses only)
iterare log -v 2                # Verbose (all details)
```

### `iterare list`

List execution runs for the project.

```bash
iterare list                    # Active and finished runs
iterare list --all              # Include cleaned up runs
```

### `iterare merge [RUN_NAME]`

Merge a worktree branch back into the current branch.

```bash
iterare merge                   # Merge most recent run
iterare merge refactor-abc12345 # Merge specific run
```

### `iterare cleanup [RUN_NAME]`

Remove the git worktree and branch for a run. Log files are preserved.

```bash
iterare cleanup                 # Clean up most recent run
iterare cleanup -y              # Skip confirmation
iterare cleanup refactor-abc12345 -y  # Specific run
```

## Configuration

### Project Structure

After running `iterare init`, your project will contain:

```
.iterare/
├── config.toml               # Main configuration
├── Dockerfile                # Custom Docker image (optional)
└── prompts/                  # Prompt files
    └── example-prompt.md

workspaces/                   # Git worktrees (gitignored)
```

### Config File (`.iterare/config.toml`)

```toml
[docker]
image = "iterare-llm:latest"

[session]
shell = "/bin/bash"

[claude]
credentials_path = "~/.config/iterare"

[firewall]
# Additional domains to allow through the firewall.
# Default domains (Anthropic API, GitHub, npm) are always included.
allowed_domains = [
    "pypi.org",
    "files.pythonhosted.org",
]
```

### Prompt Files

Prompts are markdown files with optional YAML frontmatter:

```markdown
---
workspace: my-feature
branch: main
---

# Task Description

Implement feature X by doing Y and Z.
```

Frontmatter fields:
- **workspace** -- Worktree directory name (defaults to prompt filename)
- **branch** -- Base branch for the worktree (defaults to current branch)

### Environment Variables

Pass host environment variables to the container with `--env`:

```bash
export PIP_INDEX_URL="https://pypi.company.internal/simple"
iterare execute install-deps --env PIP_INDEX_URL
```

The flag accepts the variable *name* and reads the value from your shell. If a variable is not set,
execution fails with an error.

### Network Security

The container runs behind a whitelist-based firewall using iptables:

- All outbound traffic is blocked by default
- Only whitelisted domains are allowed (resolved to IPs via DNS)
- Default whitelist includes `api.anthropic.com`, GitHub APIs, npm registry
- Additional domains are configured in `config.toml`

This prevents the autonomous agent from exfiltrating code or downloading malicious packages from unapproved sources.

### Execution Flow

1. Load configuration from `.iterare/config.toml`
2. Parse prompt file (extract frontmatter metadata)
3. Create git worktree on a new branch
4. Write `.claude-auto-config.json` and `.claude-prompt.md` to worktree
5. Launch Docker container with worktree mounted at `/workspace`
6. Container initializes firewall, then runs Claude Code autonomously
7. Monitor via `iterare log -f`
8. Merge results with `iterare merge`, clean up with `iterare cleanup`

## Development

```bash
make sync       # Install dependencies
make test       # Run tests (289 tests)
make coverage   # Run tests with coverage report (100% coverage)
make lint       # Check code style
make format     # Auto-format code
```

## Troubleshooting

### Docker image not found

Build the images first:

```bash
make build-base
make build
```

### Container already running

```bash
docker stop it-<run-name>
docker rm it-<run-name>
```

### Credentials not found

Run the credentials command to authenticate:

```bash
iterare credentials
```

### Network blocked in container

Add the required domain to your `config.toml`:

```toml
[firewall]
allowed_domains = ["example.com"]
```
