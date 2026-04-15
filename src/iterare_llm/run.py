"""Run name generation and management for iterare."""

import hashlib
import json
import time
from pathlib import Path

from iterare_llm.git import worktree_exists
from iterare_llm.logging import get_logger
from iterare_llm.paths import get_app_cache_dir

logger = get_logger(__name__)

# Length of hash suffix for run names
HASH_LENGTH = 8


def generate_run_name(prompt_name: str) -> str:
    """
    Generate a unique run name based on prompt name and timestamp.

    The run name consists of the prompt name with a hash of the timestamp
    appended with a dash. This ensures each run is unique even when using
    the same prompt multiple times.

    Parameters
    ----------
    prompt_name : str
        Base name for the run (typically the prompt filename without extension)

    Returns
    -------
    str
        Unique run name in format: {prompt_name}-{hash}

    Examples
    --------
    >>> name = generate_run_name("refactor-api")
    >>> name.startswith("refactor-api-")
    True
    >>> len(name.split("-")[-1])  # Hash should be 8 characters
    8
    """
    # Get current timestamp
    timestamp = str(time.time())

    # Generate hash from timestamp
    hash_value = hashlib.sha256(timestamp.encode()).hexdigest()[:HASH_LENGTH]

    run_name = f"{prompt_name}-{hash_value}"
    logger.debug(f"Generated run name: {run_name}")

    return run_name


def get_runs_file(project_dir: Path) -> Path:
    """
    Get the runs metadata file path for a specific project.

    Each project has its own runs file identified by a hash of its path.
    This allows tracking runs separately for different projects.

    Parameters
    ----------
    project_dir : Path
        Project directory path

    Returns
    -------
    Path
        Path to the runs metadata file for this project

    Examples
    --------
    >>> project = Path("/path/to/project")
    >>> runs_file = get_runs_file(project)
    >>> runs_file.name.endswith('.json')
    True
    """
    cache_dir = get_app_cache_dir()
    runs_dir = cache_dir / "runs"
    runs_dir.mkdir(parents=True, exist_ok=True)

    # Create a unique filename for this project based on its path
    project_hash = hashlib.sha256(str(project_dir.resolve()).encode()).hexdigest()[:16]
    runs_file = runs_dir / f"runs-{project_hash}.json"

    logger.debug(f"Runs file for {project_dir}: {runs_file}")
    return runs_file


def load_runs_metadata(project_dir: Path) -> dict:
    """
    Load runs metadata for a project.

    Parameters
    ----------
    project_dir : Path
        Project directory path

    Returns
    -------
    dict
        Dictionary mapping run names to metadata

    Examples
    --------
    >>> metadata = load_runs_metadata(Path("/project"))
    >>> isinstance(metadata, dict)
    True
    """
    runs_file = get_runs_file(project_dir)

    if not runs_file.exists():
        logger.debug(f"No runs metadata file found at {runs_file}")
        return {}

    try:
        with open(runs_file, "r") as f:
            data = json.load(f)
        logger.debug(f"Loaded {len(data)} runs from metadata file")
        return data
    except (json.JSONDecodeError, OSError) as e:
        logger.warning(f"Failed to load runs metadata: {e}")
        return {}


def save_runs_metadata(project_dir: Path, metadata: dict) -> None:
    """
    Save runs metadata for a project.

    Parameters
    ----------
    project_dir : Path
        Project directory path
    metadata : dict
        Dictionary mapping run names to metadata

    Raises
    ------
    OSError
        If unable to write metadata file
    """
    runs_file = get_runs_file(project_dir)

    try:
        with open(runs_file, "w") as f:
            json.dump(metadata, f, indent=2)
        logger.debug(f"Saved {len(metadata)} runs to metadata file")
    except OSError as e:
        logger.error(f"Failed to save runs metadata: {e}")
        raise OSError(f"Failed to save runs metadata: {e}") from e


def register_run(project_dir: Path, run_name: str, prompt_name: str) -> None:
    """
    Register a new run in the cache.

    Parameters
    ----------
    project_dir : Path
        Project directory path
    run_name : str
        Unique run name
    prompt_name : str
        Original prompt name

    Examples
    --------
    >>> register_run(Path("/project"), "refactor-api-abc123", "refactor-api")
    """
    metadata = load_runs_metadata(project_dir)

    metadata[run_name] = {
        "prompt_name": prompt_name,
        "timestamp": time.time(),
        "project_dir": str(project_dir.resolve()),
    }

    save_runs_metadata(project_dir, metadata)
    logger.info(f"Registered run: {run_name}")


def list_runs(project_dir: Path) -> list[dict]:
    """
    List all runs for a project.

    Parameters
    ----------
    project_dir : Path
        Project directory path

    Returns
    -------
    list[dict]
        List of run metadata dictionaries, sorted by timestamp (newest first)

    Examples
    --------
    >>> runs = list_runs(Path("/project"))
    >>> isinstance(runs, list)
    True
    """
    metadata = load_runs_metadata(project_dir)

    runs = [{"run_name": name, **data} for name, data in metadata.items()]

    # Sort by timestamp, newest first
    runs.sort(key=lambda x: x.get("timestamp", 0), reverse=True)

    logger.debug(f"Found {len(runs)} runs for project")
    return runs


def list_runs_with_workspaces(project_dir: Path) -> list[str]:
    """
    List run IDs that still have existing workspaces.

    Parameters
    ----------
    project_dir : Path
        Project directory path

    Returns
    -------
    list[str]
        List of run names that have existing worktrees

    Examples
    --------
    >>> runs = list_runs_with_workspaces(Path("/project"))
    >>> isinstance(runs, list)
    True
    """
    metadata = load_runs_metadata(project_dir)

    # Filter runs that still have workspaces
    runs_with_workspaces = []
    for run_name in metadata.keys():
        if worktree_exists(project_dir, run_name):
            runs_with_workspaces.append(run_name)

    logger.debug(f"Found {len(runs_with_workspaces)} runs with existing workspaces")
    return runs_with_workspaces
