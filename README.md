# llm-convos

[![PyPI](https://img.shields.io/pypi/v/llm-convos.svg)](https://pypi.org/project/llm-convos/)
[![Changelog](https://img.shields.io/github/v/release/daturkel/llm-convos?include_prereleases&label=changelog)](https://github.com/daturkel/llm-convos/releases)
[![Tests](https://github.com/daturkel/llm-convos/actions/workflows/test.yml/badge.svg)](https://github.com/daturkel/llm-convos/actions/workflows/test.yml)
[![License](https://img.shields.io/badge/license-MIT-blue.svg)](https://github.com/daturkel/llm-convos/blob/main/LICENSE)

A plugin for [LLM](https://llm.datasette.io/) that lets you browse, search, and resume past conversations interactively.

## Installation

```bash
llm install llm-convos
```

## Usage

```bash
llm convos
```

This opens an interactive list of your recent conversations. Use arrow keys or `j`/`k` to navigate, and `q` or `Esc` to quit.

From the picker you can:
- Press `Enter` to resume the selected conversation
- Press `s` to show the full conversation rendered as markdown in your terminal
- Press `w` to write the conversation to a markdown file (prompts for a filename, pre-filled with the conversation ID)

Pass `-c N/--context N` to print the last N exchanges before resuming, so you have context for where you left off.

### Show a conversation directly

```bash
llm convos show <conversation-id>
```

Renders the full conversation as markdown in your terminal. Pass `-o`/`--output` to write to a file instead:

```bash
llm convos show <conversation-id> -o transcript.md
```

### Modes

| Flag | Behavior |
|------|----------|
| _(default)_ | Interactive list, inline (doesn't take over the full screen) |
| `-m preview` | Interactive list with a scrollable preview pane below |
| `-m plain` | Non-interactive table, useful for scripting |

Plain mode is used automatically when stdout is not a tty.

### Searching

```bash
llm convos -s asyncio
```

Filters conversations to those containing the search term in any prompt or response. In interactive mode the matching excerpt is shown (with the term highlighted) instead of the first prompt.

### Options

`llm convos`:
```
-n, --limit INTEGER      Max conversations to show (-1 for all) [default: 20]
-s, --search TEXT        Filter by prompt/response text
-m, --mode [interactive|preview|plain]
                         Display mode
-d, --database FILE      Path to log database (default: llm's logs.db)
-c, --context INTEGER    Exchanges to print before resuming [default: 0]
```

`llm convos show <conversation-id>`:
```
-o, --output FILE        Write markdown to this file instead of printing
-d, --database FILE      Path to log database (default: llm's logs.db)
```

### Keyboard shortcuts

| Key | Action |
|-----|--------|
| `↑` / `↓` | Navigate the conversation list |
| `k` / `j` | Scroll the preview pane up/down |
| `gg` / `G` | Jump to top / bottom of list |
| `Enter` | Resume selected conversation |
| `s` | Show selected conversation as markdown in terminal |
| `w` | Write selected conversation to a markdown file |
| `q` / `Esc` | Quit |

### Custom database path

If you keep your LLM logs at a non-default path, pass it explicitly:

```bash
llm convos -d /path/to/logs.db
```

The `LLM_USER_PATH` environment variable is also respected automatically.

## Development

```bash
git clone https://github.com/daturkel/llm-convos
cd llm-convos
uv run pytest
```

To run LLM with your in-development version of the plugin:

```bash
uv run llm convos
```
