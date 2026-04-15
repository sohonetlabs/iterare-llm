"""Git worktree management for iterare."""

import subprocess
from pathlib import Path

from iterare_llm.exceptions import GitError, NotGitRepositoryError, WorktreeExistsError
from iterare_llm.logging import get_logger

logger = get_logger(__name__)


def run_git_command(repo_path: Path, args: list[str]) -> str:
    """
    Run a git command in the specified repository.

    Parameters
    ----------
    repo_path : Path
        Path to the git repository
    args : list[str]
        Git command arguments (e.g., ['status', '--short'])

    Returns
    -------
    str
        Command output (stdout)

    Raises
    ------
    GitError
        If git command fails
    """
    cmd = ["git", "-C", str(repo_path)] + args
    logger.debug(f"Running git command: {' '.join(cmd)}")

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            check=True,
        )
        logger.debug(f"Git command succeeded: {result.stdout[:100]}")
        return result.stdout.strip()
    except subprocess.CalledProcessError as e:
        logger.error(f"Git command failed: {e.stderr}")
        raise GitError(
            f"Git command failed: {' '.join(args)}\nError: {e.stderr.strip()}"
        ) from e
    except FileNotFoundError as e:
        logger.error("Git executable not found")
        raise GitError("Git executable not found. Is git installed?") from e


def is_git_repository(path: Path) -> bool:
    """
    Check if path is a git repository.

    Parameters
    ----------
    path : Path
        Path to check

    Returns
    -------
    bool
        True if path is a git repository, False otherwise

    Examples
    --------
    >>> is_git_repository(Path("/path/to/repo"))
    True
    >>> is_git_repository(Path("/not/a/repo"))
    False
    """
    try:
        run_git_command(path, ["rev-parse", "--git-dir"])
        return True
    except GitError:
        return False


def get_current_branch(repo_path: Path) -> str:
    """
    Get the current git branch.

    Parameters
    ----------
    repo_path : Path
        Path to the git repository

    Returns
    -------
    str
        Name of the current branch

    Raises
    ------
    NotGitRepositoryError
        If path is not a git repository
    GitError
        If unable to determine current branch

    Examples
    --------
    >>> get_current_branch(Path("/path/to/repo"))
    'main'
    """
    if not is_git_repository(repo_path):
        raise NotGitRepositoryError(f"{repo_path} is not a git repository")

    logger.debug(f"Getting current branch for {repo_path}")
    branch = run_git_command(repo_path, ["branch", "--show-current"])
    logger.debug(f"Current branch: {branch}")
    return branch


def list_worktrees(repo_path: Path) -> list[str]:
    """
    List all worktrees for a repository.

    Parameters
    ----------
    repo_path : Path
        Path to the git repository

    Returns
    -------
    list[str]
        List of worktree paths

    Raises
    ------
    GitError
        If unable to list worktrees
    """
    logger.debug(f"Listing worktrees for {repo_path}")

    output = run_git_command(repo_path, ["worktree", "list", "--porcelain"])

    # Parse worktree list output
    # Format is:
    # worktree /path/to/worktree
    # HEAD <hash>
    # branch refs/heads/branch-name
    #
    # worktree /path/to/another
    # ...

    worktrees = []
    for line in output.split("\n"):
        if line.startswith("worktree "):
            worktree_path = line[len("worktree ") :]
            worktrees.append(worktree_path)

    logger.debug(f"Found {len(worktrees)} worktrees")
    return worktrees


def get_worktree_path(repo_path: Path, worktree_name: str) -> Path:
    """
    Calculate the path for a worktree.

    Worktrees are created in the workspaces/ directory adjacent to the repo.

    Parameters
    ----------
    repo_path : Path
        Path to the git repository
    worktree_name : str
        Name of the worktree

    Returns
    -------
    Path
        Absolute path where worktree will be created

    Examples
    --------
    >>> get_worktree_path(Path("/project"), "task-1")
    Path('/project/workspaces/task-1')
    """
    worktree_path = repo_path / "workspaces" / worktree_name
    logger.debug(f"Calculated worktree path: {worktree_path}")
    return worktree_path


def worktree_exists(repo_path: Path, worktree_name: str) -> bool:
    """
    Check if a worktree already exists.

    Parameters
    ----------
    repo_path : Path
        Path to the git repository
    worktree_name : str
        Name of the worktree to check

    Returns
    -------
    bool
        True if worktree exists, False otherwise

    Examples
    --------
    >>> worktree_exists(Path("/project"), "task-1")
    False
    """
    if not is_git_repository(repo_path):
        return False

    try:
        worktree_path = get_worktree_path(repo_path, worktree_name)
        existing_worktrees = list_worktrees(repo_path)

        exists = str(worktree_path) in existing_worktrees
        logger.debug(
            f"Worktree '{worktree_name}' {'exists' if exists else 'does not exist'}"
        )
        return exists
    except GitError:
        return False


def create_worktree(
    repo_path: Path, worktree_name: str, branch: str | None = None
) -> Path:
    """
    Create a git worktree with a new branch.

    Creates a new branch for the worktree based on the specified branch (or current
    branch). This avoids conflicts when the base branch is already checked out in
    another worktree. The new branch uses the worktree_name directly.

    Parameters
    ----------
    repo_path : Path
        Path to the git repository
    worktree_name : str
        Name for the new worktree
    branch : str | None, optional
        Base branch to create the worktree branch from. If None, uses current branch.

    Returns
    -------
    Path
        Path to the created worktree

    Raises
    ------
    NotGitRepositoryError
        If path is not a git repository
    WorktreeExistsError
        If worktree already exists
    GitError
        If unable to create worktree

    Examples
    --------
    >>> create_worktree(Path("/project"), "task-1")
    Path('/project/workspaces/task-1')
    >>> create_worktree(Path("/project"), "task-2", "feature/new")
    Path('/project/workspaces/task-2')
    """
    if not is_git_repository(repo_path):
        raise NotGitRepositoryError(f"{repo_path} is not a git repository")

    if worktree_exists(repo_path, worktree_name):
        raise WorktreeExistsError(
            f"Worktree '{worktree_name}' already exists. "
            "Use a different workspace name or remove the existing worktree."
        )

    worktree_path = get_worktree_path(repo_path, worktree_name)

    # Ensure workspaces directory exists
    workspaces_dir = repo_path / "workspaces"
    workspaces_dir.mkdir(exist_ok=True)
    logger.debug(f"Created workspaces directory: {workspaces_dir}")

    # Determine base branch to use
    if branch is None:
        base_branch = get_current_branch(repo_path)
        logger.debug(f"Using current branch as base: {base_branch}")
    else:
        base_branch = branch
        logger.debug(f"Using specified branch as base: {base_branch}")

    # Create a new branch for this worktree using the run name
    # This makes the branch name unique per run
    worktree_branch = worktree_name
    logger.debug(f"Creating new branch for worktree: {worktree_branch}")

    # Create worktree with new branch based on base_branch
    logger.info(
        f"Creating worktree '{worktree_name}' at {worktree_path} "
        f"(branch: {worktree_branch} based on {base_branch})"
    )
    run_git_command(
        repo_path,
        ["worktree", "add", "-b", worktree_branch, str(worktree_path), base_branch],
    )

    logger.info(f"Successfully created worktree at {worktree_path}")
    return worktree_path


def remove_worktree(repo_path: Path, worktree_name: str) -> None:
    """
    Remove a git worktree.

    Parameters
    ----------
    repo_path : Path
        Path to the git repository
    worktree_name : str
        Name of the worktree to remove

    Raises
    ------
    NotGitRepositoryError
        If path is not a git repository
    GitError
        If unable to remove worktree

    Examples
    --------
    >>> remove_worktree(Path("/project"), "task-1")
    """
    if not is_git_repository(repo_path):
        raise NotGitRepositoryError(f"{repo_path} is not a git repository")

    worktree_path = get_worktree_path(repo_path, worktree_name)

    if not worktree_exists(repo_path, worktree_name):
        logger.warning(f"Worktree '{worktree_name}' does not exist, nothing to remove")
        return

    logger.info(f"Removing worktree '{worktree_name}' at {worktree_path}")
    run_git_command(repo_path, ["worktree", "remove", str(worktree_path), "--force"])

    logger.info(f"Successfully removed worktree '{worktree_name}'")


def branch_exists(repo_path: Path, branch_name: str) -> bool:
    """
    Check if a git branch exists.

    Parameters
    ----------
    repo_path : Path
        Path to the git repository
    branch_name : str
        Name of the branch to check

    Returns
    -------
    bool
        True if branch exists, False otherwise

    Examples
    --------
    >>> branch_exists(Path("/project"), "feature-branch")
    True
    """
    try:
        run_git_command(repo_path, ["rev-parse", "--verify", branch_name])
        return True
    except Exception:
        return False


def remove_branch(repo_path: Path, branch_name: str) -> None:
    """
    Remove a git branch forcefully.

    Parameters
    ----------
    repo_path : Path
        Path to the git repository
    branch_name : str
        Name of the branch to remove
    """
    logger.info(f"Removing branch '{branch_name}'")
    run_git_command(repo_path, ["branch", "-D", branch_name])
    logger.info(f"Successfully removed branch '{branch_name}'")


def merge_branch(repo_path: Path, branch_name: str) -> None:
    """
    Merge a branch into the current branch.

    Parameters
    ----------
    repo_path : Path
        Path to the git repository
    branch_name : str
        Name of the branch to merge
    """
    logger.info(f"Merging branch '{branch_name}' into current branch")
    run_git_command(repo_path, ["merge", branch_name])
    logger.info(f"Successfully merged branch '{branch_name}'")
