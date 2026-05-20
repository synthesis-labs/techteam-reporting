# Raw exports — 2026-05

Drop monthly tool exports here, named exactly as below. `load.py` looks for
these filenames; anything not present is skipped.

| File             | Source                                               |
|------------------|------------------------------------------------------|
| `employees.csv`  | HR employee master                                   |
| `claude.csv`     | Claude admin console → Members export                |
| `cursor.csv`     | Cursor team admin → Members export                   |
| `chatgpt.csv`    | ChatGPT admin → Members export (alternating rows)    |
| `copilot.csv`    | GitHub org → Copilot seats (alternating rows, NBSP)  |
| `gemini.csv`     | Google Workspace export                              |

Files are untouched as-downloaded. The loader handles each format's quirks.
