# ARCHITECTURE.md

Component overview, data flow, and design decisions for OHRM Wiki Sync.

For the full multi-page design document (executive summary, trigger options,
permission analysis, etc.), see
`merged_specs/Jira_to_Wiki_Automation_Design_2026-05-11.docx` outside this
repo. This file is the engineering summary.

## High-level flow

```
+-----------+      manual or cron       +--------------------+      LLM call (Claude API or
|  Jira     | ─────────────────────────▶|  Automation        |      Routine in Anthropic cloud)
|  (source) |                            |  (one of:          |─────────────────────────────┐
+-----------+                            |   - sync.py CLI    |                              │
                                         |   - Routine        |                              ▼
                                         |   - FastAPI svc    |                    +--------------+
                                         |     [Phase 2+])    |                    |   Claude     |
                                         +---------┬──────────+                    +------┬-------+
                                                   │                                      │
                                                   │ allowlist-guarded                    │
                                                   │ PUT/POST /api/pages/<id>             │
                                                   ▼                                      │
                                         +--------------------+                            │
                                         |  BookStack         |◀──── reads source + target page
                                         |  Enterprise Wiki   |
                                         +---------┬----------+
                                                   │
                                                   ▼ audit log row
                                         +---------+----------+
                                         | wiki_update_change_log.xlsx
                                         | + memory entries    |
                                         +--------------------+
```

## Two execution modes (the repo supports both)

### 1. Standalone CLI (`automation/sync.py`)

- **Where it runs:** your laptop or a server you control.
- **Auth to LLM:** Anthropic Console API key (`ANTHROPIC_API_KEY`).
- **Outputs:** local files (HTML, DOCX, xlsx) + BookStack write.
- **Trigger:** manual (`py sync.py CM-37 --publish`), cron, or webhook receiver (Phase 2+).
- **Status:** Phase 1 complete.

### 2. Anthropic Routine (`routines/cm_daily_sync.prompt.md` + `deploy.py`)

- **Where it runs:** Anthropic's cloud.
- **Auth to LLM:** uses your Claude.ai subscription (no Console key needed).
- **Outputs:** routine run log at claude.ai/code/routines + BookStack write.
- **Trigger:** cron (minimum 1-hour interval) or one-time.
- **Status:** Deployed 2026-05-12 (`trig_01A8A5tuxU9Cct1fzVABtAe8`).

The two share `resources/` (formatting authorities) and follow the same
validation, allowlist, and audit conventions. Pick whichever fits the runtime
you control.

## Module responsibilities

| Module | Responsibility |
|---|---|
| `automation/sync.py` | End-to-end CLI: fetch Jira → fetch wiki → call LLM → validate → publish → log |
| `automation/resolver.py` | Universal Jira-project-key → BookStack book/chapter resolution. Strategies: config.yaml → cache → keyword overlap → AI classification → human-readable error. |
| `automation/config.yaml` | Per-project overrides (which BookStack page to update for a given Jira project). Optional — resolver handles the rest. |
| `resources/SKILL.md` | The skill definition. System-prompt material for the LLM. |
| `resources/WIKI_PAGE_RENDER.md` | Rendering rules companion to SKILL.md. |
| `resources/specification-writing-guideline.md` | **Canonical authority** for formatting (heading hierarchy, table column counts, bullet style). Wins on disagreements with the two above. |
| `routines/<name>.prompt.md` | Self-contained routine prompts. Placeholders for secrets. |
| `routines/deploy.py` | Substitutes placeholders from `.env` and calls the Routines API. |

## Safety guarantees (apply to both modes)

1. **Per-run write allowlist** — `ALLOWED_WRITES = {("PUT", "/api/pages/543")}` (or similar). Any non-allowlisted `(method, path)` raises before the request leaves the host.
2. **Pre-flight metadata check** — before any write, `GET /api/pages/<id>` and verify `name`, `chapter_id`, `book_id` match the target. Refuse on drift.
3. **Validation gate** — checklist (no `<h1>`, no `<th>`, anchors present, no placeholders, etc.) runs *before* the allowlist is constructed.
4. **Audit log** — append-only `wiki_update_change_log.xlsx` (CLI) or routine run log (routine) per cycle.
5. **No DELETE permission** — explicitly excluded from any allowlist.

## Resolver decision flow

```
For a given Jira project_key:
  1. Hit config.yaml? → use it.
  2. Hit cached resolution? → use it.
  3. Project name shares ≥1 strong keyword with a wiki book name? → use it.
  4. Claude classification confidence ≥ 0.5? → use it.
  5. Team-named project (Baratheons, HighTower, etc.)? → refuse with suggestion to pass CLI overrides.
  6. Else → error with helpful suggestions.
```

See `automation/resolver.py` for the implementation.

## Why the two-phase pattern (Phase A read-only, Phase B `--publish`)

Wiki writes are non-reversible shared-state changes. The two-phase pattern
gives the operator a chance to inspect the merged HTML and the comparison
table before any write. The validator runs in Phase A; Phase B is a thin
wrapper that re-runs the validator and then publishes if it still passes.

## Failure modes (handled)

| Failure | Detected at | Behaviour |
|---|---|---|
| Jira API 401 | first read | Fail fast, mark run FAILED |
| BookStack 401 | first read | Fail fast |
| Destination ambiguous | resolver | Queue / error with suggestions |
| Validator FAIL | step 4 / step 8 | Mark BLOCKED, do not publish |
| LLM returns non-JSON | step 4 | Save to `out/<hex>_bad_response.txt`, fail |
| BookStack 5xx on write | step 9 | Retry with backoff; if persists, mark FAILED |
| Non-allowlisted write attempted | request() | Hard refuse; should be unreachable in normal flow |
| Duplicate trigger | idempotency key (Phase 3+) | Return existing run id; no-op |

## What's not yet built (roadmap)

- **Phase 2** — FastAPI middleware exposing `/sync` and `/approve` endpoints for a Jira Automation manual trigger (option A in the design doc).
- **Phase 3** — Forge app issue action for the polished in-Jira UX.
- **Phase 4** — Auto-publish via webhook on `Status = Done` (for whitelisted projects only, still validator-gated).
- **Scheduled drift detection** — daily gap-analysis job that creates `wiki-gap` Jira tickets for new gaps.

Each can be added without touching the standalone CLI or routine paths — they
share the same engine.
