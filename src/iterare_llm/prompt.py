"""Prompt file parsing and resolution for iterare."""

import re
from dataclasses import dataclass
from pathlib import Path

import yaml

from iterare_llm.exceptions import PromptError, PromptNotFoundError
from iterare_llm.logging import get_logger

logger = get_logger(__name__)


@dataclass
class PromptMetadata:
    """Metadata from prompt frontmatter."""

    workspace: str | None = None
    branch: str | None = None


@dataclass
class Prompt:
    """Parsed prompt with metadata and content."""

    metadata: PromptMetadata
    content: str
    path: Path


def extract_frontmatter(content: str) -> tuple[dict | None, str]:
    """
    Extract YAML frontmatter from markdown content.

    Frontmatter must be at the start of the file, enclosed in --- markers.

    Parameters
    ----------
    content : str
        Full content of the prompt file

    Returns
    -------
    tuple[dict | None, str]
        Tuple of (frontmatter_dict, remaining_content).
        frontmatter_dict is None if no frontmatter found.

    Examples
    --------
    >>> content = "---\\nworkspace: test\\n---\\nPrompt content"
    >>> metadata, text = extract_frontmatter(content)
    >>> metadata
    {'workspace': 'test'}
    >>> text
    'Prompt content'
    """
    # Match frontmatter: --- at start, YAML content (possibly empty), closing ---
    # Pattern allows for empty frontmatter (no content between --- markers)
    pattern = r"^---\s*\n(.*?)\n?---\s*\n(.*)$"
    match = re.match(pattern, content, re.DOTALL)

    if not match:
        logger.debug("No frontmatter found in prompt")
        return None, content

    yaml_content = match.group(1).strip()
    remaining_content = match.group(2)

    logger.debug("Found frontmatter in prompt")
    # Return empty dict as frontmatter if it's truly empty (not None)
    return yaml_content if yaml_content else dict(), remaining_content


def parse_yaml_frontmatter(yaml_str: str) -> dict:
    """
    Parse YAML frontmatter string.

    Parameters
    ----------
    yaml_str : str
        YAML content to parse

    Returns
    -------
    dict
        Parsed YAML as dictionary

    Raises
    ------
    PromptError
        If YAML is malformed
    """
    try:
        data = yaml.safe_load(yaml_str)
        if data is None:
            return {}
        if not isinstance(data, dict):
            logger.warning("Frontmatter is not a dictionary, ignoring")
            return {}
        logger.debug(f"Parsed frontmatter with keys: {list(data.keys())}")
        return data
    except yaml.YAMLError as e:
        logger.warning(f"Invalid YAML in frontmatter: {e}")
        raise PromptError(f"Invalid YAML in frontmatter: {e}") from e


def is_prompt_name(value: str) -> bool:
    """
    Check if value is a prompt name vs. a file path.

    A prompt name:
    - Does not contain path separators
    - Does not have an extension

    Parameters
    ----------
    value : str
        Value to check

    Returns
    -------
    bool
        True if value looks like a name, False if it looks like a path

    Examples
    --------
    >>> is_prompt_name("example")
    True
    >>> is_prompt_name("example.md")
    False
    >>> is_prompt_name("path/to/example.md")
    False
    >>> is_prompt_name(".iterare/prompts/example.md")
    False
    """
    # Check for path separators
    if "/" in value or "\\" in value:
        return False

    # Check for file extension
    if "." in value:
        return False

    return True


def find_prompt_by_name(name: str, prompts_dir: Path) -> Path | None:
    """
    Find a prompt file by name in the prompts directory.

    Searches for files matching the name with .md extension.

    Parameters
    ----------
    name : str
        Prompt name (without extension)
    prompts_dir : Path
        Directory containing prompt files

    Returns
    -------
    Path | None
        Path to the prompt file, or None if not found

    Examples
    --------
    >>> prompts_dir = Path("/project/.iterare/prompts")
    >>> find_prompt_by_name("example", prompts_dir)
    Path('/project/.iterare/prompts/example.md')
    """
    if not prompts_dir.exists():
        logger.debug(f"Prompts directory does not exist: {prompts_dir}")
        return None

    # Look for exact match with .md extension
    prompt_path = prompts_dir / f"{name}.md"
    if prompt_path.exists():
        logger.debug(f"Found prompt by name: {prompt_path}")
        return prompt_path

    logger.debug(f"No prompt found with name: {name}")
    return None


def resolve_prompt_path(name_or_path: str, project_dir: Path) -> Path:
    """
    Resolve prompt name or path to absolute path.

    If value looks like a name (no path separators or extension),
    searches in .iterare/prompts/ directory.

    Parameters
    ----------
    name_or_path : str
        Prompt name or file path
    project_dir : Path
        Project root directory

    Returns
    -------
    Path
        Resolved absolute path to prompt file

    Raises
    ------
    PromptNotFoundError
        If prompt cannot be found
    FileNotFoundError
        If specified path doesn't exist

    Examples
    --------
    >>> resolve_prompt_path("example", Path("/project"))
    Path('/project/.iterare/prompts/example.md')
    >>> resolve_prompt_path(".iterare/prompts/task.md", Path("/project"))
    Path('/project/.iterare/prompts/task.md')
    """
    logger.debug(f"Resolving prompt: {name_or_path}")

    # Check if it's a name or a path
    if is_prompt_name(name_or_path):
        # Treat as name, search in prompts directory
        prompts_dir = project_dir / ".iterare" / "prompts"
        prompt_path = find_prompt_by_name(name_or_path, prompts_dir)

        if prompt_path is None:
            raise PromptNotFoundError(
                f"Prompt '{name_or_path}' not found in {prompts_dir}. "
                f"Available prompts: {', '.join(p.stem for p in list_prompts(project_dir))}"
            )

        logger.info(f"Resolved prompt name '{name_or_path}' to {prompt_path}")
        return prompt_path
    else:
        # Treat as path
        if Path(name_or_path).is_absolute():
            prompt_path = Path(name_or_path)
        else:
            prompt_path = (project_dir / name_or_path).resolve()

        if not prompt_path.exists():
            raise FileNotFoundError(f"Prompt file not found: {prompt_path}")

        logger.info(f"Resolved prompt path to {prompt_path}")
        return prompt_path


def list_prompts(project_dir: Path) -> list[Path]:
    """
    List all available prompts in the project.

    Parameters
    ----------
    project_dir : Path
        Project root directory

    Returns
    -------
    list[Path]
        List of prompt file paths

    Examples
    --------
    >>> list_prompts(Path("/project"))
    [Path('/project/.iterare/prompts/example.md'), ...]
    """
    prompts_dir = project_dir / ".iterare" / "prompts"

    if not prompts_dir.exists():
        logger.debug(f"Prompts directory does not exist: {prompts_dir}")
        return []

    prompts = sorted(prompts_dir.glob("*.md"))
    logger.debug(f"Found {len(prompts)} prompts in {prompts_dir}")
    return prompts


def parse_prompt_file(path: Path) -> Prompt:
    """
    Parse a prompt file with optional YAML frontmatter.

    Parameters
    ----------
    path : Path
        Path to the prompt file

    Returns
    -------
    Prompt
        Parsed prompt with metadata and content

    Raises
    ------
    FileNotFoundError
        If prompt file doesn't exist
    PermissionError
        If unable to read prompt file
    PromptError
        If YAML frontmatter is malformed

    Examples
    --------
    >>> prompt = parse_prompt_file(Path("example.md"))
    >>> prompt.content
    'Please refactor the code...'
    >>> prompt.metadata.workspace
    'custom-workspace'
    """
    logger.debug(f"Parsing prompt file: {path}")

    if not path.exists():
        raise FileNotFoundError(f"Prompt file not found: {path}")

    try:
        content = path.read_text()
    except PermissionError as e:
        logger.error(f"Permission denied reading prompt file: {path}")
        raise PermissionError(f"Cannot read prompt file: {path}") from e

    # Extract frontmatter
    frontmatter_yaml, prompt_content = extract_frontmatter(content)

    # Parse frontmatter if present
    metadata_dict = {}
    if frontmatter_yaml is not None:
        try:
            metadata_dict = parse_yaml_frontmatter(frontmatter_yaml)
        except PromptError:
            logger.warning("Failed to parse frontmatter, continuing without metadata")
            # Continue without metadata rather than failing

    # Build metadata object
    metadata = PromptMetadata(
        workspace=metadata_dict.get("workspace"),
        branch=metadata_dict.get("branch"),
    )

    prompt = Prompt(
        metadata=metadata,
        content=prompt_content.strip(),
        path=path,
    )

    logger.info(f"Successfully parsed prompt from {path}")
    return prompt


def get_workspace_name_from_prompt(prompt: Prompt) -> str:
    """
    Derive workspace name from prompt metadata or filename.

    Uses workspace field from frontmatter if present,
    otherwise derives from prompt filename.

    Parameters
    ----------
    prompt : Prompt
        Parsed prompt

    Returns
    -------
    str
        Workspace name to use

    Examples
    --------
    >>> prompt = Prompt(
    ...     metadata=PromptMetadata(workspace="custom"),
    ...     content="content",
    ...     path=Path("example.md")
    ... )
    >>> get_workspace_name_from_prompt(prompt)
    'custom'
    >>> prompt = Prompt(
    ...     metadata=PromptMetadata(workspace=None),
    ...     content="content",
    ...     path=Path("refactor-api.md")
    ... )
    >>> get_workspace_name_from_prompt(prompt)
    'refactor-api'
    """
    if prompt.metadata.workspace:
        workspace_name = prompt.metadata.workspace
        logger.debug(f"Using workspace name from frontmatter: {workspace_name}")
    else:
        # Derive from filename (without extension)
        workspace_name = prompt.path.stem
        logger.debug(f"Derived workspace name from filename: {workspace_name}")

    return workspace_name
