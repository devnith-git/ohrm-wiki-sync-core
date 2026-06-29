# Routines

Anthropic Claude scheduled-agent definitions. Each `<name>.prompt.md` is a
self-contained prompt that ships verbatim to the routine config. **Secrets are
never in the prompt** — they live as environment variables on the routine in
the claude.ai UI and are read at runtime.

## Files

| File | Purpose |
|---|---|
| `cm_daily_sync.prompt.md`  | Daily sync of Jira epic CM-35 → BookStack page 543 (hard-coded target) |
| `pnp_daily_sync.prompt.md` | Daily sync of Jira project PNP (Performance Core) → BookStack Performance book (destination discovered at runtime) |
| `deploy.py`                | Create / update / dry-run a routine from a prompt file |

## How the secret-handling works

```
+------------------+   verbatim    +-------------------+   ships to    +---------------------+
| <name>.prompt.md | ────────────▶ |    deploy.py      | ───────────▶  |  Anthropic Routines |
|  (in git, NO     |  no substitu- |  (just validates) |   create /    |  config             |
|  secrets, NO     |  tion needed  |                   |   update      +---------+-----------+
|  placeholders)   |               +-------------------+                         │
+------------------+                                                              ▼ at fire time
                                                                       +---------------------+
+-------------------+                                                   |  Routine session    |
| Routines UI →     |  one-time setup, persists                         |  reads env vars     |
| Environment vars  |─────────────────────────────────────────────────▶ |  (echo $WIKI_*)    |
| ATLASSIAN_CLOUD_  |  WIKI_BASE_URL, WIKI_TOKEN_ID, WIKI_TOKEN_SECRET  |  + builds AUTH      |
| ID, WIKI_*        |                                                   |  header in-memory   |
+-------------------+                                                   +---------------------+
```

- **The prompt template in git contains no secrets and no placeholders.** It
  references env vars by name (`$WIKI_TOKEN_ID`, `${WIKI_BASE_URL}`, etc.)
  which the routine resolves at fire time.
- **Secrets live ONLY in the claude.ai routines UI** — Edit Routine → Environment
  Variables. They are stored encrypted by Anthropic and never appear in the
  prompt config.
- **No `.env` substitution at deploy time.** `deploy.py` just validates and
  ships the prompt verbatim. The only env vars `deploy.py` reads are the
  deploy-time ones (`ROUTINE_ENVIRONMENT_ID`, `ATLASSIAN_MCP_UUID`,
  `WIKI_MCP_UUID`).

## Required runtime env vars (set in the routine's UI)

| Env var | Sensitive? | Example |
|---|---|---|
| `ATLASSIAN_CLOUD_ID` | low (just an id) | `8cb10ab9-f92f-44b6-8fe2-d076ed2e5175` |
| `WIKI_BASE_URL` | low | `https://enterprisewiki.orangehrm.com` |
| `WIKI_TOKEN_ID` | **HIGH** | (from BookStack profile) |
| `WIKI_TOKEN_SECRET` | **HIGH** | (from BookStack profile) |

The routine validates these on first step and aborts with `FAILED: missing
env var` if any are absent — it will never run silently with broken
credentials.

## Optional runtime env vars

| Env var | Sensitive? | Purpose |
|---|---|---|
| `GITHUB_TOKEN` | **HIGH** | Fine-grained PAT (`contents:write` on `devnith-git/ohrm-wiki-sync`) used to commit a per-run audit log to `logs/<routine>/<ts>.md`. If unset the log-commit step is silently skipped. |

### Per-run audit logs (the `logs/` tree)

Both routines commit a structured log file at the end of each run. The path
is `logs/<routine_name>/<UTC iso timestamp>.md`, e.g.
`logs/cm_daily_sync/2026-05-12T013023Z.md`. The file has YAML frontmatter
(routine id, run timestamp, status, wiki page ids, HTTP counters, story
counts) followed by the verbatim AUDIT SUMMARY block + a story/epic table +
a diff summary. The commit history of `logs/` is the persistent audit
trail; the AUDIT SUMMARY's `Log commit:` line points to the commit url for
each run.

The log-commit step is best-effort: if GitHub rejects the PUT for any
reason, the routine logs `Log commit: FAILED <code>` and exits cleanly —
the wiki sync itself is never blocked on the log write.

## Common workflows

### Initial deploy

```powershell
# 1. Set deploy-time env vars (one-time)
cp ..\.env.example ..\.env
# Edit .env — fill in only ROUTINE_ENVIRONMENT_ID, ATLASSIAN_MCP_UUID, WIKI_MCP_UUID.
# Do NOT put WIKI_TOKEN_* in .env — they live in the routines UI.

# 2. Validate the prompt
py deploy.py --dry-run cm_daily_sync

# 3. Create the routine
py deploy.py --create cm_daily_sync --cron "30 1 * * *"

# 4. CRITICAL: open the printed manage URL and add the runtime env vars
#    via Edit → Environment variables. Without this the routine will refuse
#    to run with "FATAL: env var WIKI_TOKEN_ID is not set".
```

### Update the prompt after editing `cm_daily_sync.prompt.md`

```powershell
py deploy.py --update cm_daily_sync
```

### Rotate the BookStack token

1. Generate a new token pair in BookStack.
2. Open the routine in the claude.ai UI → Edit → Environment Variables.
3. Update `WIKI_TOKEN_ID` and `WIKI_TOKEN_SECRET`.
4. Revoke the old token in BookStack.

No `deploy.py` run is needed — env vars live entirely in the UI now.

## Adding a new routine

1. Copy `cm_daily_sync.prompt.md` → `<new_name>.prompt.md`.
2. Edit the prompt body. Reference any required secrets via `$VAR_NAME`.
3. `py deploy.py --create <new_name> --cron "..."`.
4. Set the routine's environment variables in the claude.ai UI.

## Constraints

- Routines are time-based only (cron with **minimum 1-hour interval** or one-time
  `run_once_at`). They do not accept inbound webhooks.
- The agent has only the tools listed in `allowed_tools` plus the MCP
  connectors listed in `mcp_connections`. No local filesystem outside the
  ephemeral sandbox.
- Env vars are per-routine (in the routine's UI), not shared across routines
  in the same environment.
- Output appears at `https://claude.ai/code/routines/{trigger_id}`.
