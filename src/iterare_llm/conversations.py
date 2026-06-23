"""Discovery and resumption of persisted Claude Code conversations.

Claude Code writes each conversation as a `<session-id>.jsonl` transcript under
its projects directory. iterare bind-mounts a per-project store into that
location (see `paths.get_conversations_dir`) so transcripts survive container
teardown. This module reads that host store to list conversations, drive shell
autocomplete, and validate `--continue` / `--resume` requests before launch.
"""

import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from iterare_llm.exceptions import (
    ConversationNotFoundError,
    NoConversationsError,
)
from iterare_llm.logging import get_logger
from iterare_llm.paths import get_conversations_dir

logger = get_logger(__name__)

# Cap on transcript lines scanned for metadata; the summary, first user message
# and git branch all appear near the top, so unbounded reads are wasteful.
MAX_METADATA_LINES = 200

# Width of the truncated description shown in listings and autocomplete help.
DESCRIPTION_WIDTH = 60


@dataclass
class Conversation:
    """
    Metadata for a single persisted Claude Code conversation.

    Attributes
    ----------
    session_id : str
        Conversation/session UUID (the transcript filename stem). This is the
        value passed to `claude --resume`.
    description : str
        Human-readable label: the conversation summary if present, otherwise
        the first user message. Empty when neither could be read.
    git_branch : str
        Git branch recorded in the transcript, if any.
    modified : float
        Transcript file modification time (epoch seconds), used for ordering.
    """

    session_id: str
    description: str
    git_branch: str
    modified: float

    def short_description(self) -> str:
        """Return the description truncated to `DESCRIPTION_WIDTH` characters."""
        text = " ".join(self.description.split())
        if len(text) <= DESCRIPTION_WIDTH:
            return text
        return text[: DESCRIPTION_WIDTH - 1] + "…"

    def modified_display(self) -> str:
        """Return the modification time formatted for display."""
        return datetime.fromtimestamp(self.modified).strftime("%Y-%m-%d %H:%M")

    def completion_help(self) -> str:
        """Return a one-line label for shell autocomplete help text."""
        parts = [self.modified_display()]
        if self.git_branch:
            parts.append(self.git_branch)
        description = self.short_description()
        if description:
            parts.append(description)
        return " · ".join(parts)


def extract_message_text(message: dict) -> str:
    """Pull the plain-text portion of a transcript message, if any."""
    content = message.get("content")
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        texts = [
            part.get("text", "")
            for part in content
            if isinstance(part, dict) and part.get("type") == "text"
        ]
        return " ".join(text for text in texts if text).strip()
    return ""


def _parse_conversation_file(path: Path) -> Conversation:
    """
    Read a single transcript into a `Conversation`.

    Parsing is deliberately defensive: unreadable files (e.g. container-written
    transcripts owned by a different uid) and malformed lines degrade to the
    bare session id rather than raising, so listings never crash.

    Parameters
    ----------
    path : Path
        Path to the `.jsonl` transcript

    Returns
    -------
    Conversation
        Parsed metadata, with empty fields where data was unavailable
    """
    session_id = path.stem
    summary = ""
    first_message = ""
    git_branch = ""

    try:
        with path.open(encoding="utf-8") as handle:
            for index, line in enumerate(handle):
                if index >= MAX_METADATA_LINES:
                    break
                try:
                    entry = json.loads(line)
                except json.JSONDecodeError:
                    continue

                if not isinstance(entry, dict):
                    continue

                if not summary and entry.get("type") == "summary":
                    summary = str(entry.get("summary", "")).strip()
                if not git_branch and entry.get("gitBranch"):
                    git_branch = str(entry["gitBranch"])
                if not first_message and entry.get("type") == "user":
                    first_message = extract_message_text(entry.get("message", {}))

                if summary and first_message and git_branch:
                    break
    except OSError as error:
        logger.debug(f"Could not read conversation '{path}': {error}")

    try:
        modified = path.stat().st_mtime
    except OSError:
        modified = 0.0

    return Conversation(
        session_id=session_id,
        description=summary or first_message,
        git_branch=git_branch,
        modified=modified,
    )


def list_conversations(project_dir: Path) -> list[Conversation]:
    """
    List persisted conversations for a project, newest first.

    Parameters
    ----------
    project_dir : Path
        Project directory whose conversation store is read

    Returns
    -------
    list[Conversation]
        Conversations sorted by transcript modification time, newest first.
        Empty when the store does not exist or holds no transcripts.
    """
    conversations_dir = get_conversations_dir(project_dir)
    if not conversations_dir.is_dir():
        logger.debug(f"No conversation store at {conversations_dir}")
        return []

    conversations = [
        _parse_conversation_file(path)
        for path in conversations_dir.glob("*.jsonl")
        if path.is_file()
    ]
    conversations.sort(key=lambda conversation: conversation.modified, reverse=True)
    logger.debug(f"Found {len(conversations)} conversation(s) for {project_dir}")
    return conversations


def conversation_autocomplete(incomplete: str) -> list[tuple[str, str]]:
    """
    Autocomplete callback for `--resume` session ids.

    Returns `(session_id, help)` tuples so the shell shows a readable label
    (time, branch, first message) alongside each id. Never raises: completion
    callbacks must stay silent on failure.

    Parameters
    ----------
    incomplete : str
        Partial session id typed by the user

    Returns
    -------
    list[tuple[str, str]]
        Matching session ids paired with their help label
    """
    try:
        conversations = list_conversations(Path.cwd())
        return [
            (conversation.session_id, conversation.completion_help())
            for conversation in conversations
            if not incomplete or conversation.session_id.startswith(incomplete)
        ]
    except Exception:
        return []


def resolve_continue_or_resume(
    project_dir: Path,
    continue_conversation: bool,
    resume_session_id: str | None,
) -> None:
    """
    Validate a `--continue` / `--resume` request against the project's store.

    Catches the common failure modes before a container is launched so the user
    gets a clear host-side error instead of an opaque in-container one.

    Parameters
    ----------
    project_dir : Path
        Project directory whose conversation store is checked
    continue_conversation : bool
        Whether `--continue` was requested
    resume_session_id : str | None
        Session id requested via `--resume`, if any

    Raises
    ------
    NoConversationsError
        If a continue/resume was requested but the store is empty
    ConversationNotFoundError
        If `--resume <id>` names a session not present in the store
    """
    if not (conversations := list_conversations(project_dir)):
        raise NoConversationsError(
            "No persisted conversations found for this project. "
            "Run a session first, then continue or resume it."
        )

    if resume_session_id and not any(
        conversation.session_id == resume_session_id for conversation in conversations
    ):
        raise ConversationNotFoundError(
            f"Conversation '{resume_session_id}' not found for this project. "
            "List available conversations with: iterare conversations"
        )
