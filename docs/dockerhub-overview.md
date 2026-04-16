# Iterare

Automated, isolated execution of Claude Code prompts in firewall-restricted Docker containers.

`iterare` creates git worktrees, launches containerised Claude Code instances with autonomous permissions, and maintains safety through network firewalls and container isolation. This enables "agentic loops" where Claude Code can modify codebases without human confirmation while being restricted to whitelisted network access and mounted files.

> **Warning** — This does not fully protect from malicious code execution or data exfiltration. It simply raises the barriers to these things happening. Use at your own risk.

## How It Works

1. You write a prompt describing a task (e.g. "refactor auth to use JWT")
2. Iterare creates an isolated git worktree on a new branch
3. A Docker container launches with the worktree mounted at `/workspace`
4. An iptables-based firewall restricts outbound traffic to whitelisted domains only
5. Claude Code executes the prompt autonomously until completion
6. You review the changes, merge, and clean up

## Quick Start

Install the CLI tool and initialise your project:

```bash
pip install iterare-llm
iterare install
iterare credentials
cd /path/to/your/project
iterare init
```

### Interactive Mode

```bash
iterare interactive
```

### Autonomous Execution

```bash
# Create a prompt
cat > .iterare/prompts/refactor.md << 'EOF'
---
workspace: refactor-auth
branch: main
---

Refactor the authentication module to use JWT tokens.
EOF

# Execute, monitor, merge, clean up
iterare execute refactor
iterare log -f
iterare merge
iterare cleanup -y
```

## Image Architecture

This is a two-layer image:

| Layer | Image | Contents |
|-------|-------|----------|
| Base | `iterare-base` | Claude Code Node.js application |
| Runtime | `sohonet/iterare-llm` | `uv`, `jq`, firewall scripts, entrypoint |

At runtime, the container mounts your worktree and credentials, configures the firewall, then launches Claude Code.

## Network Security

The container runs behind a **whitelist-based firewall** using iptables and ipsets:

- All outbound traffic is **blocked by default**
- Only whitelisted domains are resolved and allowed
- Default whitelist: `api.anthropic.com`, GitHub APIs, npm registry, VS Code marketplace
- Additional domains configured via `config.toml`

This prevents the autonomous agent from exfiltrating code or downloading packages from unapproved sources.

## Configuration

Project configuration lives in `.iterare/config.toml`:

```toml
[docker]
image = "sohonet/iterare-llm:latest"

[firewall]
allowed_domains = [
    "pypi.org",
    "files.pythonhosted.org",
]
```

### Environment Variables

Pass host environment variables into the container:

```bash
iterare execute my-prompt --env PIP_INDEX_URL --env GITHUB_TOKEN
iterare interactive --env PIP_INDEX_URL
```

## Commands

| Command | Description |
|---------|-------------|
| `iterare init` | Initialise a project |
| `iterare install` | Create global config directories |
| `iterare credentials` | Fetch Claude Code credentials |
| `iterare execute <prompt>` | Run a prompt autonomously |
| `iterare interactive` | Launch an interactive session |
| `iterare log [-f]` | View execution logs |
| `iterare list` | List execution runs |
| `iterare merge` | Merge worktree branch back |
| `iterare cleanup` | Remove worktree and branch |

## Links

- **Source**: [github.com/sohonetlabs/iterare-llm](https://github.com/sohonetlabs/iterare-llm)
- **PyPI**: [pypi.org/project/iterare-llm](https://pypi.org/project/iterare-llm/)
- **Issues**: [github.com/sohonetlabs/iterare-llm/issues](https://github.com/sohonetlabs/iterare-llm/issues)
