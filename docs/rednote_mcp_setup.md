# RedNote-MCP Setup

This project uses RedNote-MCP as the preferred Xiaohongshu/RedNote access path.
Use it for small, read-only research batches. Do not use it as a crawler.

## Install

```powershell
npm install -g rednote-mcp
```

## Initialize Login

Run initialization and finish login in the browser window it opens:

```powershell
rednote-mcp init 120
```

The tool stores cookies outside this repo. Do not copy, print, commit, or inspect
cookie files.

## Codex MCP Config

Add this to `C:\Users\<User>\.codex\config.toml`:

```toml
[mcp_servers.rednote]
command = "rednote-mcp"
args = ["--stdio"]
```

Then restart Codex.

## Expected Tools

After restart, Codex should expose tools similar to:

- `mcp__rednote.search_notes`
- `mcp__rednote.get_note_content`
- `mcp__rednote.get_note_comments`
- `mcp__rednote.login`

## Low-frequency Research Boundary

- 1-5 keywords per run.
- 3-10 notes per keyword.
- Add pauses between searches and detail reads.
- Read comments only for selected promising notes.
- Stop retrying if an endpoint times out.
- Never perform account write actions unless the user explicitly confirms them.

## Standalone Script

`scripts/collect_xhs_notes.py` can call a stdio MCP server directly. It is useful
outside Codex or when you want raw JSON snapshots.

Example:

```powershell
python scripts\collect_xhs_notes.py --config config\xhs_keywords.example.json --out data\xhs_raw\popmart.json
```

The script starts `rednote-mcp --stdio`, calls `search_notes`, optionally reads a
small number of note details, and writes JSON output.
