"""Interactive prompt_toolkit picker with optional preview pane."""

from __future__ import annotations

import os

from prompt_toolkit import Application, prompt
from prompt_toolkit.buffer import Buffer
from prompt_toolkit.document import Document
from prompt_toolkit.filters import Condition
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.layout import HSplit, Layout
from prompt_toolkit.layout.containers import (
    ConditionalContainer,
    Float,
    FloatContainer,
    Window,
)
from prompt_toolkit.layout.controls import BufferControl, FormattedTextControl
from prompt_toolkit.layout.dimension import Dimension
from prompt_toolkit.styles import Style

from .text import build_preview_lines, flatten_lines, relative_time

Row = tuple[str, str | None, int, str, str]

HINT_INTERACTIVE = (
    " ↑↓ navigate   ctrl+↑↓ top/bottom   / search   enter resume   s show   w write   q quit"
)
HINT_PREVIEW = " ↑↓ navigate   ctrl+↑↓ top/bottom   jk/gg/G scroll preview   / search   enter resume   s show   w write   q quit"
HINT_SHORT = " ? shortcuts"

SHORTCUTS = [
    ("↑ / ↓", "Navigate list"),
    ("Ctrl+↑ / Ctrl+↓", "Jump to top / bottom of list"),
    ("j / k", "Scroll preview up/down"),
    ("gg / G", "Jump to top / bottom of preview"),
    ("/ ", "Search"),
    ("Enter", "Resume conversation"),
    ("s", "Show conversation"),
    ("w", "Write to markdown file"),
    ("q / Esc", "Quit"),
    ("?", "Toggle this help"),
]


def pick_interactive(
    rows: list[Row],
    search: str | None,
    show_preview: bool,
    database: str | None,
) -> tuple[str, str, str | None] | None:
    """Show an interactive picker.

    Returns a tuple of (action, cid, extra) or None if cancelled.
    - action "resume": cid is the conversation to continue, extra is None
    - action "show": cid is the conversation to display, extra is None
    - action "write": cid is the conversation to save, extra is the filepath
    - action "search": extra is the new search term (or None to clear)
    """
    selected = [0]
    cancelled = [False]
    action = ["resume"]
    extra: list[str | None] = [None]
    list_scroll = [0]
    preview_scroll = [0]
    preview_total_lines = [1]
    last_was_g = [False]
    searching = [False]
    showing_help = [False]

    term_size = os.get_terminal_size()
    term_width = term_size.columns
    term_height = term_size.lines

    preview_height = max(5, term_height // 2) if show_preview else 0
    list_height = max(5, term_height - preview_height - 1) if show_preview else term_height - 3
    # header + separator = 2 lines; footer hint adds 1 more in non-preview mode
    list_visible_rows = list_height - (2 if show_preview else 3)
    preview_width = term_width - 2
    fixed_cols = 26 + 4 + 11 + 12
    preview_col_width = max(10, term_width - fixed_cols)

    # Use short hint if terminal is too narrow for the full one
    full_hint = HINT_PREVIEW if show_preview else HINT_INTERACTIVE
    hint_text = full_hint if term_width >= len(full_hint) else HINT_SHORT

    initial_search = search or ""
    search_buffer = Buffer(name="search", document=Document(initial_search, len(initial_search)))

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
            lines.append(("class:footer", hint_text))
        return lines

    def get_preview_text() -> list[tuple[str, str]]:
        cid = rows[selected[0]][0]
        all_lines = flatten_lines(build_preview_lines(cid, search, preview_width, database))
        total = len(all_lines)
        preview_total_lines[0] = total
        scroll = min(preview_scroll[0], max(0, total - preview_height))
        preview_scroll[0] = scroll

        visible_flat: list[tuple[str, str]] = []
        for logical_line in all_lines[scroll:]:
            for frag in logical_line:
                visible_flat.append(frag)
            visible_flat.append(("", "\n"))

        return visible_flat

    def get_footer_hint_text() -> list[tuple[str, str]]:
        scroll = preview_scroll[0]
        total = preview_total_lines[0]
        suffix = f"   {scroll + 1}/{total} lines"
        text = hint_text + suffix if hint_text != HINT_SHORT else hint_text
        return [("class:footer", text)]

    def get_help_text() -> list[tuple[str, str]]:
        key_w = max(len(k) for k, _ in SHORTCUTS)
        lines: list[tuple[str, str]] = [("class:help.title", " Keyboard shortcuts\n")]
        lines.append(("class:help.separator", " " + "─" * (key_w + 22) + "\n"))
        for key, desc in SHORTCUTS:
            lines.append(("class:help.key", f"  {key:<{key_w}}"))
            lines.append(("class:help.desc", f"  {desc}\n"))
        lines.append(("class:footer", " any key to close"))
        return lines

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

    is_searching = Condition(lambda: searching[0])
    not_searching = Condition(lambda: not searching[0])
    is_showing_help = Condition(lambda: showing_help[0])
    not_showing_help = Condition(lambda: not showing_help[0])

    @kb.add("up", filter=not_searching & not_showing_help)
    def move_up(_event):
        select(selected[0] - 1)

    @kb.add("down", filter=not_searching & not_showing_help)
    def move_down(_event):
        select(selected[0] + 1)

    @kb.add("c-up", filter=not_searching & not_showing_help)
    def jump_list_top(_event):
        select(0)

    @kb.add("c-down", filter=not_searching & not_showing_help)
    def jump_list_bottom(_event):
        select(len(rows) - 1)
        list_scroll[0] = max(0, len(rows) - list_visible_rows)

    @kb.add("g", filter=not_searching & not_showing_help)
    def handle_g(_event):
        if last_was_g[0]:
            preview_scroll[0] = 0
            clear_g()
        else:
            last_was_g[0] = True

    @kb.add("G", filter=not_searching & not_showing_help)
    def jump_bottom(_event):
        preview_scroll[0] = max(0, preview_total_lines[0] - preview_height)
        clear_g()

    @kb.add("j", filter=not_searching & not_showing_help)
    def scroll_preview_down(_event):
        preview_scroll[0] += 1
        clear_g()

    @kb.add("k", filter=not_searching & not_showing_help)
    def scroll_preview_up(_event):
        preview_scroll[0] = max(0, preview_scroll[0] - 1)
        clear_g()

    @kb.add("enter", filter=not_searching & not_showing_help)
    def confirm(event):
        clear_g()
        event.app.exit()

    @kb.add("s", filter=not_searching & not_showing_help)
    def show(event):
        action[0] = "show"
        clear_g()
        event.app.exit()

    @kb.add("w", filter=not_searching & not_showing_help)
    def write(event):
        action[0] = "write"
        clear_g()
        event.app.exit()

    @kb.add("/", filter=not_searching & not_showing_help)
    def start_search(event):
        searching[0] = True
        search_buffer.set_document(Document(search_buffer.text, len(search_buffer.text)))
        event.app.layout.focus(search_buffer)
        clear_g()

    @kb.add("enter", filter=is_searching)
    def submit_search(event):
        searching[0] = False
        term = search_buffer.text.strip()
        extra[0] = term or None
        action[0] = "search"
        event.app.layout.focus(list_control)
        event.app.exit()

    @kb.add("escape", filter=is_searching)
    @kb.add("c-c", filter=is_searching)
    def cancel_search(event):
        searching[0] = False
        event.app.layout.focus(list_control)

    @kb.add("?", filter=not_searching)
    def toggle_help(event):
        showing_help[0] = not showing_help[0]
        clear_g()

    # Any key closes help (except ? which toggles it — handled above)
    @kb.add("<any>", filter=is_showing_help & not_searching)
    def close_help(_event):
        showing_help[0] = False

    @kb.add("q", filter=not_searching & not_showing_help)
    @kb.add("c-c", filter=not_searching & not_showing_help)
    @kb.add("escape", filter=not_searching & not_showing_help)
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
            "search-label": "ansidarkgray",
            "preview.user": "bold cyan",
            "preview.assistant": "bold green",
            "preview.user.text": "noinherit",
            "preview.assistant.text": "noinherit ansigray",
            "preview.separator": "ansidarkgray",
            "preview.match": "bold yellow",
            "preview.empty": "ansidarkgray italic",
            "help.title": "bold cyan",
            "help.separator": "ansidarkgray",
            "help.key": "bold",
            "help.desc": "",
            "help-modal": "bg:#1e1e1e",
        }
    )

    list_control = FormattedTextControl(get_list_text, focusable=True)
    search_control = BufferControl(buffer=search_buffer, focusable=True)

    help_window = Window(
        content=FormattedTextControl(get_help_text),
        style="class:help-modal",
        width=Dimension(preferred=50, max=60),
        height=Dimension(preferred=len(SHORTCUTS) + 3),
    )

    if show_preview:
        preview_control = FormattedTextControl(get_preview_text, focusable=False)
        footer_control = FormattedTextControl(get_footer_hint_text, focusable=False)
        inner = HSplit(
            [
                Window(content=list_control, height=Dimension(preferred=list_height)),
                Window(height=1, char="─", style="class:separator"),
                Window(
                    content=preview_control,
                    height=Dimension(min=preview_height - 1, max=preview_height - 1),
                ),
                ConditionalContainer(
                    Window(content=footer_control, height=1),
                    filter=not_searching,
                ),
                ConditionalContainer(
                    HSplit(
                        [
                            Window(height=1, char="─", style="class:separator"),
                            Window(
                                content=search_control,
                                height=1,
                                get_line_prefix=lambda *_: [("class:search-label", " Search: ")],
                            ),
                        ]
                    ),
                    filter=is_searching,
                ),
            ]
        )
    else:
        inner = Window(content=list_control)

    root = FloatContainer(
        content=inner,
        floats=[
            Float(
                content=ConditionalContainer(help_window, filter=is_showing_help),
                xcursor=False,
                ycursor=False,
            )
        ],
    )

    app: Application = Application(
        layout=Layout(root, focused_element=list_control),
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

    if action[0] == "search" and not show_preview:
        # Non-preview mode still uses the external prompt approach
        try:
            term = prompt("Search: ", default=search or "").strip()
        except (KeyboardInterrupt, EOFError):
            term = ""
        extra[0] = term or None

    return action[0], cid, extra[0]
