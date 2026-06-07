# XHS Radar

Semi-automated Xiaohongshu/RedNote hotspot radar for topic discovery, low-follower high-engagement note analysis, writing angles, and Feishu report generation.

## What This MVP Does

- Searches a small set of Xiaohongshu keywords at low frequency.
- Reads selected public notes with RedNote-MCP.
- Extracts hooks, writing patterns, user demand, and topic models.
- Generates a compact Markdown report.
- Creates a Feishu docx report from the Markdown report.
- Can grant a Feishu user collaborator access to an app-created document.

The project is intentionally not a crawler. The value is editorial judgment, not high-volume collection.

## Safety Principles

- Read-only Xiaohongshu behavior by default.
- No likes, favorites, follows, comments, posts, or private messages.
- No cookie/token printing or inspection.
- Small keyword batches only.
- Stop retrying if an endpoint times out or appears hostile.
- Final publishing actions always require explicit human confirmation.

## Environment Variables

Required for Feishu document creation:

```powershell
setx FEISHU_APP_ID "your_feishu_app_id"
setx FEISHU_APP_SECRET "your_feishu_app_secret"
```

Optional:

```powershell
setx FEISHU_REPORT_FOLDER_TOKEN "target_feishu_folder_token"
setx FEISHU_REPORT_USER_EMAIL "your_feishu_login_email"
setx FEISHU_REPORT_USER_PERM "full_access"
```

Useful Feishu permissions:

- `docx:document` or `docx:document:create` to create docs.
- `docx:document.block:convert` to convert Markdown into richer doc blocks.
- Drive permission/member scopes to add a user collaborator to app-created docs.

## Current Scripts

Create a Feishu report from Markdown:

```powershell
python scripts\create_feishu_report.py reports\popmart_mvp_2026-06-07.md
```

Grant a user access to an app-created doc:

```powershell
python scripts\share_feishu_doc.py QSBWd0aOXo6FhCxt2LScU5EEnEs email your@email.com full_access
```

## Codex Skill

The reusable skill is in:

```text
skills/xhs-radar/
```

It contains the workflow and bundled scripts for repeating the hotspot radar process.
