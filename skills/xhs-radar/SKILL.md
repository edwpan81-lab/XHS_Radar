---
name: xhs-radar
description: >
  Run a low-frequency Xiaohongshu/RedNote hotspot radar for topic discovery,
  low-follower high-engagement note analysis, writing-method teardown, dual
  WeChat/Xiaohongshu topic recommendations, and Feishu report generation.
  Use when the user asks to analyze Xiaohongshu trends, low-follower high-like
  notes, brand/topic MVP tests, or create a Feishu report from XHS findings.
metadata:
  short-description: Xiaohongshu hotspot and writing-pattern radar
---

# XHS Radar

Use this skill to turn small Xiaohongshu/RedNote samples into editorial decisions:
hotspot signals, low-follower high-engagement candidates, writing-pattern teardown,
topic recommendations, and Feishu reports.

## Safety Defaults

- Treat Xiaohongshu as read-only unless the user explicitly confirms an account write action.
- Search 1-5 keywords per run and 3-10 notes per keyword by default.
- Add human-like pauses between searches and reads.
- Do not inspect, print, copy, or expose cookies, tokens, browser storage, or passwords.
- Do not retry hostile/timeouting endpoints repeatedly; record the failure and continue.
- Never like, favorite, follow, comment, publish, delete, or message unless explicitly requested and confirmed.

## Standard Workflow

1. Confirm the topic keyword and purpose.
   - For brand MVPs, use one primary keyword plus 2-4 angle keywords.
   - Example: `泡泡玛特`, `Labubu 普通人`, `泡泡玛特 避雷`, `泡泡玛特 为什么火`.
2. Search with RedNote-MCP first.
   - Prefer `search_notes` with small limits.
   - Record title, author, content snippet, likes, comments, URL, and tags.
   - For setup details and standalone collection, read `references/rednote_mcp.md`.
3. Select promising notes for detail reads.
   - Prioritize high comments, high saves if available, strong title hooks, and unusual angles.
   - If follower count is unavailable, label the sample as `疑似低粉高互动` and require manual/browser review.
4. Analyze each note.
   - Hook/title pattern.
   - Target audience.
   - Pain point or desire.
   - Content structure.
   - Comment-section demand if available.
   - Why it may be performing well.
   - Reusable writing pattern.
   - WeChat angle and Xiaohongshu angle.
5. Produce a compact report.
   - Top findings first.
   - Sample table.
   - Writing-pattern teardown.
   - Reusable topic models.
   - Recommended WeChat topics.
   - Recommended Xiaohongshu topics.
   - Soft-commerce opportunities.
   - Collection boundary and safety notes.
6. Create a Feishu doc if requested.
   - Use `scripts/create_feishu_report.py`.
   - If the doc is app-owned, grant the user access with `scripts/share_feishu_doc.py`.

## Low-Follower High-Engagement Heuristic

Do not rely on a single hard threshold. Use tiers:

- Strong low-follower hit: followers `< 3000` and likes `> 500`.
- Low-follower high-like: followers `< 10000` and likes `> 1000`.
- High-throughput sample: likes / followers `> 0.3`.
- Super-throughput sample: likes / followers `> 1`.
- Discussion sample: comments / likes `> 0.05`.
- Utility sample: comments near or above likes, often indicating guide/decision demand.

If follower count is unavailable, keep the sample but mark it `粉丝数待复核`.

## Report Style

Keep reports practical and compact. Good sections:

1. 本期结论
2. 样本榜单
3. 写法拆解
4. 可复用选题模型
5. 给你的选题建议
6. 软性种草机会
7. 下一步
8. 本次采集边界

Avoid turning the report into a raw list. Convert each signal into a decision:

- Is this worth writing?
- What is the strongest angle?
- What can the user write that is differentiated?
- What should be avoided because it is generic, crowded, or too promotional?

## Feishu Scripts

Bundled scripts live in `scripts/`.

Required environment variables:

```powershell
setx FEISHU_APP_ID "your_feishu_app_id"
setx FEISHU_APP_SECRET "your_feishu_app_secret"
```

Optional:

```powershell
setx FEISHU_REPORT_FOLDER_TOKEN "target_folder_token"
setx FEISHU_REPORT_USER_EMAIL "your_feishu_email"
setx FEISHU_REPORT_USER_MOBILE "your_feishu_login_mobile"
setx FEISHU_REPORT_USER_PERM "full_access"
```

Create a report:

```powershell
python scripts/create_feishu_report.py path/to/report.md
```

If `FEISHU_REPORT_USER_MOBILE`, `FEISHU_REPORT_USER_EMAIL`, or
`FEISHU_REPORT_MEMBER_TYPE` + `FEISHU_REPORT_MEMBER_ID` is configured, report
creation automatically adds that user as a collaborator.

Grant the user access:

```powershell
python scripts/share_feishu_doc.py DOCUMENT_ID email user@example.com full_access
```

This requires `docs:permission.member` or `docs:permission.member:create`.
If missing, open the scope in the Feishu app console, publish the permission
change, then rerun the command.

If Feishu says `email doesn't exist`, the provided email is not a user in the
current tenant. Use the user's workplace email, or resolve it first:

```powershell
python scripts/share_feishu_doc.py --resolve-email user@example.com
python scripts/share_feishu_doc.py --resolve-mobile 13800138000
python scripts/share_feishu_doc.py DOCUMENT_ID openid OPEN_ID full_access
```

Email/mobile resolution requires the Feishu scope `contact:user.id:readonly`.

If Markdown conversion fails, create plain text blocks and tell the user which
Feishu scope is missing, usually `docx:document.block:convert`.

## RedNote-MCP Script

Use `scripts/collect_xhs_notes.py` when the user wants raw JSON snapshots from
RedNote-MCP outside the Codex MCP tool surface.

```powershell
python scripts/collect_xhs_notes.py --config config/xhs_keywords.example.json --out data/xhs_raw/sample.json --detail-limit 1
```

Keep `--detail-limit` small. If the script or MCP server times out, stop rather
than repeatedly retrying.
