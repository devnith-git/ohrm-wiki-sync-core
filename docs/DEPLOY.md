# DEPLOY.md

How to set up, deploy, update, and tear down the OHRM Wiki Sync.

## Prerequisites

- Python 3.10+ (`py --version`)
- A BookStack account with API-token + edit rights on the target chapter
- A Jira account with API token + read on the target project(s)
- An Anthropic account (Console API key for `sync.py`; Claude.ai sub for routines)
- Git ≥ 2.30

## One-time setup (developer machine)

```powershell
git clone <repo-url> ohrm-wiki-sync
cd ohrm-wiki-sync

# Copy and fill in the env template
cp .env.example .env
notepad .env     # Or your editor of choice
```

Fill in `.env`:

```
JIRA_USER=devnith@orangehrm.com
JIRA_API_TOKEN=<from id.atlassian.com>
ATLASSIAN_CLOUD_ID=8cb10ab9-f92f-44b6-8fe2-d076ed2e5175
ANTHROPIC_API_KEY=sk-ant-...
WIKI_TOKEN_ID=<from BookStack profile>
WIKI_TOKEN_SECRET=<from BookStack profile>
WIKI_BASE_URL=https://enterprisewiki.orangehrm.com
ROUTINE_ENVIRONMENT_ID=env_01VQwdo2ZPUCQiu3YNY8rwzU
ATLASSIAN_MCP_UUID=af43bc0a-a7ec-4b6a-b841-7e574624993f
WIKI_MCP_UUID=b6ed3c23-ccf2-4ebb-8d8a-ac2bf810496a
ROUTINE_TRIGGER_ID=    # leave blank until first --create
```

Install Python deps:

```powershell
py -m pip install -r automation/requirements.txt
```

Smoke-test:

```powershell
# Validates env loading + connectors. Doesn't touch the wiki.
py automation/sync.py CM-37
```

You should see the workflow run through Steps 1-8 and stop with
`PHASE A complete. Validation: PASS.` and zero writes.

## Deploy / update the daily routine

```powershell
# First time:
py routines/deploy.py --dry-run cm_daily_sync     # verify substitution
py routines/deploy.py --create cm_daily_sync --cron "30 1 * * *"

# Copy the printed trigger_id into .env:
#   ROUTINE_TRIGGER_ID=trig_01XYZ...

# Future updates (after editing the prompt or rotating secrets):
py routines/deploy.py --update cm_daily_sync
```

## Cron-expression reference

The script accepts standard 5-field cron in **UTC**. Minimum interval is 1 hour.

| Local time (Asia/Colombo, UTC+5:30) | Cron (UTC) |
|---|---|
| Every day at 07:00 | `30 1 * * *` |
| Weekdays at 09:00 | `30 3 * * 1-5` |
| Every 2 hours | `0 */2 * * *` |
| First of every month at 08:00 | `30 2 1 * *` |

For one-time runs, replace `--cron "..."` with `--run-once-at "2026-05-20T01:30:00Z"`.

## Production / cloud deployment of the standalone CLI

If you also want `automation/sync.py` running on a server (not just on
your laptop), put the repo on a small VM or Cloud Run / Azure Container App:

1. Build a Docker image:
   ```dockerfile
   FROM python:3.12-slim
   WORKDIR /app
   COPY automation /app/automation
   COPY resources /app/resources
   COPY .env /app/.env
   RUN pip install --no-cache-dir -r automation/requirements.txt
   CMD ["python", "automation/sync.py", "$JIRA_KEY", "--publish"]
   ```
2. **Do NOT bake `.env` into the image.** Mount it as a runtime secret
   (Cloud Run secret manager, Azure KeyVault, AWS Secrets Manager).
3. For scheduling, prefer the Anthropic routine path (no infra needed).
   Use the Python container only if you need outputs (DOCX/XLSX) on the
   server's local filesystem.

## Rotating secrets

See `SECURITY.md` § Rotation procedure.

## Tearing down

- **Disable the routine** (keep the config for reference):
  ```powershell
  # Easiest: open https://claude.ai/code/routines/<trigger_id> and click Disable
  ```
- **Delete the routine** — the Routines API does not expose a delete endpoint;
  delete via the web UI at `claude.ai/code/routines`.
- **Revoke tokens** — Jira at id.atlassian.com, BookStack at profile, Anthropic
  at console.
- **Remove `.env`** — wipe locally:
  ```powershell
  rm .env
  ```
- **Audit** — `git log --all --source -- '*.env' '*wiki.env.txt*'` should
  return zero hits. If anything appears, do `git filter-repo` history rewrite.

## Verifying a deployed routine

```powershell
# Via Claude Code skill:
# Type /schedule, pick "List routines", read the output

# Or directly via the Routines API (substitute trigger id):
py -c "import os, urllib.request, json; req = urllib.request.Request(f'https://api.anthropic.com/v1/code/triggers/{os.environ[\"ROUTINE_TRIGGER_ID\"]}', headers={'x-api-key': os.environ['ANTHROPIC_API_KEY'], 'anthropic-version': '2023-06-01'}); print(json.dumps(json.loads(urllib.request.urlopen(req).read()), indent=2))"
```
