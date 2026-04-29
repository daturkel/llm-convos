"""Interactive prompt_toolkit picker with optional preview pane."""

from __future__ import annotations

import os

from prompt_toolkit import Application, prompt
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.layout import HSplit, Layout
from prompt_toolkit.layout.containers import Window
from prompt_toolkit.layout.controls import FormattedTextControl
from prompt_toolkit.layout.dimension import Dimension
from prompt_toolkit.styles import Style

from .text import build_preview_lines, flatten_lines, relative_time

Row = tuple[str, str | None, int, str, str]

PREVIEW_HEIGHT = 12


def pick_interactive(
    rows: list[Row],
    search: str | None,
    show_preview: bool,
    database: str | None,
) -> tuple[str, str, str | None] | None:
    """Show an interactive picker.

    Returns a tuple of (action, cid, extra) where action is one of "resume",
    "show", or "write"; extra is the destination filepath for "write" or None.
    Returns None if cancelled.
    """
    selected = [0]
    cancelled = [False]
    action = ["resume"]
    extra: list[str | None] = [None]
    list_scroll = [0]
    preview_scroll = [0]
    preview_total_lines = [1]
    last_was_g = [False]

    term_size = os.get_terminal_size()
    term_width = term_size.columns
    term_height = term_size.lines

    list_height = max(5, term_height - PREVIEW_HEIGHT - 1) if show_preview else term_height - 3
    # header + separator = 2 lines; footer hint adds 1 more in non-preview mode
    list_visible_rows = list_height - (2 if show_preview else 3)
    preview_width = term_width - 2
    fixed_cols = 26 + 4 + 11 + 12
    preview_col_width = max(10, term_width - fixed_cols)

    def get_list_text() -> list[tuple[str, str]]:
        lines: list[tuple[str, str]] = []
        header = f" {'ID':<26}  {'Msgs':>4}  {'Last Active':<11}  {'Preview':<{preview_col_width}}"
        lines.append(("class:header", header + "\n"))
        lines.append(("class:separator", "─" * term_width + "\n"))
        visible = rows[list_scroll[0] : list_scroll[0] + list_visible_rows]
        for i, (cid, _model, num_responses, last_active, matched_text) in enumerate(visible):
            abs_i = list_scroll[0] + i
            text = (matched_text or "").replace("\n", " ")
            if search:
                idx = text.lower().find(search.lower())
                if idx != -1:
                    s = max(0, idx - 40)
                    e = min(len(text), idx + len(search) + 40)
                    text = ("…" if s > 0 else "") + text[s:e] + ("…" if e < len(text) else "")
            if len(text) > preview_col_width - 1:
                text = text[: preview_col_width - 2] + "…"
            age = relative_time(last_active)
            line = f" {cid}  {num_responses:>4}  {age:<11}  {text:<{preview_col_width}}"
            lines.append(("class:selected" if abs_i == selected[0] else "", line + "\n"))
        if not show_preview:
            hint = " ↑↓ navigate   ctrl+↑↓ top/bottom   jk/gg/G scroll preview   / search   enter resume   s show   w write   q quit"
            lines.append(("class:footer", hint))
        return lines

    def get_preview_text() -> list[tuple[str, str]]:
        cid = rows[selected[0]][0]
        all_lines = flatten_lines(build_preview_lines(cid, search, preview_width, database))
        total = len(all_lines)
        preview_total_lines[0] = total
        scroll = min(preview_scroll[0], max(0, total - PREVIEW_HEIGHT))
        preview_scroll[0] = scroll

        visible_flat: list[tuple[str, str]] = []
        for logical_line in all_lines[scroll:]:
            for frag in logical_line:
                visible_flat.append(frag)
            visible_flat.append(("", "\n"))

        hint = f" j/k scroll   {scroll + 1}/{total} lines"
        visible_flat.append(("class:footer", hint))
        return visible_flat

    kb = KeyBindings()

    def select(idx: int) -> None:
        selected[0] = max(0, min(len(rows) - 1, idx))
        if selected[0] < list_scroll[0]:
            list_scroll[0] = selected[0]
        elif selected[0] >= list_scroll[0] + list_visible_rows:
            list_scroll[0] = selected[0] - list_visible_rows + 1
        preview_scroll[0] = 0
        last_was_g[0] = False

    def clear_g() -> None:
        last_was_g[0] = False

    @kb.add("up")
    def move_up(_event):
        select(selected[0] - 1)

    @kb.add("down")
    def move_down(_event):
        select(selected[0] + 1)

    @kb.add("c-up")
    def jump_list_top(_event):
        select(0)

    @kb.add("c-down")
    def jump_list_bottom(_event):
        select(len(rows) - 1)
        list_scroll[0] = max(0, len(rows) - list_visible_rows)

    @kb.add("g")
    def handle_g(_event):
        if last_was_g[0]:
            preview_scroll[0] = 0
            clear_g()
        else:
            last_was_g[0] = True

    @kb.add("G")
    def jump_bottom(_event):
        preview_scroll[0] = max(0, preview_total_lines[0] - PREVIEW_HEIGHT)
        clear_g()

    @kb.add("j")
    def scroll_preview_down(_event):
        preview_scroll[0] += 1
        clear_g()

    @kb.add("k")
    def scroll_preview_up(_event):
        preview_scroll[0] = max(0, preview_scroll[0] - 1)
        clear_g()

    @kb.add("enter")
    def confirm(event):
        clear_g()
        event.app.exit()

    @kb.add("s")
    def show(event):
        action[0] = "show"
        clear_g()
        event.app.exit()

    @kb.add("w")
    def write(event):
        action[0] = "write"
        clear_g()
        event.app.exit()

    @kb.add("/")
    def search_prompt(event):
        action[0] = "search"
        clear_g()
        event.app.exit()

    @kb.add("q")
    @kb.add("c-c")
    @kb.add("escape")
    def cancel(event):
        cancelled[0] = True
        clear_g()
        event.app.exit()

    style = Style.from_dict(
        {
            "header": "bold cyan",
            "separator": "ansidarkgray",
            "selected": "reverse bold",
            "footer": "ansidarkgray italic",
            "preview.user": "bold cyan",
            "preview.assistant": "bold green",
            "preview.user.text": "",
            "preview.assistant.text": "ansigray",
            "preview.separator": "ansidarkgray",
            "preview.match": "bold yellow",
            "preview.empty": "ansidarkgray italic",
        }
    )

    list_control = FormattedTextControl(get_list_text, focusable=True)

    if show_preview:
        preview_control = FormattedTextControl(get_preview_text, focusable=False)
        root = HSplit(
            [
                Window(content=list_control, height=Dimension(preferred=list_height)),
                Window(height=1, char="─", style="class:separator"),
                Window(
                    content=preview_control,
                    height=Dimension(min=PREVIEW_HEIGHT, max=PREVIEW_HEIGHT),
                ),
            ]
        )
    else:
        root = Window(content=list_control)

    app: Application = Application(
        layout=Layout(root),
        key_bindings=kb,
        style=style,
        full_screen=show_preview,
        mouse_support=False,
    )
    app.run()

    if cancelled[0]:
        return None

    cid = rows[selected[0]][0]

    if action[0] == "write":
        # Prompt for filename after the TUI has fully exited
        default_name = f"{cid[:8]}.md"
        try:
            path = prompt("Save to: ", default=default_name).strip()
        except (KeyboardInterrupt, EOFError):
            path = ""
        if not path:
            return None
        extra[0] = path

    if action[0] == "search":
        try:
            term = prompt("Search: ", default=search or "").strip()
        except (KeyboardInterrupt, EOFError):
            term = ""
        extra[0] = term or None  # None means clear the search

    return action[0], cid, extra[0]
