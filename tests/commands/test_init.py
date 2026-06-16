"""Tests for init command."""

from unittest.mock import patch

import pytest
from typer.testing import CliRunner

from iterare_llm.commands.init import _update_gitignore, init_project
from iterare_llm.config import create_global_config
from iterare_llm.main import app

runner = CliRunner()


class TestInitProject:
    def test_creates_structure(self, tmp_path):
        init_project(tmp_path)

        assert (tmp_path / ".iterare").is_dir()
        assert (tmp_path / ".iterare" / "prompts").is_dir()
        assert (tmp_path / "workspaces").is_dir()
        assert (tmp_path / ".iterare" / "Dockerfile").is_file()
        assert (tmp_path / ".iterare" / "config.toml").is_file()
        assert (tmp_path / ".iterare" / "prompts" / "example-prompt.md").is_file()

    def test_already_exists_without_force(self, tmp_path):
        (tmp_path / ".iterare").mkdir()

        with pytest.raises(FileExistsError):
            init_project(tmp_path)

    def test_force_overwrites(self, tmp_path):
        (tmp_path / ".iterare").mkdir()

        init_project(tmp_path, force=True)

        assert (tmp_path / ".iterare" / "config.toml").is_file()

    @patch(
        "iterare_llm.commands.init.Path.mkdir", side_effect=PermissionError("denied")
    )
    def test_permission_error(self, _, tmp_path):
        with pytest.raises(PermissionError, match="Permission denied"):
            init_project(tmp_path)

    @patch("iterare_llm.commands.init.Path.mkdir", side_effect=OSError("disk full"))
    def test_os_error(self, _, tmp_path):
        with pytest.raises(OSError, match="Failed to initialize project"):
            init_project(tmp_path, force=True)

    def test_project_config_is_minimal(self, tmp_path):
        init_project(tmp_path)

        content = (tmp_path / ".iterare" / "config.toml").read_text()
        # The project file only documents inheritance; it carries no active
        # (uncommented) settings.
        assert "inherits all settings from the global config" in content
        active_lines = [
            line
            for line in content.splitlines()
            if line.strip() and not line.lstrip().startswith("#")
        ]
        assert active_lines == []


class TestGlobalConfig:
    def test_init_creates_global_when_missing(self, tmp_path, isolate_global_config):
        created = init_project(tmp_path)

        assert created is True
        assert isolate_global_config.is_file()
        content = isolate_global_config.read_text()
        assert "[mounts]" in content
        assert "SOURCE:TARGET" in content

    def test_init_does_not_overwrite_existing_global(
        self, tmp_path, isolate_global_config
    ):
        isolate_global_config.parent.mkdir(parents=True, exist_ok=True)
        isolate_global_config.write_text("# user edits\n")

        created = init_project(tmp_path)

        assert created is False
        assert isolate_global_config.read_text() == "# user edits\n"

    def test_force_does_not_overwrite_existing_global(
        self, tmp_path, isolate_global_config
    ):
        (tmp_path / ".iterare").mkdir()
        isolate_global_config.parent.mkdir(parents=True, exist_ok=True)
        isolate_global_config.write_text("# user edits\n")

        created = init_project(tmp_path, force=True)

        assert created is False
        assert isolate_global_config.read_text() == "# user edits\n"

    def test_create_global_config_is_idempotent(self, isolate_global_config):
        assert create_global_config() is True
        assert create_global_config() is False


class TestUpdateGitignore:
    def test_creates_if_missing(self, tmp_path):
        _update_gitignore(tmp_path)

        content = (tmp_path / ".gitignore").read_text()
        assert "workspaces/" in content

    def test_appends_to_existing(self, tmp_path):
        (tmp_path / ".gitignore").write_text("node_modules/\n")

        _update_gitignore(tmp_path)

        content = (tmp_path / ".gitignore").read_text()
        assert "node_modules/" in content
        assert "workspaces/" in content

    def test_idempotent(self, tmp_path):
        (tmp_path / ".gitignore").write_text("workspaces/\n")

        _update_gitignore(tmp_path)

        lines = (tmp_path / ".gitignore").read_text().splitlines()
        assert lines.count("workspaces/") == 1


class TestInitCommand:
    def test_success(self, tmp_path):
        result = runner.invoke(app, ["init", str(tmp_path)])

        assert result.exit_code == 0
        assert "Initialized iterare" in result.output

    def test_already_exists(self, tmp_path):
        (tmp_path / ".iterare").mkdir()

        result = runner.invoke(app, ["init", str(tmp_path)])

        assert result.exit_code == 1

    def test_force(self, tmp_path):
        (tmp_path / ".iterare").mkdir()

        result = runner.invoke(app, ["init", "--force", str(tmp_path)])

        assert result.exit_code == 0

    @patch(
        "iterare_llm.commands.init.init_project", side_effect=PermissionError("nope")
    )
    def test_permission_error(self, _, tmp_path):
        result = runner.invoke(app, ["init", str(tmp_path)])

        assert result.exit_code == 1
        assert "Error initializing project" in result.output

    @patch("iterare_llm.commands.init.init_project", side_effect=OSError("disk full"))
    def test_os_error(self, _, tmp_path):
        result = runner.invoke(app, ["init", str(tmp_path)])

        assert result.exit_code == 1
        assert "Error initializing project" in result.output

    @patch(
        "iterare_llm.commands.init.init_project", side_effect=RuntimeError("unexpected")
    )
    def test_unexpected_error(self, _, tmp_path):
        result = runner.invoke(app, ["init", str(tmp_path)])

        assert result.exit_code == 1
        assert "Error initializing project" in result.output
