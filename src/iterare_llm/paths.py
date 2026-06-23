"""Centralized path management for iterare application directories."""

import hashlib
from pathlib import Path

from platformdirs import user_cache_dir, user_config_dir, user_data_dir

from iterare_llm.logging import get_logger

logger = get_logger(__name__)

# Length of the project-path hash used to namespace per-project cache dirs.
PROJECT_HASH_LENGTH = 16


def get_app_config_dir() -> Path:
    """
    Get the application config directory.

    Returns
    -------
    Path
        Application config directory path

    Examples
    --------
    >>> config_dir = get_app_config_dir()
    >>> config_dir.name
    'iterare'
    """
    config_dir = Path(user_config_dir("iterare", ensure_exists=False))
    logger.debug(f"Application config directory: {config_dir}")
    return config_dir


def get_app_cache_dir() -> Path:
    """
    Get the application cache directory.

    Returns
    -------
    Path
        Application cache directory path

    Examples
    --------
    >>> cache_dir = get_app_cache_dir()
    >>> cache_dir.name
    'iterare'
    """
    cache_dir = Path(user_cache_dir("iterare", ensure_exists=False))
    logger.debug(f"Application cache directory: {cache_dir}")
    return cache_dir


def get_app_data_dir() -> Path:
    """
    Get the application data directory.

    Returns
    -------
    Path
        Application data directory path

    Examples
    --------
    >>> data_dir = get_app_data_dir()
    >>> 'iterare' in str(data_dir)
    True
    """
    data_dir = Path(user_data_dir("iterare", ensure_exists=False))
    logger.debug(f"Application data directory: {data_dir}")
    return data_dir


def get_logs_dir() -> Path:
    """
    Get the application logs directory.

    Uses user_data_dir as the base directory, which is the appropriate
    location for persistent application data like logs.

    Returns
    -------
    Path
        Application logs directory path

    Examples
    --------
    >>> logs_dir = get_logs_dir()
    >>> 'iterare' in str(logs_dir)
    True
    >>> logs_dir.name
    'logs'
    """
    data_dir = get_app_data_dir()
    logs_dir = data_dir / "logs"
    logger.debug(f"Application logs directory: {logs_dir}")
    return logs_dir


def get_tmp_dir() -> Path:
    """
    Get the application tmp directory.

    Returns
    -------
    Path
        Application tmp directory path

    Examples
    --------
    >>> tmp_dir = get_tmp_dir()
    >>> 'iterare' in str(tmp_dir)
    True
    """
    cache_dir = get_app_cache_dir()
    tmp_dir = cache_dir / "tmp"
    logger.debug(f"Application tmp directory: {tmp_dir}")
    return tmp_dir


def project_hash(project_dir: Path) -> str:
    """
    Hash a project directory to a stable identifier for cache namespacing.

    The same project always maps to the same hash, so per-project caches
    (runs metadata, conversation store) can be keyed off it.

    Parameters
    ----------
    project_dir : Path
        Project directory path

    Returns
    -------
    str
        Truncated hex digest of the resolved project path

    Examples
    --------
    >>> len(project_hash(Path("/project")))
    16
    """
    digest = hashlib.sha256(str(project_dir.resolve()).encode()).hexdigest()
    return digest[:PROJECT_HASH_LENGTH]


def get_conversations_dir(project_dir: Path) -> Path:
    """
    Get the per-project Claude conversation store directory.

    This host directory is bind-mounted into the container at the Claude Code
    projects path so transcripts persist across container teardown and can be
    resumed. Each project gets its own directory keyed by `project_hash`.

    Parameters
    ----------
    project_dir : Path
        Project directory path

    Returns
    -------
    Path
        Path to the conversation store for this project

    Examples
    --------
    >>> conversations_dir = get_conversations_dir(Path("/project"))
    >>> conversations_dir.parent.name
    'conversations'
    """
    cache_dir = get_app_cache_dir()
    conversations_dir = cache_dir / "conversations" / project_hash(project_dir)
    logger.debug(f"Conversation store for {project_dir}: {conversations_dir}")
    return conversations_dir


def get_log_file_path(run_name: str) -> Path:
    """
    Generate a log file path for a specific run.

    The log file is created in the application logs directory with the
    run name as the filename.

    Parameters
    ----------
    run_name : str
        Unique run name to namespace the log file

    Returns
    -------
    Path
        Path to the log file

    Examples
    --------
    >>> log_path = get_log_file_path("refactor-api-abc123")
    >>> log_path.name
    'refactor-api-abc123.log'
    >>> 'logs' in str(log_path)
    True
    """
    logger.debug(f"Generating log file path for run '{run_name}'")

    logs_dir = get_logs_dir()
    log_file = logs_dir / f"{run_name}.log"

    logger.debug(f"Generated log file path: {log_file}")
    return log_file
