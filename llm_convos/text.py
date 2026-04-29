"""Text rendering helpers — relative times, snippet extraction, preview lines."""

from __future__ import annotations

import re
from datetime import datetime, timezone

from rich.text import Text

from .db import fetch_messages

FormattedFragment = tuple[str, str]
FormattedText = list[FormattedFragment]


def relative_time(dt_str: str) -> str:
    if not dt_str:
        return ""
    dt = datetime.fromisoformat(dt_str.replace("Z", "+00:00"))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    now = datetime.now(timezone.utc)
    seconds = int((now - dt).total_seconds())
    if seconds < 60:
        return "just now"
    elif seconds < 3600:
        return f"{seconds // 60}m ago"
    elif seconds < 86400:
        return f"{seconds // 3600}h ago"
    elif seconds < 86400 * 7:
        return f"{seconds // 86400}d ago"
    elif seconds < 86400 * 30:
        return f"{seconds // (86400 * 7)}w ago"
    else:
        return dt.strftime("%Y-%m-%d")


def make_snippet(text: str, term: str) -> Text:
    """Return a rich Text snippet centered on the first match of `term`,
    with the matched substring highlighted."""
    text = text.replace("\n", " ")
    idx = text.lower().find(term.lower())
    if idx == -1:
        return Text(text[:120], overflow="ellipsis")
    start = max(0, idx - 60)
    end = min(len(text), idx + len(term) + 60)
    snippet = ("…" if start > 0 else "") + text[start:end] + ("…" if end < len(text) else "")
    rich_text = Text(overflow="ellipsis")
    m = re.search(re.escape(term), snippet, re.IGNORECASE)
    if m:
        s, e = m.start(), m.end()
        rich_text.append(snippet[:s])
        rich_text.append(snippet[s:e], style="bold yellow")
        rich_text.append(snippet[e:])
    else:
        rich_text.append(snippet)
    return rich_text


def flatten_lines(formatted: FormattedText) -> list[FormattedText]:
    """Split formatted text fragments into per-line groups."""
    logical_lines: list[FormattedText] = [[]]
    for style, text in formatted:
        parts = text.split("\n")
        for i, part in enumerate(parts):
            if part:
                logical_lines[-1].append((style, part))
            if i < len(parts) - 1:
                logical_lines.append([])
    if logical_lines and not logical_lines[-1]:
        logical_lines.pop()
    return logical_lines


def _wrap_text(text: str, width: int, indent: int = 2) -> list[str]:
    """Word-wrap a single line to fit within `width` columns, with indent."""
    words = text.split()
    out: list[str] = []
    current = ""
    prefix = " " * indent
    max_w = width - indent - 1
    for word in words:
        if len(current) + len(word) + (1 if current else 0) <= max_w:
            current = current + (" " if current else "") + word
        else:
            if current:
                out.append(prefix + current)
            current = word
    if current:
        out.append(prefix + current)
    return out or [prefix]


def build_preview_lines(
    cid: str, search: str | None, preview_width: int, database: str | None
) -> FormattedText:
    """Build prompt_toolkit-style formatted text for the preview pane."""
    messages = fetch_messages(cid, database)
    if not messages:
        return [("class:preview.empty", " (no messages)")]

    if search:
        target_idx = next(
            (i for i, (_, t) in enumerate(messages) if search.lower() in t.lower()),
            None,
        )
        start = max(0, (target_idx or 0) - 1)
        end = min(len(messages), (target_idx or 0) + 2)
        show_messages = list(enumerate(messages))[start:end]
    else:
        show_messages = list(enumerate(messages))

    lines: FormattedText = []
    for _, (role, text) in show_messages:
        is_user = role == "user"
        label_style = "class:preview.user" if is_user else "class:preview.assistant"
        text_style = "class:preview.user.text" if is_user else "class:preview.assistant.text"
        lines.append((label_style, (" You" if is_user else " Assistant") + "\n"))
        lines.append(("class:preview.separator", " " + "─" * (preview_width - 2) + "\n"))

        for raw_line in text.replace("\r\n", "\n").split("\n")[:60]:
            if not raw_line.strip():
                lines.append((text_style, "\n"))
                continue
            for wrapped in _wrap_text(raw_line, preview_width):
                if search and search.lower() in wrapped.lower():
                    m = re.search(re.escape(search), wrapped, re.IGNORECASE)
                    if m:
                        s, e = m.start(), m.end()
                        lines.append((text_style, wrapped[:s]))
                        lines.append(("class:preview.match", wrapped[s:e]))
                        lines.append((text_style, wrapped[e:] + "\n"))
                        continue
                lines.append((text_style, wrapped + "\n"))

        lines.append(("", "\n"))

    return lines
