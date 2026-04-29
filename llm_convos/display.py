"""Rich-based output: the plain-mode table and the resume-context print."""

from __future__ import annotations

from rich import box
from rich.console import Console
from rich.table import Table
from rich.text import Text

from .db import fetch_messages
from .text import make_snippet, relative_time

console = Console(soft_wrap=False)


Row = tuple[str, str | None, int, str, str]


def print_table(rows: list[Row], search: str | None) -> None:
    """Render the conversation list as a non-interactive Rich table."""
    col_label = "Match" if search else "First Prompt"
    table = Table(box=box.ROUNDED, show_header=True, header_style="bold cyan", expand=True)
    table.add_column("ID", style="dim", no_wrap=True, min_width=26, max_width=26)
    table.add_column("Msgs", justify="right", no_wrap=True, min_width=4, max_width=4)
    table.add_column("Last Active", no_wrap=True, min_width=7, max_width=11)
    table.add_column(col_label, no_wrap=True, overflow="ellipsis", ratio=1)

    for cid, _model, num_responses, last_active, matched_text in rows:
        if search:
            preview: Text = make_snippet(matched_text or "", search)
        else:
            preview = Text((matched_text or "").replace("\n", " "), overflow="ellipsis")
        table.add_row(cid, str(num_responses), relative_time(last_active), preview)

    console.print(table)
    console.print("[dim]Resume with: llm chat --continue --conversation <ID>[/dim]")


def print_context(cid: str, n: int, database: str | None) -> None:
    """Print the last `n` exchanges of conversation `cid` before resuming."""
    messages = fetch_messages(cid, database)
    exchanges: list[tuple[str, str]] = []
    i = 0
    while i < len(messages) - 1:
        if messages[i][0] == "user" and messages[i + 1][0] == "assistant":
            exchanges.append((messages[i][1], messages[i + 1][1]))
            i += 2
        else:
            i += 1

    for prompt, response in exchanges[-n:]:
        console.print("[bold cyan]You[/bold cyan]")
        console.print(prompt.strip())
        console.print()
        console.print("[bold green]Assistant[/bold green]")
        console.print(response.strip())
        console.print()

    console.rule(style="dim")
