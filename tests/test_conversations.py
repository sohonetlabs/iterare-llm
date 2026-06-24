"""Tests for conversation discovery and resume validation."""

import json
import os
from unittest.mock import patch

import pytest

from iterare_llm.conversations import (
    Conversation,
    DESCRIPTION_WIDTH,
    extract_message_text,
    _parse_conversation_file,
    conversation_autocomplete,
    list_conversations,
    resolve_continue_or_resume,
)
from iterare_llm.exceptions import (
    ConversationNotFoundError,
    NoConversationsError,
)


def write_transcript(directory, session_id, lines, mtime=None):
    """Write a `.jsonl` transcript and optionally stamp its mtime."""
    path = directory / f"{session_id}.jsonl"
    path.write_text("\n".join(json.dumps(line) for line in lines) + "\n")
    if mtime is not None:
        os.utime(path, (mtime, mtime))
    return path


@pytest.fixture
def store(tmp_path):
    """Conversation store directory with `get_conversations_dir` pointed at it."""
    conversations_dir = tmp_path / "conversations"
    conversations_dir.mkdir()
    with patch(
        "iterare_llm.conversations.get_conversations_dir",
        return_value=conversations_dir,
    ):
        yield conversations_dir


class TestExtractMessageText:
    def test_string_content(self):
        assert extract_message_text({"content": "  hello  "}) == "hello"

    def test_list_content_joins_text_parts(self):
        message = {
            "content": [
                {"type": "text", "text": "first"},
                {"type": "tool_use", "name": "Bash"},
                {"type": "text", "text": "second"},
            ]
        }
        assert extract_message_text(message) == "first second"

    def test_list_content_without_text(self):
        message = {"content": [{"type": "tool_result", "content": "x"}]}
        assert extract_message_text(message) == ""

    def test_missing_content(self):
        assert extract_message_text({}) == ""


class TestParseConversationFile:
    def test_prefers_summary(self, tmp_path):
        path = write_transcript(
            tmp_path,
            "sess-1",
            [
                {"type": "summary", "summary": "Refactor the API"},
                {
                    "type": "user",
                    "message": {"content": "do the thing"},
                    "gitBranch": "main",
                },
            ],
        )

        conversation = _parse_conversation_file(path)

        assert conversation.session_id == "sess-1"
        assert conversation.description == "Refactor the API"
        assert conversation.git_branch == "main"

    def test_falls_back_to_first_user_message(self, tmp_path):
        path = write_transcript(
            tmp_path,
            "sess-2",
            [
                {"type": "mode", "mode": "default"},
                {
                    "type": "user",
                    "message": {"content": "first prompt"},
                    "gitBranch": "dev",
                },
                {"type": "user", "message": {"content": "second prompt"}},
            ],
        )

        conversation = _parse_conversation_file(path)

        assert conversation.description == "first prompt"
        assert conversation.git_branch == "dev"

    def test_tolerates_malformed_lines(self, tmp_path):
        path = tmp_path / "sess-3.jsonl"
        path.write_text(
            "not json\n"
            + json.dumps({"type": "user", "message": {"content": "ok"}})
            + "\n"
        )

        conversation = _parse_conversation_file(path)

        assert conversation.session_id == "sess-3"
        assert conversation.description == "ok"

    def test_empty_file_degrades_to_session_id(self, tmp_path):
        path = tmp_path / "sess-4.jsonl"
        path.touch()

        conversation = _parse_conversation_file(path)

        assert conversation.session_id == "sess-4"
        assert conversation.description == ""
        assert conversation.git_branch == ""

    def test_skips_non_dict_lines(self, tmp_path):
        path = write_transcript(
            tmp_path,
            "sess-5",
            [[1, 2], {"type": "user", "message": {"content": "real"}}],
        )

        conversation = _parse_conversation_file(path)

        assert conversation.description == "real"

    def test_stops_after_max_metadata_lines(self, tmp_path):
        # Metadata only on a line beyond the scan cap is never read.
        lines = [{"type": "noise"}] * 205
        lines.append({"type": "user", "message": {"content": "too late"}})
        path = write_transcript(tmp_path, "sess-6", lines)

        conversation = _parse_conversation_file(path)

        assert conversation.description == ""

    def test_unreadable_path_degrades(self, tmp_path):
        # A missing path makes both .open() and .stat() raise OSError.
        conversation = _parse_conversation_file(tmp_path / "gone.jsonl")

        assert conversation.session_id == "gone"
        assert conversation.description == ""
        assert conversation.modified == 0.0


class TestConversationDisplay:
    def test_short_description_truncates(self):
        conversation = Conversation("id", "x" * 100, "main", 0.0)

        assert conversation.short_description().endswith("…")
        assert len(conversation.short_description()) == DESCRIPTION_WIDTH

    def test_completion_help_includes_branch_and_description(self):
        conversation = Conversation("id", "do work", "feature", 0.0)

        help_text = conversation.completion_help()

        assert "feature" in help_text
        assert "do work" in help_text


class TestListConversations:
    def test_missing_store_returns_empty(self, tmp_path):
        with patch(
            "iterare_llm.conversations.get_conversations_dir",
            return_value=tmp_path / "absent",
        ):
            assert list_conversations(tmp_path) == []

    def test_sorted_newest_first(self, store, tmp_path):
        write_transcript(
            store, "old", [{"type": "user", "message": {"content": "old"}}], mtime=1000
        )
        write_transcript(
            store, "new", [{"type": "user", "message": {"content": "new"}}], mtime=2000
        )

        result = list_conversations(tmp_path)

        assert [c.session_id for c in result] == ["new", "old"]


class TestConversationAutocomplete:
    def test_filters_by_prefix(self):
        conversations = [
            Conversation("abc-1", "a", "main", 0.0),
            Conversation("xyz-2", "b", "main", 0.0),
        ]
        with patch(
            "iterare_llm.conversations.list_conversations",
            return_value=conversations,
        ):
            result = conversation_autocomplete("abc")

        assert result == [("abc-1", conversations[0].completion_help())]

    def test_no_prefix_returns_all(self):
        conversations = [Conversation("abc-1", "a", "main", 0.0)]
        with patch(
            "iterare_llm.conversations.list_conversations",
            return_value=conversations,
        ):
            result = conversation_autocomplete("")

        assert [session_id for session_id, _ in result] == ["abc-1"]

    def test_swallows_errors(self):
        with patch(
            "iterare_llm.conversations.list_conversations",
            side_effect=OSError("boom"),
        ):
            assert conversation_autocomplete("") == []


class TestResolveContinueOrResume:
    def test_continue_with_empty_store_raises(self, store, tmp_path):
        with pytest.raises(NoConversationsError):
            resolve_continue_or_resume(tmp_path, True, None)

    def test_resume_unknown_id_raises(self, store, tmp_path):
        write_transcript(
            store, "known", [{"type": "user", "message": {"content": "x"}}]
        )

        with pytest.raises(ConversationNotFoundError):
            resolve_continue_or_resume(tmp_path, False, "missing")

    def test_resume_known_id_passes(self, store, tmp_path):
        write_transcript(
            store, "known", [{"type": "user", "message": {"content": "x"}}]
        )

        resolve_continue_or_resume(tmp_path, False, "known")

    def test_continue_with_conversations_passes(self, store, tmp_path):
        write_transcript(
            store, "known", [{"type": "user", "message": {"content": "x"}}]
        )

        resolve_continue_or_resume(tmp_path, True, None)
