"""Tests for git worktree management."""

import logging
import subprocess
from pathlib import Path
from unittest.mock import call

import pytest

from iterare_llm.exceptions import GitError, NotGitRepositoryError, WorktreeExistsError
from iterare_llm.git import (
    create_worktree,
    get_current_branch,
    get_worktree_path,
    is_git_repository,
    branch_exists,
    list_worktrees,
    merge_branch,
    remove_branch,
    remove_worktree,
    run_git_command,
    worktree_exists,
)


class TestRunGitCommand:

    def test_success(self, mock_subprocess_run):
        mock_subprocess_run.return_value.stdout = "output\n"

        result = run_git_command(Path("/repo"), ["status"])

        assert result == "output"
        assert mock_subprocess_run.call_args_list == [
            call(
                ["git", "-C", "/repo", "status"],
                capture_output=True,
                text=True,
                check=True,
            )
        ]

    def test_command_failure(self, mock_subprocess_run):
        mock_subprocess_run.side_effect = subprocess.CalledProcessError(
            1, "git", stderr="fatal: not a git repository"
        )

        with pytest.raises(GitError, match="Git command failed"):
            run_git_command(Path("/repo"), ["status"])

    def test_git_not_installed(self, mock_subprocess_run):
        mock_subprocess_run.side_effect = FileNotFoundError()

        with pytest.raises(GitError, match="Git executable not found"):
            run_git_command(Path("/repo"), ["status"])


class TestIsGitRepository:

    def test_is_repo(self, mock_git):
        result = is_git_repository(Path("/repo"))

        assert result is True

    def test_not_repo(self, mock_git):
        mock_git.is_repo = False

        result = is_git_repository(Path("/not-a-repo"))

        assert result is False


class TestGetCurrentBranch:

    def test_returns_branch_name(self, mock_git):
        result = get_current_branch(Path("/repo"))

        assert result == "main"

    def test_not_a_repo(self, mock_git):
        mock_git.is_repo = False

        with pytest.raises(NotGitRepositoryError):
            get_current_branch(Path("/not-a-repo"))


class TestListWorktrees:

    def test_parses_porcelain_output(self, mock_git):
        result = list_worktrees(Path("/project"))

        assert result == ["/project", "/project/workspaces/task-1"]

    def test_no_worktrees(self, mock_git):
        mock_git.worktree_paths = []

        result = list_worktrees(Path("/project"))

        assert result == []


def test_get_worktree_path():
    result = get_worktree_path(Path("/project"), "task-1")

    assert result == Path("/project/workspaces/task-1")


class TestWorktreeExists:

    def test_exists(self, mock_git):
        result = worktree_exists(Path("/project"), "task-1")

        assert result is True

    def test_does_not_exist(self, mock_git):
        result = worktree_exists(Path("/project"), "nonexistent")

        assert result is False

    def test_not_a_repo(self, mock_git):
        mock_git.is_repo = False

        result = worktree_exists(Path("/not-a-repo"), "task-1")

        assert result is False

    def test_git_error_during_list(self, mock_subprocess_run):
        success = subprocess.CompletedProcess(["git"], 0, stdout=".git\n", stderr="")
        mock_subprocess_run.side_effect = [
            success,
            subprocess.CalledProcessError(1, "git", stderr="git error"),
        ]

        result = worktree_exists(Path("/project"), "task-1")

        assert result is False


class TestCreateWorktree:

    def test_creates_worktree(self, tmp_path, mock_git):
        mock_git.worktree_paths = []

        result = create_worktree(tmp_path, "new-task")

        assert result == tmp_path / "workspaces" / "new-task"
        assert (tmp_path / "workspaces").is_dir()

    def test_with_explicit_branch(self, tmp_path, mock_git):
        mock_git.worktree_paths = []

        result = create_worktree(tmp_path, "new-task", branch="develop")

        assert result == tmp_path / "workspaces" / "new-task"

    def test_not_a_repo(self, tmp_path, mock_git):
        mock_git.is_repo = False

        with pytest.raises(NotGitRepositoryError):
            create_worktree(tmp_path, "new-task")

    def test_already_exists(self, tmp_path, mock_git):
        worktree_path = str(tmp_path / "workspaces" / "existing")
        mock_git.worktree_paths = [worktree_path]

        with pytest.raises(WorktreeExistsError):
            create_worktree(tmp_path, "existing")


class TestRemoveWorktree:

    def test_removes_existing(self, tmp_path, mock_git, mock_subprocess_run):
        worktree_path = str(tmp_path / "workspaces" / "task-1")
        mock_git.worktree_paths = [worktree_path]

        remove_worktree(tmp_path, "task-1")

        assert mock_subprocess_run.call_args_list[-1] == call(
            ["git", "-C", str(tmp_path), "worktree", "remove", worktree_path, "--force"],
            capture_output=True,
            text=True,
            check=True,
        )

    def test_nonexistent_is_noop(self, tmp_path, mock_git, caplog):
        mock_git.worktree_paths = []

        with caplog.at_level(logging.WARNING):
            remove_worktree(tmp_path, "nonexistent")

        assert "does not exist, nothing to remove" in caplog.text

    def test_not_a_repo(self, tmp_path, mock_git):
        mock_git.is_repo = False

        with pytest.raises(NotGitRepositoryError):
            remove_worktree(tmp_path, "task-1")


class TestBranchExists:

    def test_exists(self, mock_git):
        result = branch_exists(Path("/project"), "main")

        assert result is True

    def test_does_not_exist(self, mock_git):
        result = branch_exists(Path("/project"), "nonexistent")

        assert result is False


def test_remove_branch(mock_git, mock_subprocess_run):
    remove_branch(Path("/project"), "feature-branch")

    assert mock_subprocess_run.call_args_list[-1] == call(
        ["git", "-C", "/project", "branch", "-D", "feature-branch"],
        capture_output=True,
        text=True,
        check=True,
    )


def test_merge_branch(mock_git, mock_subprocess_run):
    merge_branch(Path("/project"), "feature-branch")

    assert mock_subprocess_run.call_args_list[-1] == call(
        ["git", "-C", "/project", "merge", "feature-branch"],
        capture_output=True,
        text=True,
        check=True,
    )
