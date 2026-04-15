"""Shared test fixtures for iterare-llm."""

import subprocess
from pathlib import Path
from textwrap import dedent
from unittest.mock import MagicMock, patch

import pytest

from iterare_llm.config import (
    ClaudeConfig,
    Config,
    DEFAULT_DOCKER_IMAGE,
    DEFAULT_SHELL,
    DockerConfig,
    FirewallConfig,
    SessionConfig,
)
from iterare_llm.docker import ExecutionConfig
from iterare_llm.prompt import Prompt, PromptMetadata


@pytest.fixture
def project_dir(tmp_path):
    """Project directory with .iterare structure and valid config."""
    iterare_dir = tmp_path / ".iterare"
    iterare_dir.mkdir()
    prompts_dir = iterare_dir / "prompts"
    prompts_dir.mkdir()
    workspaces_dir = tmp_path / "workspaces"
    workspaces_dir.mkdir()

    config_toml = iterare_dir / "config.toml"
    config_toml.write_text(
        '[docker]\n'
        'image = "iterare-llm:latest"\n'
        "\n"
        "[session]\n"
        'shell = "/bin/bash"\n'
        "\n"
        "[claude]\n"
        f'credentials_path = "{tmp_path / "credentials"}"\n'
        "\n"
        "[firewall]\n"
        'allowed_domains = ["pypi.org"]\n'
    )

    creds_dir = tmp_path / "credentials"
    creds_dir.mkdir()
    (creds_dir / ".credentials.json").write_text('{"token": "test"}')
    (creds_dir / ".claude.json").write_text('{"session": "test"}')

    return tmp_path


@pytest.fixture
def credentials_dir(tmp_path):
    """Directory with test credential files."""
    creds_dir = tmp_path / "creds"
    creds_dir.mkdir()
    (creds_dir / ".credentials.json").write_text('{"token": "test"}')
    (creds_dir / ".claude.json").write_text('{"session": "test"}')
    return creds_dir


@pytest.fixture
def sample_config(credentials_dir):
    """Sample Config dataclass with valid defaults."""
    return Config(
        docker=DockerConfig(image=DEFAULT_DOCKER_IMAGE),
        session=SessionConfig(shell=DEFAULT_SHELL),
        claude=ClaudeConfig(credentials_path=str(credentials_dir)),
        firewall=FirewallConfig(allowed_domains=["pypi.org"]),
    )


@pytest.fixture
def sample_prompt(tmp_path):
    """Sample Prompt dataclass with metadata."""
    prompt_path = tmp_path / "test-prompt.md"
    prompt_path.write_text("Test prompt content")
    return Prompt(
        metadata=PromptMetadata(workspace="test-workspace", branch="main"),
        content="Test prompt content",
        path=prompt_path,
    )


@pytest.fixture
def sample_prompt_no_metadata(tmp_path):
    """Sample Prompt dataclass without metadata."""
    prompt_path = tmp_path / "my-task.md"
    prompt_path.write_text("Do the task")
    return Prompt(
        metadata=PromptMetadata(),
        content="Do the task",
        path=prompt_path,
    )


@pytest.fixture
def sample_execution_config(tmp_path):
    """Sample ExecutionConfig for docker tests."""
    worktree = tmp_path / "worktree"
    worktree.mkdir()
    creds = tmp_path / "creds"
    creds.mkdir()
    config_file = creds / ".claude.json"
    config_file.write_text("{}")

    return ExecutionConfig(
        image_name="iterare-llm:latest",
        worktree_path=worktree,
        workspace_name="test-run-abc123",
        claude_credentials_path=creds,
        claude_config_file=config_file,
        prompt_content="Do the thing",
        allowed_domains=["pypi.org", "example.com"],
    )


# ---------------------------------------------------------------------------
# Boundary mocks
#
# These seal off the real subprocess / Docker SDK so nothing hits the OS.
# In git module tests we inspect the exact subprocess args submitted.
# In command-level tests the same mock is active but assertions focus on
# the higher-level function behaviour, not the subprocess args.
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_subprocess_run():
    """Mock subprocess.run in the git module (the git boundary)."""
    with patch("iterare_llm.git.subprocess.run") as mock_run:
        mock_result = MagicMock(spec=subprocess.CompletedProcess)
        mock_result.stdout = ""
        mock_result.stderr = ""
        mock_result.returncode = 0
        mock_run.return_value = mock_result
        yield mock_run


class FakeGit:
    """Callable that simulates git subprocess responses.

    Dispatches on the git subcommand and returns sensible defaults.
    Tests can modify ``worktree_paths`` and ``current_branch`` to
    configure the simulated repo state.
    """

    def __init__(self):
        self.worktree_paths = ["/project", "/project/workspaces/task-1"]
        self.current_branch = "main"
        self.is_repo = True
        self.branches = {"main", "task-1"}

    def __call__(self, cmd, **kwargs):
        result = subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

        if "rev-parse" in cmd and "--git-dir" in cmd:
            if not self.is_repo:
                raise subprocess.CalledProcessError(
                    128, cmd, stderr="fatal: not a git repository"
                )
            result.stdout = ".git\n"
        elif "rev-parse" in cmd and "--verify" in cmd:
            branch_name = cmd[-1]
            if branch_name not in self.branches:
                raise subprocess.CalledProcessError(
                    128, cmd, stderr=f"fatal: Needed a single revision"
                )
            result.stdout = "abc123\n"
        elif "worktree" in cmd and "list" in cmd:
            blocks = []
            for p in self.worktree_paths:
                blocks.append(dedent(f"""\
                    worktree {p}
                    HEAD abc123
                    branch refs/heads/main
                """).strip())
            result.stdout = "\n".join(blocks)
        elif "branch" in cmd and "--show-current" in cmd:
            result.stdout = f"{self.current_branch}\n"

        return result


@pytest.fixture
def mock_git(mock_subprocess_run):
    """Mock subprocess configured with FakeGit defaults.

    Returns the FakeGit instance so tests can adjust state
    (e.g. ``mock_git.current_branch = "dev"``).
    """
    git = FakeGit()
    mock_subprocess_run.side_effect = git
    return git


@pytest.fixture
def mock_docker_client():
    """Bare mock Docker client (the docker SDK boundary).

    Patches docker.from_env so get_docker_client() returns this mock
    instead of connecting to a real daemon.
    """
    client = MagicMock()
    client.ping.return_value = True
    with patch("iterare_llm.docker.docker.from_env", return_value=client):
        yield client
