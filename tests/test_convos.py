import re
import sqlite3
from datetime import datetime, timedelta, timezone
from io import StringIO

import pytest

from llm_convos import (
    build_preview_lines,
    fetch_messages,
    fetch_rows,
    flatten_lines,
    make_snippet,
    relative_time,
)
from llm_convos.display import print_context, show_conversation

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def create_db(path: str) -> None:
    """Create a minimal llm-compatible logs.db at path with test data."""
    con = sqlite3.connect(path)
    con.executescript("""
        CREATE TABLE conversations (
            id TEXT PRIMARY KEY,
            name TEXT,
            model TEXT
        );
        CREATE TABLE responses (
            id TEXT PRIMARY KEY,
            model TEXT,
            prompt TEXT,
            system TEXT,
            prompt_json TEXT,
            options_json TEXT,
            response TEXT,
            response_json TEXT,
            conversation_id TEXT REFERENCES conversations(id),
            duration_ms INTEGER,
            datetime_utc TEXT,
            input_tokens INTEGER,
            output_tokens INTEGER,
            token_details TEXT,
            schema_id TEXT,
            resolved_model TEXT
        );

        INSERT INTO conversations VALUES ('conv-1', 'Test Conv 1', 'gpt-4');
        INSERT INTO conversations VALUES ('conv-2', 'Test Conv 2', 'gpt-4');

        -- conv-1: two exchanges
        INSERT INTO responses VALUES (
            'resp-1', 'gpt-4', 'What is asyncio?', NULL, NULL, NULL,
            'asyncio is a library for async I/O', NULL,
            'conv-1', 1000, '2024-01-01T10:00:00',
            10, 20, NULL, NULL, NULL
        );
        INSERT INTO responses VALUES (
            'resp-2', 'gpt-4', 'How do I use it?', NULL, NULL, NULL,
            'Use async/await syntax', NULL,
            'conv-1', 1000, '2024-01-01T10:01:00',
            10, 20, NULL, NULL, NULL
        );

        -- conv-2: one exchange, more recent
        INSERT INTO responses VALUES (
            'resp-3', 'gpt-4', 'Tell me about Python GIL', NULL, NULL, NULL,
            'The GIL prevents true parallelism', NULL,
            'conv-2', 1000, '2024-01-02T10:00:00',
            10, 20, NULL, NULL, NULL
        );
    """)
    con.close()


@pytest.fixture
def db_path(tmp_path):
    path = str(tmp_path / "logs.db")
    create_db(path)
    return path


# ---------------------------------------------------------------------------
# fetch_rows
# ---------------------------------------------------------------------------


def test_fetch_rows_returns_most_recent_first(db_path):
    # conv-2 is more recent, should come first
    rows = fetch_rows(10, None, db_path)
    assert rows[0][0] == "conv-2"
    assert rows[1][0] == "conv-1"


def test_fetch_rows_limit(db_path):
    rows = fetch_rows(1, None, db_path)
    assert len(rows) == 1


def test_fetch_rows_msg_count(db_path):
    rows = fetch_rows(10, None, db_path)
    by_id = {r[0]: r for r in rows}
    assert by_id["conv-1"][2] == 2  # two responses
    assert by_id["conv-2"][2] == 1  # one response


def test_fetch_rows_first_prompt(db_path):
    # matched_text for no-search is first prompt
    rows = fetch_rows(10, None, db_path)
    by_id = {r[0]: r for r in rows}
    assert by_id["conv-1"][4] == "What is asyncio?"
    assert by_id["conv-2"][4] == "Tell me about Python GIL"


def test_fetch_rows_search_matches_prompt(db_path):
    rows = fetch_rows(10, "asyncio", db_path)
    assert len(rows) == 1
    assert rows[0][0] == "conv-1"


def test_fetch_rows_search_matches_response(db_path):
    rows = fetch_rows(10, "GIL", db_path)
    assert len(rows) == 1
    assert rows[0][0] == "conv-2"


def test_fetch_rows_search_matched_text_is_matching_content(db_path):
    # When search matches the response (not prompt), matched_text should be the response
    rows = fetch_rows(10, "prevents true parallelism", db_path)
    assert len(rows) == 1
    assert "prevents true parallelism" in rows[0][4]


def test_fetch_rows_search_no_results(db_path):
    rows = fetch_rows(10, "nonexistent_xyz", db_path)
    assert rows == []


def test_fetch_rows_no_limit(db_path):
    # -1 means no limit — should return all conversations
    rows = fetch_rows(-1, None, db_path)
    assert len(rows) == 2


def test_fetch_rows_search_case_insensitive(db_path):
    rows = fetch_rows(10, "ASYNCIO", db_path)
    assert len(rows) == 1
    assert rows[0][0] == "conv-1"


# ---------------------------------------------------------------------------
# fetch_messages
# ---------------------------------------------------------------------------


def test_fetch_messages_returns_alternating_roles(db_path):
    # Clear lru_cache between tests
    fetch_messages.cache_clear()
    messages = fetch_messages("conv-1", db_path)
    assert messages[0] == ("user", "What is asyncio?")
    assert messages[1] == ("assistant", "asyncio is a library for async I/O")
    assert messages[2] == ("user", "How do I use it?")
    assert messages[3] == ("assistant", "Use async/await syntax")


def test_fetch_messages_ordered_oldest_first(db_path):
    fetch_messages.cache_clear()
    messages = fetch_messages("conv-1", db_path)
    assert messages[0][1] == "What is asyncio?"


def test_fetch_messages_unknown_conversation(db_path):
    fetch_messages.cache_clear()
    messages = fetch_messages("nonexistent", db_path)
    assert messages == []


# ---------------------------------------------------------------------------
# relative_time
# ---------------------------------------------------------------------------


def utc_str(delta_seconds: int) -> str:
    dt = datetime.now(timezone.utc) - timedelta(seconds=delta_seconds)
    return dt.strftime("%Y-%m-%dT%H:%M:%S")


def test_relative_time_just_now():
    assert relative_time(utc_str(10)) == "just now"


def test_relative_time_minutes():
    assert relative_time(utc_str(90)) == "1m ago"


def test_relative_time_hours():
    assert relative_time(utc_str(7200)) == "2h ago"


def test_relative_time_days():
    assert relative_time(utc_str(86400 * 3)) == "3d ago"


def test_relative_time_weeks():
    assert relative_time(utc_str(86400 * 14)) == "2w ago"


def test_relative_time_old_returns_date():
    result = relative_time(utc_str(86400 * 60))
    # Should be a date string like 2024-02-24
    assert re.match(r"\d{4}-\d{2}-\d{2}", result)


def test_relative_time_empty():
    assert relative_time("") == ""


# ---------------------------------------------------------------------------
# make_snippet
# ---------------------------------------------------------------------------


def test_make_snippet_no_match_returns_start():
    text = "hello world this is a test"
    result = make_snippet(text, "xyz")
    assert "hello world" in result.plain


def test_make_snippet_highlights_match():
    text = "the quick brown fox jumps"
    result = make_snippet(text, "fox")
    # The match span should be styled
    spans = [(s, e, style) for s, e, style in result._spans if style]
    assert any("yellow" in str(style) for _, _, style in spans)


def test_make_snippet_match_is_centered():
    # Build a long string where the match is in the middle
    text = "a " * 100 + "TARGET" + " b" * 100
    result = make_snippet(text, "TARGET")
    assert "TARGET" in result.plain


def test_make_snippet_case_insensitive():
    text = "Hello World"
    result = make_snippet(text, "world")
    assert "World" in result.plain


def test_make_snippet_strips_newlines():
    text = "line one\nline two\nTARGET here"
    result = make_snippet(text, "TARGET")
    assert "\n" not in result.plain


# ---------------------------------------------------------------------------
# show_conversation
# ---------------------------------------------------------------------------


def test_show_conversation_terminal(db_path):
    # Renders role labels and message text when no output path given
    fetch_messages.cache_clear()
    from unittest.mock import patch

    from rich.console import Console

    buf = StringIO()
    with patch("llm_convos.display.Console", return_value=Console(file=buf, highlight=False)):
        show_conversation("conv-1", db_path)

    output = buf.getvalue()
    assert "What is asyncio?" in output
    assert "asyncio is a library" in output


def test_show_conversation_file_output(db_path, tmp_path):
    # Writes markdown with expected structure to file
    fetch_messages.cache_clear()
    out = str(tmp_path / "out.md")
    show_conversation("conv-1", db_path, output=out)
    with open(out) as f:
        content = f.read()
    assert "## You" in content
    assert "## Assistant" in content
    assert "What is asyncio?" in content
    assert "asyncio is a library" in content
    assert "---" in content


def test_show_conversation_unknown_id(db_path):
    # Gracefully handles a missing conversation with no crash
    fetch_messages.cache_clear()
    show_conversation("nonexistent", db_path)  # should not raise


def test_show_conversation_multiple_exchanges(db_path, tmp_path):
    # File output includes all exchanges in order
    fetch_messages.cache_clear()
    out = str(tmp_path / "out.md")
    show_conversation("conv-1", db_path, output=out)
    with open(out) as f:
        content = f.read()
    assert content.index("What is asyncio?") < content.index("How do I use it?")


# ---------------------------------------------------------------------------
# print_context
# ---------------------------------------------------------------------------


def test_print_context_prints_last_n_exchanges(db_path):
    # With n=1 only the last exchange is printed
    fetch_messages.cache_clear()
    buf = StringIO()
    from unittest.mock import patch

    from rich.console import Console

    with patch("llm_convos.display.console", Console(file=buf, highlight=False)):
        print_context("conv-1", 1, db_path)

    output = buf.getvalue()
    assert "How do I use it?" in output
    assert "Use async/await syntax" in output
    assert "What is asyncio?" not in output


def test_print_context_prints_all_exchanges_when_n_exceeds_count(db_path):
    # n larger than total exchanges prints everything
    fetch_messages.cache_clear()
    buf = StringIO()
    from unittest.mock import patch

    from rich.console import Console

    with patch("llm_convos.display.console", Console(file=buf, highlight=False)):
        print_context("conv-1", 99, db_path)

    output = buf.getvalue()
    assert "What is asyncio?" in output
    assert "How do I use it?" in output


# ---------------------------------------------------------------------------
# build_preview_lines / flatten_lines
# ---------------------------------------------------------------------------


def test_build_preview_lines_contains_role_labels(db_path):
    # Preview lines include You/Assistant labels
    fetch_messages.cache_clear()
    lines = build_preview_lines("conv-1", None, 80, db_path)
    text = "".join(t for _, t in lines)
    assert "You" in text
    assert "Assistant" in text


def test_build_preview_lines_search_highlights_match(db_path):
    # When search term present, match fragment uses preview.match style
    fetch_messages.cache_clear()
    lines = build_preview_lines("conv-1", "asyncio", 80, db_path)
    styles = [s for s, _ in lines]
    assert "class:preview.match" in styles


def test_build_preview_lines_empty_conversation(db_path):
    # Unknown cid returns empty indicator
    fetch_messages.cache_clear()
    lines = build_preview_lines("nonexistent", None, 80, db_path)
    assert any("preview.empty" in s for s, _ in lines)


def test_flatten_lines_splits_on_newlines():
    # Each logical line is a separate list
    fragments = [("a", "hello\nworld"), ("b", "!")]
    result = flatten_lines(fragments)
    assert len(result) == 2
    assert result[0] == [("a", "hello")]
    assert result[1] == [("a", "world"), ("b", "!")]


def test_flatten_lines_no_trailing_empty():
    # Trailing newline does not produce an empty final line
    fragments = [("", "line\n")]
    result = flatten_lines(fragments)
    assert result == [[("", "line")]]
