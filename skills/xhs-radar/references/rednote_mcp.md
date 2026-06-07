# RedNote-MCP Reference

## Install

```powershell
npm install -g rednote-mcp
rednote-mcp init 120
```

Add to Codex config:

```toml
[mcp_servers.rednote]
command = "rednote-mcp"
args = ["--stdio"]
```

Restart Codex after editing config.

## Tool Mapping

- Search notes: `search_notes({"keywords": "...", "limit": 5})`
- Read note content: `get_note_content({"url": "..."})`
- Read comments: `get_note_comments({"url": "..."})`

Use search result URLs with `xsec_token`; do not construct bare note IDs.

## Standalone Script

From the repo root:

```powershell
python scripts\collect_xhs_notes.py --config config\xhs_keywords.example.json --out data\xhs_raw\sample.json --detail-limit 1
```

The script calls RedNote-MCP over stdio and writes raw JSON. Keep limits small.
