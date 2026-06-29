# SECURITY.md

Threat model, secret handling, and incident response for OHRM Wiki Sync.

## Secrets inventory

| Secret | Sensitivity | Where it lives at rest | Rotation cadence |
|---|---|---|---|
| Jira API token | High — full Jira read/write as the token owner | `.env` (gitignored); Anthropic cloud (encrypted) for routines | Quarterly, or immediately on suspected leak |
| BookStack token pair (`WIKI_TOKEN_ID` + `WIKI_TOKEN_SECRET`) | **High** — full read/write to the entire wiki at the token-user's permission level | `.env` (gitignored); Anthropic cloud (encrypted) for routines | Quarterly, or immediately on suspected leak |
| GitHub PAT (`GITHUB_TOKEN`) | **High** — `contents:write` on `devnith-git/ohrm-wiki-sync`; can rewrite any tracked file (including this SECURITY.md). Fine-grained PAT scoped to the single repo limits blast radius. | Anthropic cloud (encrypted) on each routine; NEVER in `.env` for local development unless you also commit logs locally | Quarterly, or immediately on suspected leak |
| Anthropic API key | Medium — bills against the Console account, can be capped | `.env` (gitignored). Not used by routines (they use Claude.ai sub). | Quarterly |
| Atlassian Cloud ID | Low — not a secret, just an identifier | `.env` (convenient) or hard-coded | n/a |

## What's in git (and what's not)

| Location | Contents | Notes |
|---|---|---|
| `routines/<name>.prompt.md` | Prompt template **with placeholders** (`{{WIKI_TOKEN_ID}}`) | Safe to commit. The deploy script substitutes at deploy time. |
| `automation/sync.py`, `resolver.py`, `config.yaml` | Code; **no secrets** | Reads from `os.environ` (loaded from `.env` if present) |
| `automation/config.yaml` | Per-project overrides; **no secrets** | Page IDs are not secrets |
| `.env.example` | Template with placeholder values | Safe to commit |
| `.env`, `.env.local` | **Real secrets** | **Gitignored** (see `.gitignore`) |
| `resources/wiki.env.txt` (legacy) | Real secrets if you previously used the wiki.env.txt fallback | **Gitignored**. Migrate to `.env` ASAP. |
| `wiki_cache/`, `automation/out/`, `merged_specs/` | Local artifacts; **possibly sensitive** content from Jira/Wiki | Gitignored |

## How the routine handles secrets (current pattern — 2026-05-12 onward)

Live secrets live in the routine's **environment variables** (set via the
claude.ai UI), NOT in the prompt config. The prompt references env vars by
name (`$WIKI_TOKEN_ID`, `${WIKI_BASE_URL}`, ...) which the routine session
resolves at fire time via Bash.

```
+------------------+   verbatim    +-------------------+   ships to    +---------------------+
| <name>.prompt.md | ────────────▶ |    deploy.py      | ───────────▶  |  Anthropic Routines |
|  (in git, NO     |  (no-op if    |  (validates only) |   create /    |  prompt config      |
|  secrets)        |  no {{...}})  +-------------------+   update      |  (no secrets)       |
+------------------+                                                    +----------+----------+
                                                                                   │
+-------------------+   one-time setup,                                            ▼ at fire time
| Routines UI →     |   stored encrypted                                +----------------------+
| Environment vars  |   in claude.ai UI                                  |  reads $WIKI_TOKEN_* |
| ATLASSIAN_CLOUD_ID|                                                    |  builds AUTH in-mem  |
| WIKI_BASE_URL     |                                                    |  curls BookStack     |
| WIKI_TOKEN_ID     |                                                    |  prints AUDIT SUMMARY|
| WIKI_TOKEN_SECRET |                                                    |  (no secret values)  |
+-------------------+                                                    +----------------------+
```

**Where the BookStack token actually exists in plaintext (env-var pattern):**

1. In the routine's **Environment Variables** section in the claude.ai UI (encrypted at rest by Anthropic).
2. In the routine's session memory at fire time (ephemeral, in-process only).
3. Optionally in your local `.env` if you also run the standalone `automation/sync.py` CLI (filesystem ACLs only).

It is **never** in:

- The git repository
- The Anthropic Routines prompt config (`job_config.ccr.events[0].data.message.content`)
- The terminal scrollback of anyone who didn't `cat .env` themselves
- Routine logs (the routine prints only env-var lengths, never values)
- Backups of git-tracked files

## Threat model

| Threat | Impact | Mitigation |
|---|---|---|
| `.env` accidentally committed | High — token leaked to git history | `.gitignore` covers `.env`, `*.env.txt`, `wiki.env.txt`. CI should also `grep` PRs for token shapes. |
| Repo cloned by someone with no `.env` | Low — they can't deploy or run sync | Expected — the README documents the env vars required |
| Anthropic compromise | High — routine config decrypted | Mitigation = rotate BookStack token, audit BookStack revision history for unauthorized edits |
| Malicious Jira content (XSS-in-summary) | Medium — could attempt to coerce the routine into writing bad HTML | The validator (`STEP 4` in the routine, also in `sync.py`) rejects `<script>`, `<h1>`, placeholders, malformed structure. The allowlist refuses any URL other than `/api/pages/543`. |
| BookStack token has more permissions than needed | Medium — full-wiki write reachable in case of bug | Service-account user should be created with **edit-page on chapter 117 only**, not org-wide |
| Routine fires too often / loops | Low — wastes API credits, fills wiki revision history | Minimum cron interval is 1 hour. The routine itself bails out cleanly on validation failure. |

## Rotation procedure

### BookStack token

1. Log in to BookStack as the token owner. Go to **Profile → API Tokens**.
2. Click **Create Token**, name it `wiki-sync-2026-Qn`. Copy the secret immediately.
3. **Update the routine's environment variables in the claude.ai UI:**
   - Open `https://claude.ai/code/routines/<trigger_id>` (the manage URL).
   - Edit → Environment Variables.
   - Replace `WIKI_TOKEN_ID` and `WIKI_TOKEN_SECRET` with the new values.
   - Save.
4. If you also use the standalone CLI: update `.env` locally with the new token pair (only needed for `automation/sync.py`).
5. Verify the routine still works — fire `run` once via the /schedule skill or the manage UI. Look for `Status: SUCCESS` or `NO_CHANGE` and `Credentials: from-env`.
6. Revoke the old token in BookStack.
7. Audit BookStack revision history for the past 30 days, in case the old token leaked.

**Note:** no `deploy.py` redeploy is needed for a token rotation — the prompt doesn't contain the token, so the routine config is unchanged. Env vars in the UI take effect on the next routine fire.

### Jira API token

Same flow: regenerate at `id.atlassian.com/manage-profile/security/api-tokens`,
update `.env`, redeploy routine, smoke-test, revoke old.

### Anthropic API key (only affects `automation/sync.py`)

1. Console → API Keys → Create new key.
2. Update `ANTHROPIC_API_KEY` in `.env`.
3. Revoke the old key. (No deploy step needed — `sync.py` reads `.env` on every run.)

### GitHub PAT (`GITHUB_TOKEN`) for routine log commits

1. https://github.com/settings/tokens?type=beta → **Generate new token (fine-grained)**.
2. **Resource owner**: `devnith-git`. **Repository access**: *Only select repositories* → `ohrm-wiki-sync`.
3. **Repository permissions** → **Contents: Read and write**. Leave everything else unchecked.
4. **Expiration**: 90 days (the rotation cadence).
5. Copy the token (starts with `github_pat_...`). Open the routine in claude.ai (e.g. `https://claude.ai/code/routines/trig_01QhSWfCdQjX66YgGoi1YpQ3`), Edit → Environment Variables, set `GITHUB_TOKEN` to the new value. Save.
6. Repeat for every routine that commits logs (currently `cm_daily_sync` and `pnp_daily_sync`).
7. Fire-test one routine via the manage UI. Verify the AUDIT SUMMARY ends with `Log commit: <sha> <url>`.
8. Revoke the old PAT at https://github.com/settings/tokens.

**If the PAT leaks:** revoke immediately (step 8 above). Then audit `logs/` commits for the leak window — any commit not authored by `Claude Routines` (or whatever the PAT's identity surfaces as) is suspicious. The token cannot escalate to other repos because the fine-grained scope limits it to this single repo.

## Incident response

**If a secret leaks (committed to git, pasted in chat, screenshot in Slack):**

1. **Rotate immediately** (procedure above).
2. **Audit the affected system**:
   - BookStack token → revision history of every page since the leak, filtered by the service account user.
   - Jira token → activity log for the token owner.
   - Anthropic key → Console → Usage; cap to $0/month if unfamiliar usage appears.
3. **Purge the leaked secret from history**:
   - For git: `git filter-repo --invert-paths --path <file>` then force-push. Inform all collaborators to re-clone.
   - Note: rotation makes the old secret useless even if it's still in history, so this is defence-in-depth.
4. **Document the incident** in `docs/incidents/<date>-<short-name>.md` (add this folder when first needed).

## Recommended hardening (later)

- Service account `wiki-sync@orangehrm.com` in BookStack with edit-page-only on the specific target chapter (not org-wide).
- HMAC signature verification on the routine itself reading from a webhook (if/when we add Phase 3 of the design doc).
- Secrets manager integration for production deploys (GCP Secret Manager / AWS Secrets Manager / Azure Key Vault) — `.env` is fine for one-developer MVP but doesn't scale to a team.
- Pre-commit hook: `git diff --cached | grep -E '(WIKI_TOKEN_SECRET|sk-ant-|JIRA_API_TOKEN)' && exit 1`.
