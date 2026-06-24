"""Tests for centralized path management."""

from pathlib import Path
from unittest.mock import patch

from iterare_llm.paths import (
    get_app_cache_dir,
    get_app_config_dir,
    get_app_data_dir,
    get_conversations_dir,
    get_log_file_path,
    get_logs_dir,
    get_tmp_dir,
    project_hash,
)


class TestAppDirectories:
    @patch("iterare_llm.paths.user_config_dir", return_value="/mock/config/iterare")
    def test_config_dir(self, _):
        result = get_app_config_dir()

        assert result == Path("/mock/config/iterare")

    @patch("iterare_llm.paths.user_cache_dir", return_value="/mock/cache/iterare")
    def test_cache_dir(self, _):
        result = get_app_cache_dir()

        assert result == Path("/mock/cache/iterare")

    @patch("iterare_llm.paths.user_data_dir", return_value="/mock/data/iterare")
    def test_data_dir(self, _):
        result = get_app_data_dir()

        assert result == Path("/mock/data/iterare")


class TestDerivedDirectories:
    @patch("iterare_llm.paths.user_data_dir", return_value="/mock/data/iterare")
    def test_logs_dir(self, _):
        result = get_logs_dir()

        assert result == Path("/mock/data/iterare/logs")

    @patch("iterare_llm.paths.user_cache_dir", return_value="/mock/cache/iterare")
    def test_tmp_dir(self, _):
        result = get_tmp_dir()

        assert result == Path("/mock/cache/iterare/tmp")


class TestLogFilePath:
    @patch("iterare_llm.paths.user_data_dir", return_value="/mock/data/iterare")
    def test_format(self, _):
        result = get_log_file_path("refactor-api-abc123")

        assert result == Path("/mock/data/iterare/logs/refactor-api-abc123.log")


class TestProjectHash:
    def test_length(self, tmp_path):
        assert len(project_hash(tmp_path)) == 16

    def test_stable_for_same_path(self, tmp_path):
        assert project_hash(tmp_path) == project_hash(tmp_path)

    def test_differs_by_path(self, tmp_path):
        other = tmp_path / "other"
        other.mkdir()
        assert project_hash(tmp_path) != project_hash(other)


class TestConversationsDir:
    @patch("iterare_llm.paths.user_cache_dir", return_value="/mock/cache/iterare")
    def test_under_conversations_with_project_hash(self, _, tmp_path):
        result = get_conversations_dir(tmp_path)

        assert result.parent == Path("/mock/cache/iterare/conversations")
        assert result.name == project_hash(tmp_path)
