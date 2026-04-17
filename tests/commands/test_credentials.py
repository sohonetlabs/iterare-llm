"""Tests for credentials command."""

import logging
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

from iterare_llm.commands.credentials import (
    build_credentials_docker_command,
    check_existing_credentials,
    credentials_temp_dir,
    extract_credentials,
)
from iterare_llm.exceptions import DockerError, ImageNotFoundError, IterareError
from iterare_llm.main import app

runner = CliRunner()


class TestCredentialsTempDir:
    @patch("iterare_llm.commands.credentials.get_tmp_dir")
    def test_creates_and_cleans_up(self, mock_tmp_dir, tmp_path):
        mock_tmp_dir.return_value = tmp_path

        with credentials_temp_dir() as temp_dir:
            assert temp_dir.is_dir()
            assert (temp_dir / ".claude").is_dir()
            assert (temp_dir / ".claude.json").read_text() == "{}"

        assert not temp_dir.exists()

    @patch(
        "iterare_llm.commands.credentials.shutil.rmtree", side_effect=OSError("busy")
    )
    @patch("iterare_llm.commands.credentials.get_tmp_dir")
    def test_cleanup_failure_logs_warning(self, mock_tmp_dir, _, tmp_path, caplog):
        mock_tmp_dir.return_value = tmp_path

        with caplog.at_level(logging.WARNING):
            with credentials_temp_dir() as temp_dir:
                pass

        assert "Failed to clean up" in caplog.text


class TestBuildCredentialsDockerCommand:
    def test_root_user(self, tmp_path):
        result = build_credentials_docker_command(
            "iterare-llm:latest", tmp_path, "root"
        )

        assert result == [
            "docker",
            "run",
            "-it",
            "--rm",
            "--entrypoint",
            "claude",
            "-v",
            f"{tmp_path / '.claude'}:/root/.claude:rw",
            "-v",
            f"{tmp_path / '.claude.json'}:/root/.claude.json:rw",
            "iterare-llm:latest",
        ]

    def test_non_root_user(self, tmp_path):
        result = build_credentials_docker_command(
            "iterare-llm:latest", tmp_path, "node"
        )

        assert result == [
            "docker",
            "run",
            "-it",
            "--rm",
            "--entrypoint",
            "claude",
            "-v",
            f"{tmp_path / '.claude'}:/home/node/.claude:rw",
            "-v",
            f"{tmp_path / '.claude.json'}:/home/node/.claude.json:rw",
            "iterare-llm:latest",
        ]


class TestExtractCredentials:
    @pytest.fixture
    def temp_dir_with_creds(self, tmp_path):
        temp_dir = tmp_path / "temp"
        temp_dir.mkdir()
        claude_dir = temp_dir / ".claude"
        claude_dir.mkdir()
        (claude_dir / ".credentials.json").write_text('{"token": "abc"}')
        (temp_dir / ".claude.json").write_text('{"session": "xyz"}')
        return temp_dir

    def test_copies_files(self, temp_dir_with_creds, tmp_path):
        dest = tmp_path / "dest"

        creds_path, config_path = extract_credentials(temp_dir_with_creds, dest)

        assert creds_path.read_text() == '{"token": "abc"}'
        assert config_path.read_text() == '{"session": "xyz"}'

    def test_missing_credentials_file(self, tmp_path):
        temp_dir = tmp_path / "temp"
        temp_dir.mkdir()
        (temp_dir / ".claude").mkdir()

        with pytest.raises(FileNotFoundError, match="Login was not completed"):
            extract_credentials(temp_dir, tmp_path / "dest")

    def test_empty_claude_json(self, tmp_path):
        temp_dir = tmp_path / "temp"
        temp_dir.mkdir()
        claude_dir = temp_dir / ".claude"
        claude_dir.mkdir()
        (claude_dir / ".credentials.json").write_text('{"token": "abc"}')
        (temp_dir / ".claude.json").write_text("{}")

        with pytest.raises(FileNotFoundError, match="Login was not completed"):
            extract_credentials(temp_dir, tmp_path / "dest")


class TestCheckExistingCredentials:
    def test_both_exist(self, credentials_dir):
        assert check_existing_credentials(credentials_dir) is True

    def test_missing_credentials(self, tmp_path):
        (tmp_path / ".claude.json").write_text("{}")

        assert check_existing_credentials(tmp_path) is False

    def test_missing_config(self, tmp_path):
        (tmp_path / ".credentials.json").write_text("{}")

        assert check_existing_credentials(tmp_path) is False


class TestCredentialsCommand:
    @pytest.fixture(autouse=True)
    def setup_patches(self, tmp_path):
        self.config_dir = tmp_path / "config"
        self.config_dir.mkdir()

        @contextmanager
        def fake_temp_dir():
            d = tmp_path / "temp"
            d.mkdir(exist_ok=True)
            (d / ".claude").mkdir(exist_ok=True)
            (d / ".claude.json").write_text("{}")
            yield d

        self.patches = [
            patch(
                "iterare_llm.commands.credentials.get_app_config_dir",
                return_value=self.config_dir,
            ),
            patch(
                "iterare_llm.commands.credentials.check_existing_credentials",
                return_value=False,
            ),
            patch(
                "iterare_llm.commands.credentials.get_docker_client",
                return_value=MagicMock(),
            ),
            patch("iterare_llm.commands.credentials.ensure_image"),
            patch(
                "iterare_llm.commands.credentials.get_image_user", return_value="node"
            ),
            patch(
                "iterare_llm.commands.credentials.credentials_temp_dir",
                side_effect=fake_temp_dir,
            ),
            patch(
                "iterare_llm.commands.credentials.subprocess.run",
                return_value=MagicMock(returncode=0),
            ),
            patch(
                "iterare_llm.commands.credentials.extract_credentials",
                return_value=(
                    self.config_dir / ".credentials.json",
                    self.config_dir / ".claude.json",
                ),
            ),
        ]
        self.mocks = {}
        for p in self.patches:
            mock = p.start()
            self.mocks[p.attribute] = mock
        yield
        for p in self.patches:
            p.stop()

    def test_success(self):
        result = runner.invoke(app, ["credentials"])

        assert result.exit_code == 0
        assert "Credentials saved successfully" in result.output

    def test_existing_credentials_without_force(self):
        self.mocks["check_existing_credentials"].return_value = True

        result = runner.invoke(app, ["credentials"])

        assert result.exit_code == 0
        assert "Credentials already exist" in result.output

    def test_image_not_found(self):
        self.mocks["ensure_image"].side_effect = ImageNotFoundError(
            "not found locally or in registry"
        )

        result = runner.invoke(app, ["credentials"])

        assert result.exit_code == 1
        assert "not found" in result.output

    def test_docker_error(self):
        self.mocks["get_docker_client"].side_effect = DockerError("connection refused")

        result = runner.invoke(app, ["credentials"])

        assert result.exit_code == 1

    def test_file_not_found(self):
        self.mocks["extract_credentials"].side_effect = FileNotFoundError(
            "Login was not completed"
        )

        result = runner.invoke(app, ["credentials"])

        assert result.exit_code == 1
        assert "Login was not completed" in result.output

    def test_iterare_error(self):
        self.mocks["get_docker_client"].side_effect = IterareError("bad")

        result = runner.invoke(app, ["credentials"])

        assert result.exit_code == 1

    def test_unexpected_error(self):
        self.mocks["get_docker_client"].side_effect = RuntimeError("boom")

        result = runner.invoke(app, ["credentials"])

        assert result.exit_code == 1
        assert "Unexpected error" in result.output

    def test_keyboard_interrupt(self):
        self.mocks["run"].side_effect = KeyboardInterrupt()

        result = runner.invoke(app, ["credentials"])

        assert result.exit_code == 130
