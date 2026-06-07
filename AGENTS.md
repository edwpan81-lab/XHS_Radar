# XHS Hotspot Radar Agent Notes

## Project Goal

This workspace is for building a semi-automated Xiaohongshu/RedNote hotspot radar that helps with topic discovery, viral-note analysis, drafting, and review.

The working model should be:

1. Track a small set of relevant keywords.
2. Read public notes and comments at low frequency.
3. Extract pain points, hooks, formats, and audience demand.
4. Score topic candidates.
5. Produce concise daily reports, draft outlines, titles, and content angles.

Avoid building a full crawler. The useful output is editorial judgment, not large-volume scraping.

## Current Tooling

- Prefer RedNote-MCP for Xiaohongshu access.
- RedNote-MCP is installed and initialized.
- Its login cookies are saved outside the workspace by the tool. Do not read, print, copy, or expose cookie contents.
- Available RedNote-MCP operations include searching notes, reading note content, and reading comments.
- `xhs-cli` exists locally, but it previously failed to read the browser login state because it could not find the required `a1` cookie. Treat it as secondary/fallback only.
- Chrome control works for some pages, but Xiaohongshu and WeChat pages can be slow or hostile to DOM/screenshot extraction. Do not rely on browser DOM scraping as the primary pipeline.

## Safety Rules

Default to read-only behavior.

Allowed without further confirmation:

- Search public Xiaohongshu notes.
- Read public note content.
- Read public comments for selected notes.
- Create or update files inside this workspace for configs, reports, templates, and scripts.
- Summarize, score, cluster, and draft from public note data.

Not allowed unless the user explicitly asks and confirms:

- Like, favorite, follow, comment, reply, post, delete, or otherwise perform account write actions.
- Read or display cookie files, browser storage, passwords, tokens, or unrelated personal files.
- Run high-volume collection.
- Change global Codex, browser, npm, Playwright, or system configuration.
- Install dependencies.

Use low request volume:

- 1-5 keywords per run by default.
- 3-10 notes per keyword by default.
- Comments only for selected promising notes.
- Avoid repeated rapid calls against the same endpoint.

## Editorial Principles

For every analyzed note, prefer extracting:

- Title/hook pattern.
- Target audience.
- User pain point or desire.
- Promise/value proposition.
- Content structure.
- Comment-section demand.
- Reusable topic angle.
- Why it may be performing well.
- How the user can create a differentiated version.

Do not simply list hot notes. Convert raw notes into decisions:

- Is this worth writing?
- What is the strongest angle?
- What evidence supports it?
- What title/opening would fit Xiaohongshu?
- What should be avoided because it is too generic, too crowded, or too promotional?

## Recommended Workspace Structure

When creating project files, prefer this structure:

```text
config/
  xhs_keywords.json
  scoring_rules.json

inbox/
  xhs_links.md

data/
  xhs_raw/
  xhs_notes/
  xhs_comments/

reports/
  daily/
  topic_candidates/
  drafts/
  reviews/

templates/
  daily_report.md
  note_analysis.md
  draft_outline.md

scripts/
```

## Report Style

Reports should be practical and compact. Prefer:

- Top findings first.
- Clear topic recommendations.
- Short evidence snippets.
- Specific next actions.
- No unnecessary technical details.

Useful daily report sections:

1. Today’s Signals
2. High-Potential Topics
3. Note Breakdowns
4. Comment Insights
5. Draftable Angles
6. Suggested Titles
7. Risks / Saturation

## Known Environment Notes

- Codex Windows `node_repl` previously failed when `[windows] sandbox = "elevated"`.
- The temporary fix was to use:

```toml
[windows]
sandbox = "unelevated"
```

- RedNote-MCP was installed from npm and initialized successfully.
- Playwright browser download via npmmirror failed for the requested build. A local junction was created so RedNote-MCP could use an existing Playwright Chromium:

```text
C:\Users\NewAdmin\AppData\Local\ms-playwright\chromium-1223
  -> C:\Users\NewAdmin\AppData\Local\ms-playwright\chromium-1208
```

Do not alter this unless debugging RedNote-MCP initialization.

## Working Agreement

When operating in broader permission modes, voluntarily keep the project in "read-only hotspot radar mode":

- Search and read only.
- Keep requests low-frequency.
- Never expose auth material.
- Ask before writing outside the workspace or changing global setup.
- Ask before any account action.
