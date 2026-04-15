"""Workspace preparation for iterare."""

import json
from pathlib import Path

from iterare_llm.logging import get_logger

logger = get_logger(__name__)


def generate_claude_config() -> dict:
    """
    Generate Claude Code configuration.

    Returns
    -------
    dict
        Claude Code configuration dictionary
    """
    config = {
        "dangerouslyDisableToolPermissions": True,
        "maxIterations": 50,
        "workingDirectory": "/workspace",
    }
    logger.debug("Generated Claude Code config")
    return config


def write_claude_config(worktree_path: Path, config: dict) -> None:
    """
    Write Claude Code configuration to worktree.

    Parameters
    ----------
    worktree_path : Path
        Path to the worktree
    config : dict
        Configuration dictionary

    Raises
    ------
    OSError
        If unable to write config file
    """
    config_path = worktree_path / ".claude-auto-config.json"
    logger.debug(f"Writing Claude Code config to {config_path}")

    try:
        config_path.write_text(json.dumps(config, indent=2))
        logger.debug("Successfully wrote Claude Code config")
    except OSError as e:
        logger.error(f"Failed to write config file: {e}")
        raise OSError(f"Failed to write config file {config_path}: {e}") from e


def write_prompt_file(worktree_path: Path, content: str) -> None:
    """
    Write prompt content to worktree.

    Parameters
    ----------
    worktree_path : Path
        Path to the worktree
    content : str
        Prompt content

    Raises
    ------
    OSError
        If unable to write prompt file
    """
    prompt_path = worktree_path / ".claude-prompt.md"
    logger.debug(f"Writing prompt to {prompt_path}")

    try:
        prompt_path.write_text(content)
        logger.debug("Successfully wrote prompt file")
    except OSError as e:
        logger.error(f"Failed to write prompt file: {e}")
        raise OSError(f"Failed to write prompt file {prompt_path}: {e}") from e


def prepare_workspace(worktree_path: Path, prompt_content: str) -> None:
    """
    Prepare workspace with configuration and prompt files.

    Creates .claude-auto-config.json and .claude-prompt.md in the worktree.

    Parameters
    ----------
    worktree_path : Path
        Path to the worktree
    prompt_content : str
        Content of the prompt to execute

    Raises
    ------
    OSError
        If unable to write files
    """
    logger.info(f"Preparing workspace at {worktree_path}")

    config = generate_claude_config()
    write_claude_config(worktree_path, config)
    write_prompt_file(worktree_path, prompt_content)

    logger.info("Successfully prepared workspace")
