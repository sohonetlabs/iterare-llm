"""Tests for install command."""

from unittest.mock import patch

import pytest
from typer.testing import CliRunner

from iterare_llm.commands.install import create_app_directories
from iterare_llm.main import app

runner = CliRunner()


class TestCreateAppDirectories:

    @patch("iterare_llm.commands.install.get_tmp_dir")
    @patch("iterare_llm.commands.install.get_logs_dir")
    @patch("iterare_llm.commands.install.get_app_config_dir")
    def test_creates_directories(self, mock_config, mock_logs, mock_tmp, tmp_path):
        mock_config.return_value = tmp_path / "config"
        mock_logs.return_value = tmp_path / "logs"
        mock_tmp.return_value = tmp_path / "tmp"

        config_dir, logs_dir, tmp_dir = create_app_directories()

        assert config_dir.is_dir()
        assert logs_dir.is_dir()
        assert tmp_dir.is_dir()

    @patch("iterare_llm.commands.install.get_tmp_dir")
    @patch("iterare_llm.commands.install.get_logs_dir")
    @patch("iterare_llm.commands.install.get_app_config_dir")
    @patch("pathlib.Path.mkdir", side_effect=PermissionError("denied"))
    def test_permission_error(self, _, mock_config, mock_logs, mock_tmp, tmp_path):
        mock_config.return_value = tmp_path / "config"
        mock_logs.return_value = tmp_path / "logs"
        mock_tmp.return_value = tmp_path / "tmp"

        with pytest.raises(PermissionError, match="Permission denied"):
            create_app_directories()

    @patch("iterare_llm.commands.install.get_tmp_dir")
    @patch("iterare_llm.commands.install.get_logs_dir")
    @patch("iterare_llm.commands.install.get_app_config_dir")
    @patch("pathlib.Path.mkdir", side_effect=OSError("disk full"))
    def test_os_error(self, _, mock_config, mock_logs, mock_tmp, tmp_path):
        mock_config.return_value = tmp_path / "config"
        mock_logs.return_value = tmp_path / "logs"
        mock_tmp.return_value = tmp_path / "tmp"

        with pytest.raises(OSError, match="Failed to create application directories"):
            create_app_directories()


class TestInstallCommand:

    @patch("iterare_llm.commands.install.create_app_directories")
    def test_success(self, mock_create, tmp_path):
        mock_create.return_value = (
            tmp_path / "config",
            tmp_path / "logs",
            tmp_path / "tmp",
        )

        result = runner.invoke(app, ["install"])

        assert result.exit_code == 0
        assert "Installation complete" in result.output

    @patch("iterare_llm.commands.install.create_app_directories", side_effect=PermissionError("denied"))
    def test_permission_error(self, _):
        result = runner.invoke(app, ["install"])

        assert result.exit_code == 1

    @patch("iterare_llm.commands.install.create_app_directories", side_effect=OSError("disk full"))
    def test_os_error(self, _):
        result = runner.invoke(app, ["install"])

        assert result.exit_code == 1

    @patch("iterare_llm.commands.install.create_app_directories", side_effect=RuntimeError("unexpected"))
    def test_unexpected_error(self, _):
        result = runner.invoke(app, ["install"])

        assert result.exit_code == 1
