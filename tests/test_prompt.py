"""Tests for prompt file parsing and resolution."""

from pathlib import Path

import pytest

from iterare_llm.exceptions import PromptError
from iterare_llm.exceptions import PromptNotFoundError
from iterare_llm.prompt import (
    extract_frontmatter,
    find_prompt_by_name,
    is_prompt_name,
    parse_yaml_frontmatter,
    get_workspace_name_from_prompt,
    list_prompts,
    parse_prompt_file,
    resolve_prompt_path,
)

TEST_FILES = Path(__file__).parent / "test_files"


class TestExtractFrontmatter:

    def test_with_frontmatter(self):
        content = (TEST_FILES / "prompt_with_frontmatter.md").read_text()

        frontmatter, remaining = extract_frontmatter(content)

        assert frontmatter == "workspace: my-task\nbranch: main"
        assert remaining.strip() == "Do the thing."

    def test_no_frontmatter(self):
        content = (TEST_FILES / "prompt_no_frontmatter.md").read_text()

        frontmatter, remaining = extract_frontmatter(content)

        assert frontmatter is None
        assert remaining == content

    def test_empty_frontmatter(self):
        content = (TEST_FILES / "prompt_empty_frontmatter.md").read_text()

        frontmatter, remaining = extract_frontmatter(content)

        assert frontmatter == {}
        assert remaining.strip() == "Content after empty frontmatter."


class TestParseYamlFrontmatter:

    def test_valid_yaml(self):
        result = parse_yaml_frontmatter("workspace: my-task\nbranch: main")

        assert result == {"workspace": "my-task", "branch": "main"}

    def test_empty_string(self):
        result = parse_yaml_frontmatter("")

        assert result == {}

    def test_non_dict_yaml(self):
        result = parse_yaml_frontmatter("- item1\n- item2")

        assert result == {}

    def test_malformed_yaml(self):
        with pytest.raises(PromptError, match="Invalid YAML"):
            parse_yaml_frontmatter("key: [unclosed")


class TestIsPromptName:

    @pytest.mark.parametrize("value", ["example", "refactor-api", "my_task"])
    def test_names(self, value):
        assert is_prompt_name(value) is True

    @pytest.mark.parametrize(
        "value",
        [
            "example.md",
            "path/to/example.md",
            ".iterare/prompts/example.md",
            "dir\\file.md",
        ],
    )
    def test_paths(self, value):
        assert is_prompt_name(value) is False


class TestFindPromptByName:

    def test_found(self, tmp_path):
        prompt_file = tmp_path / "my-task.md"
        prompt_file.write_text("content")

        result = find_prompt_by_name("my-task", tmp_path)

        assert result == prompt_file

    def test_not_found(self, tmp_path):
        result = find_prompt_by_name("nonexistent", tmp_path)

        assert result is None

    def test_missing_directory(self, tmp_path):
        result = find_prompt_by_name("anything", tmp_path / "nope")

        assert result is None


class TestResolvePromptPath:

    def test_resolve_by_name(self, project_dir):
        prompt_file = project_dir / ".iterare" / "prompts" / "my-task.md"
        prompt_file.write_text("content")

        result = resolve_prompt_path("my-task", project_dir)

        assert result == prompt_file

    def test_resolve_by_relative_path(self, project_dir):
        prompt_file = project_dir / ".iterare" / "prompts" / "task.md"
        prompt_file.write_text("content")

        result = resolve_prompt_path(".iterare/prompts/task.md", project_dir)

        assert result == prompt_file

    def test_resolve_by_absolute_path(self, tmp_path):
        prompt_file = tmp_path / "anywhere.md"
        prompt_file.write_text("content")

        result = resolve_prompt_path(str(prompt_file), tmp_path)

        assert result == prompt_file

    def test_name_not_found(self, project_dir):
        with pytest.raises(PromptNotFoundError):
            resolve_prompt_path("nonexistent", project_dir)

    def test_path_not_found(self, project_dir):
        with pytest.raises(FileNotFoundError):
            resolve_prompt_path(".iterare/prompts/nope.md", project_dir)


class TestListPrompts:

    def test_lists_md_files(self, project_dir):
        prompts_dir = project_dir / ".iterare" / "prompts"
        (prompts_dir / "alpha.md").write_text("a")
        (prompts_dir / "beta.md").write_text("b")

        result = list_prompts(project_dir)

        assert [p.name for p in result] == ["alpha.md", "beta.md"]

    def test_empty_prompts_dir(self, project_dir):
        result = list_prompts(project_dir)

        assert result == []

    def test_missing_prompts_dir(self, tmp_path):
        result = list_prompts(tmp_path)

        assert result == []


class TestParsePromptFile:

    def test_with_frontmatter(self):
        result = parse_prompt_file(TEST_FILES / "prompt_with_frontmatter.md")

        assert result.metadata.workspace == "my-task"
        assert result.metadata.branch == "main"
        assert result.content == "Do the thing."

    def test_no_frontmatter(self):
        result = parse_prompt_file(TEST_FILES / "prompt_no_frontmatter.md")

        assert result.metadata.workspace is None
        assert result.metadata.branch is None
        assert result.content == "Just a plain prompt with no frontmatter."

    def test_missing_file(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            parse_prompt_file(tmp_path / "nope.md")

    def test_permission_error(self, tmp_path):
        restricted = tmp_path / "noperm.md"
        restricted.write_text("content")
        restricted.chmod(0o000)

        with pytest.raises(PermissionError):
            parse_prompt_file(restricted)

        restricted.chmod(0o644)

    def test_bad_frontmatter_continues_without_metadata(self):
        result = parse_prompt_file(TEST_FILES / "prompt_bad_frontmatter.md")

        assert result.metadata.workspace is None
        assert result.metadata.branch is None
        assert result.content == "Content after bad frontmatter."


class TestGetWorkspaceNameFromPrompt:

    def test_uses_frontmatter_workspace(self, sample_prompt):
        result = get_workspace_name_from_prompt(sample_prompt)

        assert result == "test-workspace"

    def test_falls_back_to_filename(self, sample_prompt_no_metadata):
        result = get_workspace_name_from_prompt(sample_prompt_no_metadata)

        assert result == "my-task"
