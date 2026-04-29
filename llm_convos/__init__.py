"""llm-convos plugin: browse and resume llm conversations."""

from __future__ import annotations

import os
import sys

import click
import llm

# Re-exported for tests
from .db import fetch_messages, fetch_rows, get_db_path, open_db  # noqa: F401
from .display import print_context, print_table
from .text import (  # noqa: F401
    build_preview_lines,
    flatten_lines,
    make_snippet,
    relative_time,
)
from .tui import pick_interactive


@llm.hookimpl
def register_commands(cli):
    @cli.command(name="convos")
    @click.option(
        "-n",
        "--limit",
        default=20,
        show_default=True,
        help="Max conversations to show (-1 for all)",
    )
    @click.option(
        "-s",
        "--search",
        default=None,
        help="Filter by prompt/response text",
    )
    @click.option(
        "-m",
        "--mode",
        type=click.Choice(["interactive", "preview", "plain"]),
        default=None,
        help="Display mode (default: interactive when tty, plain otherwise)",
    )
    @click.option(
        "-d",
        "--database",
        type=click.Path(readable=True, dir_okay=False),
        default=None,
        help="Path to log database (default: llm's logs.db)",
    )
    @click.option(
        "-c",
        "--context",
        default=0,
        show_default=True,
        help="Exchanges to print before resuming",
    )
    def convos(
        limit: int,
        search: str | None,
        mode: str | None,
        database: str | None,
        context: int,
    ) -> None:
        """Browse and resume llm conversations."""
        if mode is None:
            mode = "interactive" if sys.stdout.isatty() else "plain"

        rows = fetch_rows(limit, search, database)
        if not rows:
            click.echo("No conversations found.")
            return

        if mode == "plain":
            print_table(rows, search)
            return

        cid = pick_interactive(rows, search, show_preview=(mode == "preview"), database=database)
        if cid:
            if context > 0:
                print_context(cid, context, database)
            os.execvp("llm", ["llm", "chat", "--continue", "--conversation", cid])
