# Specification Update Routine Rollout Guideline for Project Leads

> **Audience:** Project Leads (PLs), QA Leads, Release Managers, and the Routine Owner/Admin who configures the automation.
> **Status:** Production guide. Reflects the system as of `2026-05-17`. Cross-references the canonical resource files in `resources/`, `routines/`, and `docs/`.
> **Prerequisite reading (optional):** `docs/ARCHITECTURE.md` (system design), `docs/SECURITY.md` (secret handling), `docs/DEPLOY.md` (initial deploy), `docs/EMAIL_SETUP.md` (Gmail API setup).

---

## 1. Purpose of the Routine

### What it does
The Specification Update Routine reads completed and released Jira stories for a configured project, distils the released behaviour into the canonical 5-table specification format, and writes the result to the project's target wiki page on BookStack. Each fire also commits a per-run audit log to GitHub and emails a structured report to PLs/stakeholders.

### Why we use it
Specification documents drift away from product reality the moment they're hand-maintained. PLs spend hours per release manually translating Jira tickets into spec rows; spec authors then re-translate them for QA; QA then has to chase the PL to confirm the latest behaviour. The routine collapses that loop into a single fire — Jira → canonical spec page — with deterministic, validated, additive merges.

### How it helps
- The canonical spec page always reflects the **latest released behaviour** from Jira (per the bullet-form Scenario rule in `specification-writing-guideline.md` §2.2).
- New stories appear as new ATC rows; refinements to existing features update the existing row in place (per the de-duplication contract in `release-filter-policy.md` §10.3 / `SKILL.md` §5-C).
- Cross-table fields (Form / Search / List / Audit Trail) are kept consistent without the PL having to remember every table the story affects (`SKILL.md` §5-C.4).
- The email report tells PLs exactly which stories were updated, which were skipped (with reason), and which need manual action — so a PL can read one email after the fire and know what's done and what they still own.

### Why Jira is the source of truth
The release gate is **Jira-only** (`release-filter-policy.md` §1–§9). The routine never consults the wiki, BookStack revision history, or any external system to decide whether a story is released. Jira's `fixVersion.released` flag (or a past `releaseDate`) is the authoritative signal. Story completion is decided by `statusCategory.key == "done"` (or one of the canonical "completed" status names: Done / Closed / Completed / Released). Anything else is a source of drift and is explicitly rejected.

### Why released/completed stories — not ongoing ones
A spec is a record of what the system **does**, not what it **might do**. Routine processing of ongoing stories would write speculative content that the spec author would then have to revert when the story scope changes mid-development. Released-only filtering means: the spec is always behind the latest commit (intentionally) but always ahead of the previous release.

### What problem this solves
- **PLs:** No more manual spec re-writes per release. Routine handles 80–90% of the mechanical work; PL reviews the diff and handles the 10–20% that needs judgment.
- **QA/Product:** A single source for "what does feature X do in release Y" — the canonical wiki page. No more digging through Jira tickets for the latest UI screenshot or the latest validation rule.
- **Release Managers:** The per-Epic project scan in every run (`SKILL.md` STEP 3-D) gives an at-a-glance view of which Epics are released vs pending across the whole project.

---

## 2. End-to-End Workflow Overview

### High-level flow

1. **Routine Owner/Admin** creates a project-level routine using `routines/scaffold.py` (or `deploy.py --create`).
2. Routine Owner connects: Jira (Atlassian MCP), GitHub (PAT), BookStack (token pair), Gmail OAuth (recipients).
3. **Project Lead** prepares Jira stories: clear description, assigned `fixVersion`, attached UI screenshots, Done status.
4. PL confirms the `fixVersion` is `released=true` (or `releaseDate ≤ today`) in Jira.
5. PL attaches UI assets to the Jira story description or as attachments.
6. PL runs the routine from the claude.ai routines UI (manual fire), or waits for the scheduled cron fire.
7. Routine fetches Jira data via the Atlassian MCP.
8. Routine applies the release-filter gate; only `released-AND-completed-AND-not-excluded` stories proceed.
9. Routine composes the merged HTML, validates against 14 STEP 6 checks, and PUTs to the BookStack page.
10. Routine re-hosts Jira UI images to BookStack (skipping any that fail the Atlassian allowlist).
11. Routine emits the run output: AUDIT SUMMARY, GitHub log file, and a structured email to recipients.
12. PL reviews the email, opens the wiki link, and actions any `manual_action` rows.

### Text diagram

```
+-----------------------+      manual or cron        +----------------------+
|   Jira (project key)  | -------------------------> |   Anthropic Routine  |
|   - stories           |   reads via Atlassian MCP  |   (claude.ai/code/   |
|   - fixVersions       |                            |    routines)         |
|   - attachments       |                            |                      |
+-----------------------+                            +----------+-----------+
                                                                 |
                              clones at fire-time   reads        |
                              resources/* from      stories      |
                              github.com/...        validates    |
                              ohrm-wiki-sync        composes     |
                                                    HTML         |
                                                                 v
+----------------------+    PUT /api/pages/<id>     +-------------------+
|  BookStack wiki      | <----------------------+   |   STEP 5/6/7      |
|  - page <id> updated |    (additive merge,    |   |   merge+validate  |
|  - images uploaded   |     allowlist-guarded) |   |   +write          |
+----------------------+                        +---|                   |
                                                    +--------+----------+
                                                             |
                                              +--------------+--------------+
                                              v              v              v
                                       +------------+  +----------+  +-----------+
                                       |  GitHub    |  | Gmail    |  |  AUDIT    |
                                       |  log .md   |  | email    |  |  SUMMARY  |
                                       |  commit    |  | recipients|  | stdout    |
                                       +------------+  +----------+  +-----------+
```

---

## 3. Intended Users and Access Levels

| Role | Can do | Should NOT do | Jira | GitHub | Claude Code | Routine UI run | Edit Instructions in UI |
|---|---|---|---|---|---|---|---|
| **Routine Owner/Admin** | Create routines, configure tokens, deploy via `routines/deploy.py`, rotate secrets, debug | Run unrelated projects' routines without coordination | Yes (admin) | Yes (PAT owner) | Yes | Yes | Yes |
| **Project Lead (PL)** | Run the routine for their project, adjust scope/Instructions in UI, action manual_actions | Touch tokens, deploy, modify resource files in `resources/`, change destination map | Yes (project read) | **No** — the routine commits via its own PAT; PLs don't need git access | **No** — routine runs entirely from the routines UI | Yes | Yes (scope-only) |
| **QA Lead** | Review the updated wiki page after a fire, validate test cases match Jira, request a re-fire if needed | Edit the wiki directly during a release window (routine writes are additive but timing matters) | Yes (read) | No | No | Read-only (view runs) | No |
| **Product/Feature Owner** | Read the spec, request feature-specific re-runs through the PL | Bypass the PL to fire routines | Yes (read) | No | No | Read-only | No |
| **Release Manager / Project Admin** | Mark `fixVersion.released=true` in Jira (the only path to ungate a release), set `releaseDate`, resolve BLOCKED items in the Manual Actions section | Force-run routines with `released=false` and empty `releaseDate` (the routine refuses by design) | Yes (admin on the project) | No | No | Read-only | No |
| **Developer/Maintainer** | Modify resource files (`resources/SKILL.md`, etc.), update `routines/*.prompt.md`, build new tooling (`scaffold.py`, `fetch_wiki_inventory.py`) | Run routines with experimental SKILL.md against production pages | Yes | Yes | Yes | Yes (test runs) | Yes |

**Critical clarifications:**
- **PLs do not need Claude Code for normal routine execution.** They open `https://claude.ai/code/routines/<trigger_id>` in a browser, click "Run now", read the email, and react.
- **PLs do not need direct GitHub access** if the routine is already created and connected. The routine commits via its own `GITHUB_TOKEN` (stored as a routine environment variable). PLs read the GitHub log via the URL in the email; no clone, no push, no PR.
- **PLs can adjust only the Instructions/scope** in the routine UI. The 6 canonical resource files (`SKILL.md`, `WIKI_PAGE_RENDER.md`, `release-filter-policy.md`, `specification-writing-guideline.md`, `wiki_destination.json`, `email_template.html`) live in the GitHub repo and are read by the routine at fire time. PLs MUST NOT attempt to override workflow behaviour from the UI Instructions — that contradicts the authority order and will produce inconsistent runs.
- **Claude Code is for the Routine Owner/Admin + Developer** — setup, debugging, implementation changes, advanced maintenance. PLs never need it for day-to-day operation.

---

## 4. API Keys, Tokens, Secrets, and Security

This section is non-negotiable. Read it carefully before touching any token.

### Direct answers to the four questions

#### Q: Should my API keys be public to others?
**No.** API keys must never be public. They must never appear in:
- Git commits (the repo is configured to gitignore `.env` — verify `git status` before any commit).
- Slack, Teams, or any chat channel.
- Email bodies, attachments, or signatures.
- Screenshots of terminals, IDEs, or browser dev tools.
- Routine Instructions in the claude.ai UI (the Instructions field is visible to anyone with read access to the routine).
- Comments inside any file in the repo.

Tokens belong in **environment variables** — `.env` locally (gitignored) for the CLI; the **Environment Variables** section of the claude.ai routine UI for the production routines. The routine UI encrypts env vars at rest on Anthropic's side.

#### Q: If the routine uses my API key, will logs show my name?
**Yes.** Every external system attributes actions to the token's owner:

- **Jira** — actions appear under the user account that generated the Atlassian API token. If you generated the token at `id.atlassian.com/manage-profile/security/api-tokens` while signed in as `pl-name@orangehrm.com`, every JQL query and attachment download is attributed to `pl-name@orangehrm.com` in the Jira audit log.
- **GitHub** — log commits appear with the author = the GitHub user who created the fine-grained PAT. The commit body author email and the "author" field on github.com both reflect that user.
- **BookStack** — page edits appear under the user who minted the `WIKI_TOKEN_ID` / `WIKI_TOKEN_SECRET` pair. BookStack's page revision history attributes every routine PUT to that user.
- **Gmail** — emails are sent **From:** the address that authorised the OAuth refresh token (the `EMAIL_SENDER` env var must match).

If you use **your personal account's tokens**, your name appears against every action the routine performs. Wiki readers will see "edited by `your-name@orangehrm.com` 5 minutes ago" on every routine write.

#### Q: If other PLs sign in using their own accounts, will it configure/log using their name?
**Depends on how the routine is set up.** Two patterns exist:

1. **Shared service-account tokens** (recommended) — The Routine Owner sets `WIKI_TOKEN_ID` / `JIRA_API_TOKEN` / `GITHUB_TOKEN` to tokens from a dedicated service account (e.g. `wiki-sync@orangehrm.com`). PLs see and fire the routine through the claude.ai UI, but every write is attributed to the service account. Audit logs and revision history stay consistent regardless of which PL clicked "Run now".

2. **Per-user personal tokens** — Each PL contributes their own tokens to "their" routine. Their name appears against every action they trigger. This works for one-PL projects but does NOT scale — when a PL leaves the team, the token is revoked and the routine breaks until someone else swaps in fresh credentials.

The claude.ai routines UI provides "Run now" — clicking it does not change who the tokens belong to. The configured tokens are what matter. **Who runs the routine is recorded by Anthropic's routine UI (run history), but who appears in Jira/GitHub/BookStack is determined by the tokens.**

#### Q: What is the recommended approach?
**Use a dedicated service account / bot account for every shared project routine.** This is the production-grade pattern:

- Create `wiki-sync@orangehrm.com` (or similar) as a real user in Atlassian, GitHub, BookStack, and Google Workspace.
- Generate tokens from that service account, not from any human user.
- Configure those tokens as the routine's env vars in the claude.ai UI.
- Give 2–3 admin colleagues access to the GCP project / Atlassian site / GitHub org so the routine survives a team member leaving.
- Document the service account credentials in your team's password manager.

This avoids the "every wiki edit looks like it came from one specific PL" anti-pattern, makes audit trails meaningful (you can grep BookStack revisions for "service account vs human" to find drift), and eliminates the rotation panic when a PL leaves.

### Tokens at a glance

| System | Recommended Token Owner | Minimum Scope | Audit/Log Name Shown | Where the Token Lives | Rotation Cadence |
|---|---|---|---|---|---|
| **Jira (Atlassian)** | Service account (recommended) or authorised PL | Read on the configured project | Token-account owner in Jira audit log | `JIRA_API_TOKEN` env var in routine UI; `.env` locally for the CLI | Quarterly, or on suspected leak |
| **GitHub** | Fine-grained PAT scoped to `devnith-git/ohrm-wiki-sync` (or your fork), `contents: write` only | Repo `contents: write`, nothing else | Commit author = token-account owner | `GITHUB_TOKEN` env var in routine UI | 90 days (current PAT expiry per `docs/SECURITY.md`) |
| **BookStack (Wiki)** | Service account with edit-page rights on the target chapter | Edit page + image-gallery upload on the Specification shelf (`id=3`) | Page-revision author = token-account owner | `WIKI_TOKEN_ID` + `WIKI_TOKEN_SECRET` env vars in routine UI | Quarterly |
| **Claude (Anthropic Routine)** | Routine Owner/Admin's Claude.ai account | Routine create/update/run | Run history attributed to UI clicker; routine prompt body and env vars set by the Owner | The trigger config in `claude.ai/code/routines/<id>` | n/a for the account; rotate env-var secrets per the rows above |
| **Gmail OAuth (for STEP 10 emails)** | Workspace service mailbox (recommended) OR personal Gmail (Plan A, 7-day token expiry) | `gmail.send` scope only | "From:" = `EMAIL_SENDER` env var (must match the OAuth-authorised account) | `GOOGLE_CLIENT_ID` / `_SECRET` / `_REFRESH_TOKEN` / `EMAIL_SENDER` env vars in routine UI | Workspace Internal: never expires. External + Testing: 7 days (must re-run `routines/oauth_setup.py`) |

### Rotation policy
- **Routine token rotation** (Jira, BookStack, GitHub): follow `docs/SECURITY.md` § "Rotation procedure". Quarterly on a calendar reminder, immediately on suspected leak.
- **Plan A Gmail refresh token**: weekly, until you migrate to Plan B (Workspace service mailbox — `docs/EMAIL_SETUP.md`). Run `python routines/oauth_setup.py` from a machine that has the cached `routines/.oauth_local.json`.
- **Service account passwords**: store in a team password manager. Rotate when admin team changes.

### When a PL leaves the team
1. Routine Owner revokes the PL's personal tokens in Jira, GitHub, BookStack, Google.
2. If the routine was using a service account, **nothing breaks** — the service account survives the team change.
3. If the routine was using the PL's personal tokens, the routine breaks at the next fire. Replace with service account tokens (or another PL's tokens) immediately.
4. Remove the departed PL from the routine recipient list (`EMAIL_RECIPIENTS` env var or `resources/email_recipients.json`).
5. Audit the recent BookStack/GitHub revision history for the past 30 days to confirm no unauthorised activity during the offboarding window.

### When a token expires
- **Jira / BookStack / GitHub** — routine starts returning 401/403 on the next fire. STEP 1 surfaces the failure in the AUDIT SUMMARY. Operator regenerates the token and updates the routine env var via the claude.ai UI. No code change, no redeploy.
- **Gmail refresh token (Plan A)** — `send_notification.py` exits with code 8 and prints the exact recovery one-liner. Re-run `python routines/oauth_setup.py` (no arguments — uses cached client id/secret).

### When permission errors occur
- **Jira 403 on a specific project** — the token user lacks "Browse Projects" permission on that project. Ask the Jira admin to add it.
- **BookStack 403 on the target page** — the service account lacks edit rights on the chapter. BookStack admin adds the user to the chapter's edit list.
- **GitHub 401/403 on the log commit** — PAT scope is wrong or expired. Re-mint per `docs/SECURITY.md` § "GitHub PAT".
- **Atlassian 403 on image attachment download** — `api.atlassian.com` is not in the routine execution environment's outbound network allowlist. Environment admin must add it. See §13 below for the workaround.

### What NOT to screenshot or share
- Terminal output containing any line that starts with `GOOGLE_REFRESH_TOKEN=`, `WIKI_TOKEN_SECRET=`, `JIRA_API_TOKEN=`, `sk-ant-`, or `github_pat_`.
- The `.env` file's contents (you'll see them in screenshots of your editor).
- The Environment Variables panel of the claude.ai routine UI when values are unmasked.
- Any AUDIT SUMMARY line containing actual secret VALUES (the routine is designed to print only `len=N` diagnostics — if you see real values, that's a bug; report it).

---

## 5. Initial Setup by Routine Owner/Admin

This is the path from "fresh repo" to "first PL fires the routine". Each step is owned by the Routine Owner unless otherwise noted.

### Steps

1. **Create the project-level routine.** Use `python routines/scaffold.py` (the recommended one-command path) OR follow the manual flow in `docs/DEPLOY.md`.
   ```powershell
   py routines/scaffold.py `
       --slug <project>_daily_sync `
       --project-key <PROJECT_KEY> `
       --project-name "<Human Project Name>" `
       --page-id <bookstack_page_id> `
       --page-name "<BookStack page name>" `
       --book-id <book_id> `
       --book-name "<book name>" `
       --release-scope <fixversion> `
       --cron "30 1 * * *"
   ```
   The scaffold script validates the slug shape, checks the page exists in the Specification shelf (id=3), confirms the Jira project + fixVersion exist, generates `routines/<slug>.prompt.md` from the CM template with project-specific tokens substituted, and adds the entry to `resources/wiki_destination.json`.

2. **Name the routine clearly.** Convention: `<jira-project-key-lowercase>_daily_sync` (e.g. `cm_daily_sync`, `pnp_daily_sync`, `roster_daily_sync`). The human-readable name is set automatically by `scaffold.py` (`OHRM <Project Name> Daily Wiki Sync`).

3. **Connect Jira access.** The routine uses the Atlassian MCP — already wired in `routines/mcp_connectors.json`. The token comes from the `ATLASSIAN_CLOUD_ID` env var in the routine UI.

4. **Connect GitHub repository access.** Mint a fine-grained PAT at `https://github.com/settings/tokens?type=beta`:
   - Resource owner: the org/user that hosts the repo.
   - Repository access: *Only select repositories* → the one repo.
   - Repository permissions: **Contents: Read and write**.
   - Expiration: 90 days.
   Paste into `GITHUB_TOKEN` env var in the routine UI.

5. **Connect BookStack/wiki access.** Generate a token pair under the service account's BookStack profile → API Tokens. The service account must have edit-page rights on the target chapter. Paste into `WIKI_TOKEN_ID` and `WIKI_TOKEN_SECRET`.

6. **Configure secure secrets/API tokens.** All four required env vars on the routine: `ATLASSIAN_CLOUD_ID`, `WIKI_BASE_URL`, `WIKI_TOKEN_ID`, `WIKI_TOKEN_SECRET`. Plus optional `GITHUB_TOKEN` (for STEP 9 log commit) and the Gmail OAuth set (`GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, `GOOGLE_REFRESH_TOKEN`, `EMAIL_SENDER`).

7. **Configure project key.** Set in the routine prompt body's `JIRA_PROJECT` parameter (`scaffold.py` does this automatically).

8. **Configure default fixVersion or release scope.** Set in `resources/wiki_destination.json` under `routine_destinations.<slug>.release_scope`. Updates take effect on the next fire — no redeploy needed.

9. **Configure target GitHub/spec path.** Per-routine log path is `logs/<slug>/<UTC>.md` and is automatic. Resource files in `resources/` are read at fire time from a fresh GitHub clone.

10. **Configure BookStack/wiki page mapping.** Set in `resources/wiki_destination.json` → `routine_destinations.<slug>.page_id` + `page_name` + `book_id` + `chapter_id` (null if the page lives directly in the book). The `scaffold.py` script writes this entry automatically.

11. **Add global routine instructions.** The 6 canonical resource files are the authority — they are loaded at fire time and override anything in the routine prompt body. Customise the per-routine prompt only for project-specific parameters (project key, fixVersion, page id, cron). Do not duplicate workflow logic.

12. **Add release filtering rules.** Already global — defined in `resources/release-filter-policy.md`. No per-routine work needed.

13. **Add Acceptance Test Case duplicate prevention rules.** Already global — `release-filter-policy.md` §10.3, `SKILL.md` §5-C.1 to §5-C.4. No per-routine work needed.

14. **Add UI asset handling rules.** Already global — `release-filter-policy.md` §11.1 / §11.1-bis / §11.1-ter. Also global. No per-routine work needed.

15. **Configure run output/email template.** The template lives at `resources/email_template.html` and is shared across every routine. Recipient list comes from `EMAIL_RECIPIENTS` env var (preferred) or `resources/email_recipients.json` (fallback).

16. **Configure manual/scheduled trigger.** The `--cron "30 1 * * *"` argument to `scaffold.py`/`deploy.py` sets the cron in UTC. Minimum interval is 1 hour per claude.ai routines policy. For one-time runs, use `--run-once-at "<ISO8601>"` instead.

17. **Test with a dry run.** Set `DRY_RUN=true` in the routine env vars. Click "Run now" in the claude.ai UI. The routine executes STEP 1–6 normally, skips STEP 7 (no BookStack write), but still emits the AUDIT SUMMARY, GitHub log (with `dry_run: true` in YAML), and email (subject prefixed `[DRY RUN]`). Verify the merged HTML is sensible before flipping `DRY_RUN=false`.

18. **Confirm output before enabling PL usage.** Walk one PL through their first real run with you watching. Once the email lands correctly and the wiki page shows the expected changes, hand them the routine URL and the link to this guide.

### Configuration table

| Configuration Item | Example | Required? | Configured By | Notes |
|---|---|---|---|---|
| Routine slug (`name`) | `cm_daily_sync` | Yes | Routine Owner | Must match `^[a-z][a-z0-9_]*_(daily|weekly|hourly)_sync$` (validated by `scaffold.py`) |
| Routine human name | `OHRM CM Daily Wiki Sync` | Yes | Routine Owner | Set automatically by `scaffold.py` |
| Jira project key | `CM` | Yes | Routine Owner | Filters JQL: `project = <KEY> AND fixVersion = "<scope>"` |
| `release_scope` (fixVersion) | `8.0` | Yes | Routine Owner; PL can override per fire via Instructions | Lives in `wiki_destination.json`; auto-loaded each fire |
| BookStack `page_id` | `360` | Yes | Routine Owner | Where the spec lands. Verified live by `scaffold.py` to be in shelf 3 |
| BookStack `book_id` / `chapter_id` | `11` / `117` (or null) | Yes for `book_id`, optional for `chapter_id` | Routine Owner | Captured at scaffold time; used for STEP 5C create-flow if page is missing |
| Cron expression | `30 1 * * *` (= 07:00 Asia/Colombo) | Yes | Routine Owner | UTC; min interval 1 hour |
| `DRY_RUN` env var | `false` (default) / `true` | Optional | Routine Owner or PL during testing | When `true`, STEP 7 skips the PUT; everything else runs |
| `EMAIL_RECIPIENTS` env var | `a@orangehrm.com,b@orangehrm.com` | Optional | Routine Owner | Comma-separated; takes precedence over `resources/email_recipients.json` |
| Trigger type | Manual + Cron | Yes | Routine Owner | Cron for daily, manual for ad-hoc re-fires |

---

## 6. Project Lead Prerequisites

Before a PL runs the routine, the following must be true:

- **Jira access** to the relevant project (Browse Projects permission).
- **Stories** have clear, descriptive titles (the routine uses the summary as a Feature label fallback).
- **Story descriptions** contain the final, released behaviour — not "TBD", not a Google Drive link with no text, not "see PRD". Bullet form or short paragraphs both work; the routine extracts test-case bullets from the description text.
- **Acceptance criteria** are available either inline in the description or in a confirmed-final Jira comment ("Confirmed by PL", "Final per design review", etc.).
- **fixVersion is assigned** to the story.
- **fixVersion is released** — either `released=true` or `releaseDate` ≤ today in Asia/Colombo. The Release Manager owns this.
- **Story status is completed** — Done, Closed, Completed, or Released (any of these — driven by `statusCategory.key == "done"`).
- **Story is not excluded** — no `deferred`, `cancelled`, `rejected`, `removed-from-scope`, `dropped`, `duplicate`, `wont-do`, `moved`, `not-applicable`, or `na` in the resolution, status name, or labels.
- **UI assets** (screenshots, Figma links, mockups) are attached to the Jira story description or as Jira attachments **only if they should appear in the spec**.
- **External Google Drive links are not the only source.** The routine never reads external docs (Jira is the only source of truth) — if the description points exclusively to a Drive doc, the routine BLOCKS the story.
- **PL knows which routine to run** — the URL is `https://claude.ai/code/routines/<trigger_id>`. The Routine Owner shares this on first onboarding.
- **PL understands the Instructions area** — see §10 below for the scope-adjustment patterns.

---

## 7. Jira Story Readiness Checklist

Use this checklist on each story before firing the routine. If any box is unchecked, fix it in Jira first.

- [ ] Story title is clear and descriptive (used as Feature label fallback).
- [ ] Description has the final released behaviour (not "TBD", not "see PRD", not Drive-link-only).
- [ ] Acceptance criteria are available (in description or confirmed comment).
- [ ] `fixVersion` is assigned to the story.
- [ ] `fixVersion.released=true` OR `releaseDate ≤ today` in Jira.
- [ ] Story status is Done / Closed / Completed / Released.
- [ ] Story is not Deferred / Cancelled / Rejected / Removed from Scope / Duplicate / Won't Do / Moved / Not Applicable.
- [ ] UI assets are attached to the Jira story IF they should appear in the spec (screenshots, mockups, Figma links).
- [ ] Comments that the routine should pick up (final behaviour confirmations) are clearly worded ("Confirmed by PL", "Final UI per design review", explicit yes/no on questions).
- [ ] Story does not rely solely on a Google Drive / Docs / Figma link with no inline text.
- [ ] Story belongs to the correct project key for the routine being fired.

---

## 8. Jira-Only Release Filtering Rule

Authoritative reference: `resources/release-filter-policy.md` §1–§9.

### The rule
A story is processed only if **all** of the following are true:

1. The issue belongs to the routine's configured Jira `fixVersion` (the `release_scope` value in `wiki_destination.json`).
2. Jira confirms the `fixVersion` as released — either:
   - `fixVersion.released == true`, **OR**
   - `fixVersion.releaseDate` is today or in the past (Asia/Colombo timezone).
3. The issue type is in scope — Epic / Story / Task (Epics are walked for their children, not rendered as ATC rows themselves).
4. The issue is completed — `statusCategory.key == "done"` or a canonical completion status.
5. The issue is not excluded from scope (no `deferred` / `cancelled` / `rejected` / `removed-from-scope` / `dropped` / `duplicate` / `wont-do` / `moved` / `not-applicable` / `na` token in resolution / status / labels).
6. The issue's description contains usable behaviour text (not empty, not only external links).

### What the routine does NOT use
- Wiki release dates.
- BookStack revision history.
- Wiki catalog or any third-party release-tracking system.
- The Wiki MCP.
- Any source other than Jira.

### Per-scenario behaviour

#### `released=true` (any `releaseDate`)
**CONFIRMED** → routine proceeds. Logs verbatim:
```
Release confirmed - Jira fixVersion [VERSION] for project [PROJECT_KEY] is marked as released.
```

#### `released=false` AND `releaseDate ≤ today`
**CONFIRMED** → routine proceeds. Logs verbatim:
```
Release confirmed - Jira fixVersion [VERSION] for project [PROJECT_KEY] has a releaseDate in the past or today.
```

#### `released=false` AND `releaseDate` is in the future
**SKIPPED** → routine emits AUDIT SUMMARY, GitHub log, and email with `status: SKIPPED`. Logs verbatim:
```
Skipped - Configured fixVersion [VERSION] for project [PROJECT_KEY] is not released yet because Jira releaseDate is in the future.
```
The next scheduled run after `releaseDate` will resume processing automatically.

#### `released=false` AND `releaseDate` is empty / null / missing
**BLOCKED** → routine emits AUDIT SUMMARY, GitHub log, and email with `status: BLOCKED`. Logs verbatim:
```
Blocked - Configured fixVersion [VERSION] for project [PROJECT_KEY] is not confirmed as released in Jira because released=false and releaseDate is empty. Release Manager or Project Admin must either mark the version as released or set a valid releaseDate in Jira.
```

### Per-Epic project scan (every run, every status)
Independent of the per-story release gate, the routine runs `JQL: project = <KEY> AND issuetype = Epic` on every fire (including SKIPPED and BLOCKED runs) and classifies each Epic by its `fixVersions[]`:
- `✓ Released` — at least one `fixVersion.released==true` OR `releaseDate ≤ today`.
- `⚠ Pending` — every `fixVersion` is unreleased.
- `— Unassigned` — `fixVersions[]` is empty.
- `✗ Excluded` — Epic is `cancelled` / `deferred` / `dropped` / etc.

This populates the **Epic Release Status** section of the email so the Release Manager sees the project's full Epic landscape on every fire, not just the stories that match the configured `release_scope`.

---

## 9. How Project Leads Run the Routine from UI

### Step-by-step

1. Open the routine URL: `https://claude.ai/code/routines/<trigger_id>` (provided by the Routine Owner on onboarding).
2. Confirm the correct routine is selected (the title shows e.g. *OHRM CM Daily Wiki Sync*).
3. Review the **Project Key** parameter in the prompt body (e.g. `CM`).
4. Review the **release_scope** (fixVersion) currently configured in `wiki_destination.json` — visible in the prompt's `current value:` annotation.
5. Review the **target wiki page** mapping — also visible in the prompt body's parameter table.
6. Click **Edit** → **Instructions** to open the prompt body. **Do not edit the safety rails, STEP 1–11 workflow, or any wording that contradicts the canonical resource files.** Only scope adjustments are safe here.
7. **Adjust scope only if needed** — see §10 below for copy-paste patterns (project-level / feature-specific / UI-only / ATC refresh).
8. Save the edited prompt (or skip if no edits needed).
9. Click **Run now** — fires the routine immediately. (Or wait for the cron to fire at the scheduled time.)
10. Wait — typical run takes 2–5 minutes. The routine UI shows a spinner; you do not need to keep the tab open. The email arrives when the run completes.
11. Open the email. Read in this order:
    - **Status** (Completed / Completed with Warnings / Skipped / Blocked / Failed).
    - **Run Summary** cards (Stories Checked / Updated / No Change / Skipped / Blocked / Bugs Reported).
    - **Epic Release Status** section (every Epic in the project with its release tick).
    - **Story-Level Results** table (per-story rows).
    - **Manual Actions Required** section (red box — only present when count > 0).
    - **Specification Page** link at the bottom — opens the live BookStack page.
12. Open the **Specification Page** link to verify the wiki update visually. The page should match the changes summarised in the email.
13. Review **Skipped** rows — these usually need a Jira fix (description text added, fixVersion released, exclusion label removed).
14. Review **Blocked** rows — these need a specific manual action stated in the Manual Actions section.
15. Apply the manual action (e.g. mark fixVersion as released, update Jira description) and re-run the routine.

### What PLs do NOT need to do

- **No Claude Code.** Everything is done from the browser at `claude.ai/code/routines`.
- **No GitHub access.** The routine commits its own log via its `GITHUB_TOKEN` env var. PLs read the log via the link in the email if needed.
- **No CLI scripts.** `automation/sync.py`, `routines/deploy.py`, `routines/scaffold.py` are all Routine Owner/Admin tools. PLs never run them.
- **No direct wiki edits during a fire.** Once you click "Run now", let the routine finish. If you edit the wiki at the same time, the pre-flight `updated_at` check may detect a concurrent edit and BLOCK the write.

### What might require admin help

- **If the GitHub log commit fails** (404 / 401 in the AUDIT SUMMARY): `GITHUB_TOKEN` may have expired or been revoked. Routine Owner re-mints per `docs/SECURITY.md`.
- **If Jira image download fails (403)**: the Atlassian network allowlist is blocking `api.atlassian.com`. PL or environment admin handles. See §13.
- **If the email never arrives** (no Manual Actions, no log link, just silence): Plan A Gmail token expired (7-day cycle). Routine Owner re-runs `routines/oauth_setup.py`.
- **If the wiki write fails** (validator BLOCKED): the routine ran but couldn't write because a STEP 6 check failed. The AUDIT SUMMARY lists the failing check number. Routine Owner debugs.

---

## 10. Instruction Area Usage for PLs

The **Instructions** field in the routine UI is where you tell the routine what to do **on this fire**. The canonical workflow (STEP 1–11) is in the GitHub resource files and cannot be overridden — what you can adjust is **scope**.

### Safe patterns — copy-paste these

#### Project-level run (default — what the cron does)
```
Process all completed stories under Jira project <PROJECT_KEY> and fixVersion <SCOPE> that are confirmed as released in Jira. Update the relevant specification files and include Jira UI assets where available. Follow the canonical workflow in resources/SKILL.md.
```

#### Feature-specific run (e.g. one or two stories)
```
Process only Jira stories <KEY-1> and <KEY-2>. Do not process other stories in this fire. Update only the relevant sections in the specification. Follow the canonical workflow in resources/SKILL.md and the dedup contract in release-filter-policy.md §10.3.
```

#### UI-only refresh (no scenario changes)
```
Check <KEY-1> and <KEY-2> for UI assets only. Update only the User Interfaces (UIs) section of the specification page. Do not change ATC rows, Form rows, or any other canonical table. Per release-filter-policy.md §11.1, follow the extract → upload → compare → replace/add merge algorithm. Per §11.1-bis, the UI section is a gallery — h6 + image pairs only, no paragraphs.
```

#### Acceptance Test Case refresh (force re-evaluation of all rows)
```
Review the entire Acceptance Test Cases table on the target page. For each existing row, check whether the latest Jira description for the matching story key has new bullets that should be merged in. Apply the dedup contract in release-filter-policy.md §10.3 — match by Jira key first, then by semantic Feature/Topic name. Do not create duplicate rows. Per SKILL.md §5-C.2, preserve all existing scenario bullets even if they are not in the latest Jira description.
```

#### Dry-run before a real fire
```
DRY_RUN mode is set via the DRY_RUN env var (set DRY_RUN=true in the routine Environment Variables panel, not in this Instructions field). When DRY_RUN=true, the routine runs STEP 1–6 normally and STEP 7 skips the BookStack PUT. The email banner will read [DRY RUN]. Use this to preview the diff before a real publish.
```

### What PLs MUST NOT do in the Instructions field

- **Do not force unreleased stories.** Instructions cannot override the release gate; the routine reads Jira at fire time and applies §3-§6 of `release-filter-policy.md` regardless of what the Instructions say.
- **Do not process ongoing stories.** The completion check (`statusCategory.key == "done"`) is non-overridable.
- **Do not ask the routine to use wiki release dates.** The Jira-only rule is policy. Any Instruction that says "use wiki dates" or "consult BookStack catalog" is ignored — the routine refuses.
- **Do not duplicate Acceptance Test Case rows.** The dedup contract is enforced by STEP 6 check #12. Instructions saying "always add a new row" produce a STEP 6 BLOCKED status.
- **Do not include broken Atlassian URLs as final UI references.** The routine won't, but Instructions saying "embed the Jira URL directly" are wrong — see §13.
- **Do not paste API keys into Instructions.** The Instructions field is visible to anyone with read access to the routine. Keys belong in Environment Variables.
- **Do not include personal information / PHI / customer data.** Instructions get committed to GitHub via the routine prompt body on the next `deploy.py --update`. Treat it as public-ish.

---

## 11. GitHub / Specification Update Behavior

The routine's GitHub interactions are limited and well-defined:

- **Reads** `resources/*` at fire-time from a fresh `git clone https://github.com/<your-org>/ohrm-wiki-sync` — this is how it picks up your latest SKILL.md / release-filter-policy.md / etc. without redeploying.
- **Writes** one log file per fire at `logs/<routine_slug>/<UTC_TIMESTAMP>.md` via `PUT /repos/<org>/<repo>/contents/<path>` — the timestamp uses the pinned format `YYYY-MM-DDTHHMMSSZ.md` (per `SKILL.md` STEP 9).
- **Skips silently** if `GITHUB_TOKEN` is unset — the wiki write still happens, the email still sends; only the GitHub log is missing.

### What the routine does in the BookStack write (STEP 7)

- Reads the **latest** target page from BookStack (the current `PRIOR_HTML`).
- Locates the **correct page** — `routine_destinations.<slug>.page_id` in `wiki_destination.json` (verified by the page → chapter → book → shelf chain ending in shelf id=3).
- Locates the **correct fixVersion content** — but does NOT write fixVersion as a section header or column. Jira owns "which release did this ship in"; the wiki is the current spec.
- Updates the **existing ATC row** if the Jira-key match (§5-C step 1.a) or semantic name match (§5-C step 1.b) hits.
- Creates a **new ATC row** only when no match → no duplication.
- Uses the **Jira issue key** as the primary unique identifier; the leftmost ATC cell carries a parenthetical key list like `(CM-2)` or `(CM-100, CM-200)` for multi-contributor features.
- **Preserves manually written valid content** — additive merge by default. Rows written by prior runs are never removed; legacy paragraphs are repaired in place (per `SKILL.md` §5-C.2 step 1 "Legacy paragraph-form repair").
- Updates the **User Interfaces (UIs) section** if Jira UI assets exist — gallery-only h6 + image pairs.
- Updates the **canonical 5 tables** (ATC / List / Search / Form / Audit Trail) without creating duplicate Feature/Topic/Field rows.
- Produces a **clear diff** via the GitHub log file + email Story-Level Results table.

### What PLs need to know

- PLs do not directly edit GitHub in normal workflow.
- If the GitHub log commit fails (and you care about the log file existing on GitHub), notify the Routine Owner — `GITHUB_TOKEN` may have expired or the routine may have been temporarily firewalled.
- The wiki write succeeds independently of the GitHub log commit. A failed GitHub commit is annoying but not fatal — the email still tells you what happened.

---

## 12. Acceptance Test Case Duplicate Prevention

Authoritative reference: `release-filter-policy.md` §10.3, `SKILL.md` §5-C.1–§5-C.4.

### The rule
Before adding a new Acceptance Test Case row, the routine MUST check the existing ATC table for the same feature/topic/field. Match priority:

1. **Jira-key match** — the leftmost ATC cell's parenthetical key list contains the issue's Jira key. A row may carry multiple keys (e.g. `Audit Trail (CM-100, CM-200)`).
2. **Semantic Feature/Topic name match** — the leftmost cell's name equals the issue's intended Feature/Topic name after normalisation, OR they belong to the same synonym group per `SKILL.md` §5-C.1.

### If the feature/topic already exists
- **Keep** the existing row (preserve `#`, preserve existing key list).
- **Update** the Scenario column with the newly identified released behaviour.
- **Merge** the new scenario bullets clearly per `SKILL.md` §5-C.2.
- **Preserve** existing valid test coverage — never drop earlier-confirmed bullets just because the latest Jira description omits them.
- **Append** the new contributing Jira key to the parenthetical key list (e.g. `Audit Trail (CM-100)` becomes `Audit Trail (CM-100, CM-200)`).
- Do NOT duplicate the row.

### If the feature/topic is new
- **Add** a new row at the end.
- **Map** the new Feature/Topic correctly onto the canonical column shape.
- **Add** the matching Scenario as a `<ul>` of `<li>` items (per the bullet-form rule).
- The leftmost cell ends with the Jira issue key in parentheses.

### Canonical synonym groups (`SKILL.md` §5-C.1)
- `Audit Trail` / `Audit Log` / `Audit History` / `Activity Log` / `Change History` → one row.
- `Pay Grade` / `Salary Grade` / `Compensation Grade` → one row.
- `Snapshot` / `Snap Shot` / `History View` → one row (when context = compensation snapshot).
- `Search` / `Filter` / `Filters` / `Search & Filter` → one row.
- `List View` / `Grid View` / `Table View` → one row.
- `Form` / `Add/Edit Form` / `Input Form` / `Modal Form` → one row.
- `User Interfaces (UIs)` / `UI` / `Screens` / `User Interface` → one row.

**Rule for unlisted names:** if two names refer to the same screen / data / action in the spec author's mental model, treat them as the same. When in doubt, lean toward **merge** (one row, combined scenario) rather than **split** — merging is reversible if the next iteration finds they were separate; splitting creates duplicates someone has to consolidate manually.

### Example
Story CM-100 introduces "Audit Trail" → routine creates row `Audit Trail (CM-100)`. A month later, story CM-200 refines the audit-tracking behaviour for the same feature. On the next fire, the routine:
1. Tries Jira-key match — `(CM-200)` is not in any row's key list yet, no match.
2. Tries semantic name match — `Audit Trail` (normalised from the CM-200 description) matches the existing `Audit Trail (CM-100)` row.
3. UPDATES the existing row in place, appending `, CM-200` to make it `Audit Trail (CM-100, CM-200)`, and merging the new scenario bullets per §5-C.2.
4. Does NOT create a second `Audit Trail (CM-200)` row.

---

## 13. UI Asset Handling

Authoritative reference: `release-filter-policy.md` §11.1 / §11.1-bis / §11.1-ter, `WIKI_PAGE_RENDER.md` §3, `SKILL.md` STEP 5-D.

### What the routine looks for in Jira

Per eligible story:
- **Attachments** with `mimeType` starting `image/` OR filename ending in `.png/.jpg/.jpeg/.gif/.bmp/.svg/.webp`.
- **Embedded images** in the ADF description (`mediaSingle` / `media` nodes, markdown `![]()` patterns).
- **Design-tool URLs** (Figma / InVision / Sketch / Miro / Whimsical / Excalidraw / Marvel / Adobe-XD / Zeplin) — these become external `<a>` links, NOT `<img>`.

### The gallery-only rule (§11.1-bis)

The `<h2>User Interfaces (UIs)</h2>` section is **a gallery, not a narrative**. Authored content is strictly:
- Repeating `<h6>{Topic Name}</h6>` + `<a href><img></a>` pairs, one per screen.
- Optional `<h6>Design References</h6>` sub-block at the end with one `<p><strong>Figma:</strong> <a href>...</a></p>` element for design-tool URLs.

**Forbidden inside the UI section:** `<p>` paragraphs (except inside Design References), `<ul>`/`<ol>`/`<li>`, `<table>`, heading levels other than `<h6>`, inline `<strong>UI:</strong>` labels, narrative connective text. Topic names that read as sentences (period+space, >6 words, leading `The`/`This`/`When`/`A`) FAIL STEP 6 check #7.

### Topic name source priority (§11.1-ter)
1. Jira description heading immediately preceding the image (preferred).
2. Bold/strong label in the same description paragraph (`**Salary History:** ![]()`).
3. Image filename in title case (`salary-history.png` → "Salary History").
4. Jira story title, cleaned.
5. Generic fallback `Untitled UI <n>` — routine logs `validation_warning: ui_topic_name_unresolved`.

### What if no UI assets are found
The routine adds nothing to the UI section for that story. There is no "No UI references were available" placeholder text — the section is silent (no UI assets = no entry, not a forced empty entry).

### Atlassian 403 handling — the BLOCKED_UI_IMPORT path

When the routine cannot download a Jira attachment binary because `api.atlassian.com` is blocked by the routine execution environment's outbound network allowlist (HTTP 403 "Host not in allowlist"):

- **Routine action**: skips THAT image for THIS run. The ATC row + Form/Search/Audit rows still get written normally (text content is independent of image upload).
- **Routine log line**: `UI download failed - <filename> for <KEY>: HTTP 403 Host not in allowlist.`
- **Email surfacing**: the Manual Actions section lists the affected images with the exact filenames and the action needed.
- **Routine NEVER falls back** to writing the Atlassian URL into the wiki page as a final UI reference — that produces broken images for wiki readers (the URL requires Jira auth and returns 403 to unauthenticated browsers).

**Required action when 403 happens:**
1. **Permanent fix (preferred)**: Environment admin adds `api.atlassian.com` to the routine execution environment's outbound network allowlist. After unblock, the next routine fire automatically rehosts all pending images to BookStack and replaces any stale Atlassian URLs in the wiki UI section.
2. **Manual fallback (when permanent fix isn't available)**: PL manually downloads each image from Jira (signed in via browser), uploads them to BookStack's image gallery (right-side panel on the BookStack edit page → "Insert from image gallery"), and updates the `User Interfaces (UIs)` section of the wiki page with the BookStack URLs. The next routine fire's UI merge step (§11.1) sees the now-correct BookStack URLs and no-ops.

**Status convention**: when 403 occurs, the per-story row in the email is still marked **Updated** (the ATC/Form/Audit rows did update). The `Required Action` cell calls out the manual image upload. The story is NOT marked NO_CHANGE — that would be misleading.

### What PLs should NOT do
- Do not embed broken Atlassian URLs in the wiki manually.
- Do not paraphrase a UI ("the Salary History screen shows past salaries") — paragraphs in the UI section FAIL STEP 6 check #7. If you need to describe what a screen does, that goes in the **Scenario** column of the corresponding ATC row.
- Do not use UI assets from unrelated Jira stories. The routine extracts per-story; PLs should attach images to the right story.

---

## 14. Run Output / Email Report

Every routine fire produces three artefacts:

1. **AUDIT SUMMARY** — printed to the routine session's stdout (visible in the claude.ai run history). Structured key-value block.
2. **GitHub log file** — committed to `logs/<routine_slug>/<UTC_TIMESTAMP>.md` (pinned format). YAML frontmatter + markdown summary + the rendered email HTML body between `<!-- EMAIL_BODY_START -->` / `<!-- EMAIL_BODY_END -->` markers.
3. **Email** — sent to all `EMAIL_RECIPIENTS`. Subject: `OHRM Wiki Sync — <routine_slug> — <STATUS> — <YYYY-MM-DD>`. Body: the HTML rendered from `resources/email_template.html`.

### YAML frontmatter fields

```yaml
routine: <slug>
project_key: <KEY>
fix_version: "<scope>"
fix_version_released: <true|false>
fix_version_release_date: <YYYY-MM-DD or empty>
release_gate: <CONFIRMED|NOT_YET|BLOCKED>
release_gate_log: <verbatim policy log line>
run_utc: <ISO8601 actual fire time>
status: <SUCCESS|NO_CHANGE|SKIPPED|BLOCKED|FAILED>
dry_run: <true|false>
target_page_id: <id>
target_page_name: <name>

# Discovery counts (drives the email Run Summary cards)
total_issues_found: <N>
epics_found / epics_processed: <N>
stories_found / stories_processed: <N>
tasks_found / tasks_processed: <N>
bugs_found: <N>           # reported only, not in change list
subtasks_found: <N>       # reported only
other_found: <N>          # Improvements / Refactors / Spikes / etc.

# Per-Epic project scan (STEP 3-D)
epics_scanned / epics_released / epics_pending / epics_unassigned / epics_excluded: <N>
epic_scan_summary:
  - key: <KEY>
    name: <Jira summary>
    fix_versions: <"8.0, 8.0.2" or "—">
    status: <Released|Pending|Unassigned|Excluded>
    symbol: <"✓"|"⚠"|"—"|"✗">

# Outcome counts (per processed issue)
stories_updated / stories_no_change / stories_skipped / stories_blocked: <N>

manual_actions:
  - <freeform action text>
email_subject: "OHRM Wiki Sync — <slug> — <STATUS> — <YYYY-MM-DD>"
email_send_status: SENT | PARTIAL | FAILED | SKIPPED
log_html_url: https://github.com/<org>/<repo>/blob/main/logs/<slug>/<file>
```

### Email body sections (top to bottom)

1. **Header** — routine name banner.
2. **Metadata grid** — Routine / Project / Fix Version / Run Date / Status badge.
3. **Run Summary cards** — Stories Checked / Updated / No Change / Skipped / Blocked / Bugs Reported / Manual Actions Required count.
4. **Epic Release Status** — every Epic in the project with its release tick (✓ ⚠ — ✗).
5. **Story-Level Results** — table with one row per processable story (Stories + Tasks only — Bugs / Sub-tasks / Epics are summarised in cards or the Epic section).
6. **Manual Actions Required** — red box, only shown when count > 0. Each row is one numbered action.
7. **Specification Files Updated** — table showing which wiki page got which rows from which stories.
8. **Run Conclusion** — one of 6 final-status messages (see `SKILL.md` §9-G).
9. **Specification Page** — link to the live BookStack page.
10. **Footer** — "Generated by the OHRM Wiki Sync automated routine."

### Story-level table columns
- **Jira Key** — clickable link to Jira (in the future; currently text).
- **Story Name** — Jira summary verbatim.
- **Status** — `Updated` / `No Change` / `Skipped` / `Blocked` / `Excluded` (with coloured badge).
- **Reason** — descriptive line: `Updated - ATC row #13 added for 'Pay Grade Soft Delete'; Form row updated for 'Pay Grade'.`
- **Spec File** — `Salary (page 360)` or `N/A`.
- **Updated Sections** — `ATC row #15; Form rows (Base Pay, Base Pay Type, Base Pay Frequency)`.
- **Required Action** — `No action required.` or a specific manual ask (e.g. "Release Manager must mark fixVersion as released").

### Who acts on what

| Section | Action owner |
|---|---|
| Story-Level Results — Updated rows | No action — review for spot-checks |
| Story-Level Results — No Change rows | No action — content matched existing wiki |
| Story-Level Results — Skipped rows | Project Lead — usually a Jira data fix (description, fixVersion, exclusion label) |
| Story-Level Results — Blocked rows | Release Manager (release gate) OR Project Lead (story description) per the Required Action cell |
| Manual Actions Required section | Whoever the action specifies (PL / Release Manager / Routine Owner / Env Admin) |
| Specification Files Updated table | QA Lead — spot-check the wiki page matches expectations |
| Epic Release Status — Pending rows | Release Manager — confirm whether Pending Epics need to ship in this release |

---

## 15. Common Scenarios and Expected Handling

| Scenario | Routine Action | Status | Log Message | Required Action |
|---|---|---|---|---|
| `fixVersion.released=true` AND story Done | Process story | SUCCESS | `Release confirmed - Jira fixVersion <V> for project <K> is marked as released.` | None — review email |
| `released=false` AND `releaseDate ≤ today` AND story Done | Process story | SUCCESS | `Release confirmed - Jira fixVersion <V> for project <K> has a releaseDate in the past or today.` | None |
| `released=false` AND `releaseDate` empty | Skip all stories under this fixVersion; run STEP 3-D + email anyway | BLOCKED | `Blocked - Configured fixVersion <V> for project <K> is not confirmed as released in Jira because released=false and releaseDate is empty. Release Manager or Project Admin must either mark the version as released or set a valid releaseDate in Jira.` | Release Manager marks `released=true` OR sets a valid `releaseDate` |
| `released=false` AND `releaseDate` in future | Skip all stories; run STEP 3-D + email anyway | SKIPPED | `Skipped - Configured fixVersion <V> for project <K> is not released yet because Jira releaseDate is in the future.` | None — routine resumes on next fire after `releaseDate` |
| Story outside configured `release_scope` | Not returned by JQL — invisible to this fire | n/a | n/a | None (story belongs to a different release; will surface in that release's fire) |
| Story status not completed | Skip per §7 | SKIPPED (per-story) | `Skipped - Story is linked to a released fixVersion, but the story itself is not completed.` | PL marks story Done in Jira when work is complete |
| Story marked Deferred / Cancelled / Duplicate / Won't Do | Skip per §9 | SKIPPED (per-story) | `Skipped - Story is excluded from release scope.` | None — intentional exclusion. If the exclusion was a mistake, PL removes the exclusion label in Jira |
| Story Done but description empty | Block per STEP 4-C | BLOCKED (per-story) | `Blocked - Jira description is empty. Add a textual description of the released behavior to the Jira ticket.` | PL adds description text in Jira |
| Story description has only a Google Drive link | Block per STEP 4-C | BLOCKED (per-story) | `Blocked - Jira description has no extractable behavior text. Add a textual description of the released behavior to the Jira ticket.` | PL adds inline description text in Jira (the routine ignores external links — Jira is the only source) |
| Story has UI screenshots — Atlassian allowlist OK | Download from Jira, upload to BookStack, embed | SUCCESS | `UI added - <filename> for <KEY>` | None |
| Story has UI screenshots — Atlassian returns 403 | Skip THIS image; ATC/Form/Audit rows still updated | SUCCESS (with manual_action) | `UI download failed - <filename> for <KEY>: HTTP 403 Host not in allowlist.` | Env admin unblocks `api.atlassian.com` (preferred) OR PL manually uploads images to BookStack |
| Story already exists in spec — same content | NO-OP per §5-C step 5 | NO_CHANGE (per-story) | `No change - <KEY> ATC row already up to date.` | None |
| Story already exists in spec — Jira has updated content | UPDATE in place per §5-C.2 | SUCCESS (per-story) | `Updated - ATC row #<n> scenario re-rendered to canonical bullet form; 2 new bullets added.` | None |
| Acceptance Test Case feature already exists (Jira-key match) | UPDATE existing row per §5-C step 1.a | SUCCESS | (per-row update note) | None |
| Acceptance Test Case feature already exists (semantic name match) | UPDATE existing row per §5-C step 1.b; append new Jira key to key list | SUCCESS | `Updated - ATC row #<n>: key '<KEY>' appended; <n> new scenario bullets merged.` | None |
| GitHub update fails (`GITHUB_TOKEN` expired) | Wiki write completes; STEP 9 log commit skipped silently | SUCCESS (with caveat) | (no log line) | Routine Owner re-mints `GITHUB_TOKEN` (`docs/SECURITY.md`) |
| Email send fails (Plan A 7-day token expiry) | Wiki write + GitHub log both complete; email fails | SUCCESS (with `email_send_status: FAILED`) | `email_send_error: invalid_grant` | Routine Owner re-runs `routines/oauth_setup.py` |
| BookStack update fails after validation passes | Routine retries 3× per HTTP retry policy; FAILED if all retries exhausted | FAILED | `Failed - BookStack PUT /api/pages/<id> returned 5xx after 3 retries. Wiki may be down.` | Routine Owner checks BookStack status; routine retries on next fire |
| BookStack target page returns 404 (page deleted/moved) | Fall through to STEP 5C create-flow; create new page in configured book/chapter; flag new page_id as manual_action | SUCCESS | `Note - target page <id> returned 404; STEP 5C created new page <new_id> in book <book_id>.` | Routine Owner updates `wiki_destination.json` with the new `page_id` and commits |
| STEP 6 validator fails (duplicate ATC row, paragraph in UI section, etc.) | BLOCK the BookStack PUT; emit AUDIT SUMMARY with FAIL reason | FAILED | `Failed - validation failed: check <#> — <message>` | Routine Owner debugs the LLM merge; usually a content issue in Jira that confused the routine |

---

## 16. Troubleshooting Guide

| Symptom | Likely Cause | Who Fixes | Recommended Fix |
|---|---|---|---|
| No stories processed (Stories Checked = 0) | JQL returned empty — wrong project key OR wrong fixVersion OR all stories outside scope | Routine Owner (config) or PL (Jira data) | Verify `routine_destinations.<slug>.jira_project_key` and `release_scope` in `wiki_destination.json`. Run the same JQL manually in Jira: `project = <KEY> AND fixVersion = "<scope>"`. |
| All stories skipped (Skipped = N, Updated = 0) | All stories failed the completion check OR all are excluded by resolution/label | PL | Open the email's Story-Level Results table. Each skipped row has a reason. Fix Jira data (mark Done, remove exclusion labels). |
| fixVersion not confirmed as released | `released=false` AND `releaseDate` empty | Release Manager | In Jira → Releases → click the version → either toggle "Released" to true OR set a valid `releaseDate`. |
| Jira token permission issue (401 / 403 on read) | `JIRA_API_TOKEN` revoked, expired, or scoped to wrong project | Routine Owner | Regenerate token at `id.atlassian.com/manage-profile/security/api-tokens`. Verify the token user has "Browse Projects" on the project. |
| Jira attachment download 403 (`api.atlassian.com` not in allowlist) | Routine execution environment network policy | Env admin (preferred) or PL (manual rehost) | Add `api.atlassian.com` to outbound allowlist OR manually download images and upload to BookStack image gallery. |
| GitHub update failed (no log file on github.com) | `GITHUB_TOKEN` expired, scope wrong, or repo permissions changed | Routine Owner | Re-mint per `docs/SECURITY.md` § "GitHub PAT". Confirm `contents: read and write` on the single repo. |
| BookStack update failed (`Failed - HTTP 4xx`) | Token scope wrong, service account lacks edit rights on the chapter, target page not in shelf 3, OR concurrent edit detected | Routine Owner + BookStack admin | Check BookStack token has edit-page rights on the chapter. Re-verify `page → chapter → book → shelf` chain. |
| UI images broken on the wiki page | Atlassian URLs written directly (legacy artefact from a pre-policy run) OR BookStack image was deleted | PL (one-shot fix) | Trigger the routine fire after `api.atlassian.com` is unblocked — the UI merge §11.1 replace path will swap the broken URLs with BookStack URLs automatically. |
| Duplicated Acceptance Test Case rows (same feature in two rows) | LLM merge missed the dedup contract (rare — STEP 6 check #12 should block this) | Routine Owner debugs; PL can manually merge | Open the wiki page, delete the duplicate row, save. The next routine fire will see only one row and process correctly. Report to the Routine Owner so they can investigate why STEP 6 check #12 passed. |
| Wrong spec file updated | `routine_destinations.<slug>.page_id` points to the wrong page in `wiki_destination.json` | Routine Owner | Update `wiki_destination.json` with the correct page id. Commit. Next fire writes to the right page. |
| Routine says NO_CHANGE but manual action is required | The 5 canonical tables didn't change BUT the UI section couldn't update due to Atlassian 403 | PL | Open the email — look for the Manual Actions section. Even on NO_CHANGE runs, the manual_actions array surfaces persistent issues. |
| PL cannot run routine from UI | Routine not shared with the PL OR PL's claude.ai account doesn't have access to the workspace | Routine Owner | Share the routine URL; verify the PL can see it at `claude.ai/code/routines`. |
| PL cannot see the routine in their routines list | Routine is owned by a different account in a different workspace | Routine Owner | Move the routine to a shared workspace OR re-create the routine in a workspace the PL has access to. |
| API token expired (mid-fire failure) | Quarterly rotation reminder missed | Routine Owner | Rotate per `docs/SECURITY.md`. The routine resumes on the next fire with the new token. |
| Actions logged under the wrong user/account | Personal token used instead of service account | Routine Owner | Migrate to a service account (`docs/SECURITY.md` § "Recommended hardening"). Replace the personal tokens in the routine env vars. |

---

## 17. Roles and Responsibilities

| Activity | Routine Owner/Admin | Project Lead | QA Lead | Release Manager | Developer/Maintainer |
|---|---|---|---|---|---|
| Create routine (scaffold + deploy) | **PRIMARY** | — | — | — | Assists |
| Configure Jira token | **PRIMARY** | — | — | — | Assists |
| Configure GitHub token | **PRIMARY** | — | — | — | Assists |
| Configure BookStack token | **PRIMARY** | — | — | — | Assists |
| Maintain Jira story quality (description, AC, status) | — | **PRIMARY** | Reviews | — | — |
| Confirm release / fixVersion `released=true` | — | Requests | — | **PRIMARY** | — |
| Attach UI screenshots to Jira stories | — | **PRIMARY** | Reviews | — | — |
| Run routine from UI ("Run now") | Can | **PRIMARY** | — | Can | Can |
| Adjust Instructions / scope in routine UI | Can | **PRIMARY** | — | — | Can |
| Review email run output | Reviews | **PRIMARY** | Reviews | Reviews | — |
| Action Blocked Jira items (description fixes, release gate) | — | **PRIMARY** for description; **Release Manager PRIMARY** for release | — | **PRIMARY** for release | — |
| Fix routine implementation issues (SKILL.md, prompts, scripts) | Assists | — | — | — | **PRIMARY** |
| Manage API/token security (rotation, revocation, audit) | **PRIMARY** | — | — | — | Assists |
| Review final specification quality | — | Reviews | **PRIMARY** | Reviews | — |
| Onboard a new PL to the routine | **PRIMARY** | — | — | — | — |
| Migrate to service account tokens | **PRIMARY** | — | — | — | Assists |
| Update `wiki_destination.json` after STEP 5C page recreation | **PRIMARY** | — | — | — | — |
| Unblock `api.atlassian.com` (network allowlist) | Coordinates with env admin | — | — | — | — |
| Renew Gmail OAuth refresh token (Plan A, weekly) | **PRIMARY** | — | — | — | — |

---

## 18. Recommended Rollout Process

Phased approach for adding new projects to the routine fleet:

### Phase 1 — Pilot (Day 0)
1. Finalise this guideline (you are reading it).
2. Configure ONE project-level routine using `routines/scaffold.py`.
3. Run with limited scope: `DRY_RUN=true` + Instructions limited to 1–2 stories.
4. Validate the email looks correct, the wiki preview makes sense, no STEP 6 validation FAILs.

### Phase 2 — First PL handover (Week 1)
5. Walk one PL through the routine UI in a screenshare. Show: "Run now", reading the email, opening the Specification Page link, identifying a Manual Action.
6. Have the PL run a real fire (DRY_RUN=false) for a small subset of their stories.
7. Collect feedback — what was unclear? What was missing from the email?
8. Iterate on this guide + `email_template.html` if needed.

### Phase 3 — Template improvements (Week 2)
9. Tune Instruction templates based on the PL's first real-fire experience.
10. Add any project-specific exclusions to `release-filter-policy.md` §9 (rare — most are global).
11. Verify smoke test passes after every canonical-file edit: `py tests/smoke_test.py`.

### Phase 4 — Fleet expansion (Week 3+)
12. Onboard a second project. Use `scaffold.py` — every new project should be a 1-command setup.
13. Share the routine URLs with each project's PL.
14. Confirm cron schedules don't all hit the same hour (stagger to avoid Anthropic rate limits and BookStack load spikes).

### Phase 5 — Ongoing operations
15. Train PLs on Jira readiness (this guide § 6 + § 7).
16. Monitor email reports daily (Blocked / Failed runs need attention same-day).
17. Quarterly token rotation (`docs/SECURITY.md`).
18. Migrate to Plan B Gmail (Workspace service mailbox, never-expiring tokens) — `docs/EMAIL_SETUP.md`.

---

## 19. Limitations and Important Notes

- **PLs do not need GitHub access** — only if the routine is already created and connected correctly with `GITHUB_TOKEN` set. If `GITHUB_TOKEN` is missing or expired, the GitHub log step is skipped silently (the wiki write still happens, the email still sends).
- **PLs do not need Claude Code** for normal routine usage — `claude.ai/code/routines` in a browser is enough.
- **PLs can customise routine Instructions / scope from the UI** — but cannot override the canonical workflow defined in the 6 resource files (authority order: `release-filter-policy.md > specification-writing-guideline.md > SKILL.md > WIKI_PAGE_RENDER.md > routine prompt > UI Instructions`).
- **Jira must be clean and complete** for good output. Empty descriptions, missing fixVersions, missing UI attachments → BLOCKED/SKIPPED stories.
- **The routine cannot safely infer final behaviour from incomplete Jira stories.** If the description says "see the PRD", the routine BLOCKS — it does not guess.
- **Google Drive / Figma / external links should not be the only source of requirements.** The routine ignores external links entirely (Jira-only is policy). Inline text in the Jira description is what gets processed.
- **UI image download may fail** if `api.atlassian.com` is blocked by network policy. Routine emits a Manual Action for affected images; rehosting requires either an allowlist update or manual upload.
- **Manual correction may be required** when the Atlassian allowlist blocks UI downloads — PL temporarily handles UI rehost until env admin unblocks.
- **API keys must never be shared publicly** (this is restated several times in this document because it is the highest-stakes operational rule).
- **Personal tokens cause actions to appear under that user's name** — service accounts are strongly recommended for shared routines.
- **Service account / bot token is recommended** for any production routine that survives team changes.
- **Do not create routines for individual features.** One routine per project. Feature-specific runs are done via the **Instructions / scope** field of the existing project routine, not by creating a new routine.

### Known issues at time of writing (2026-05-17)
- Atlassian allowlist not yet open for `api.atlassian.com` — CM-19 (1 image) and CM-27 (7 images) currently have broken Atlassian URLs in the wiki UI section. Will self-heal on the next fire after the allowlist is opened.
- Plan A Gmail OAuth (External + Testing) — refresh token expires every 7 days. Routine Owner must run `routines/oauth_setup.py` weekly until the migration to Plan B (Workspace service mailbox) is complete.
- `automation/sync.py` is **deprecated** (commit ad4e419) — emits pre-canonical schema. Use the scheduled routines instead. The CLI prints a warning at startup but still runs for backward compatibility.

---

## 20. Pro Plan Routine / Trigger Limitation

> **Verification:** the existence of routine/trigger limits on the Anthropic Pro plan is referenced in the architecture doc (`docs/ARCHITECTURE.md` line 53 mentions cron minimum interval). The exact numeric limit on concurrent triggers is **Not verified from current files** — confirm with your plan's terms before fleet expansion.

### Why this matters
The Anthropic Pro plan has a cap on the number of scheduled triggers and (likely) a cap on the number of routine fires per day. Creating one routine per feature (e.g. one for CM-2, one for CM-3, one for CM-19) would quickly exhaust the trigger budget. The fleet architecture is built around **one routine per project**, not one routine per feature.

### What this means in practice

- **Project-level routines are preferred.** `cm_daily_sync` handles every CM-* story. `pnp_daily_sync` handles every PNP-* story. New OHRM module → one new routine (`roster_daily_sync`, `leave_daily_sync`, etc.).
- **Individual feature updates** are handled through the **same project routine** by adjusting Instructions/scope (per § 10 above). Example: PL wants only CM-19 + CM-27 reprocessed → edit the CM routine Instructions to `Process only Jira stories CM-19 and CM-27.`, click Run now.
- **Scheduled triggers should be used carefully.** Default cron is daily at 07:00 / 06:00 Asia/Colombo for OHRM. Don't schedule every-hour fires unless there's a real need.
- **Avoid unnecessary daily/weekly triggers** for projects that aren't actively shipping (e.g. an Epic in early planning).
- **Use manual runs for one-time feature updates.** "Run now" doesn't consume a trigger slot — it uses the existing trigger.
- **Keep triggers only for active projects** where recurring spec updates are valuable. Disable triggers for retired projects (the routine still works manually; the cron just doesn't fire).

### Fleet-level monitoring suggestion
Once the fleet grows past 3–4 routines, build a small dashboard (suggested in the review report's Recommended New Features) that lists every routine, last fire status, and any consecutive failures. Add to the roadmap when capacity allows.

---

## 21. Final Checklist Before PL Runs Routine

Use this before clicking "Run now":

- [ ] The project routine exists and is shared with you (`claude.ai/code/routines/<trigger_id>`).
- [ ] You can open the routine in the claude.ai UI without a 403.
- [ ] You have Jira access to the relevant project (Browse Projects permission).
- [ ] All target stories have `fixVersion` assigned.
- [ ] `fixVersion.released=true` OR `releaseDate ≤ today` (verified in Jira → Releases).
- [ ] All target stories are Done / Closed / Completed / Released.
- [ ] No target stories are Deferred / Cancelled / Duplicate / Won't Do / Removed from Scope.
- [ ] All target stories have a description with inline behaviour text (not "TBD", not Drive-link-only).
- [ ] Acceptance criteria are inline in the description or in a confirmed-final Jira comment.
- [ ] UI assets are attached in Jira if they should appear in the spec.
- [ ] You have reviewed the routine's Instructions and only customised the scope (not the workflow).
- [ ] No API keys are pasted into the Instructions field.
- [ ] (Optional, recommended for first runs of a quarter) `DRY_RUN=true` is set in the routine env vars so this is a preview.
- [ ] You're ready to read the email when it arrives (typically 2–5 minutes after Run now).
- [ ] You know how to find the Manual Actions section if it appears.

---

## 22. Final Recommendation

To roll this out smoothly across the team:

1. **Use one project-level routine per ongoing project.** Never create routines for individual features — adjust scope through the Instructions field instead. Pro plan trigger limits and operational hygiene both reinforce this.

2. **Let PLs run routines from the UI** and adjust only Instructions / scope. The 6 canonical resource files in GitHub are the source of truth for workflow; PLs read them as documentation, not as configuration to override.

3. **Keep API keys private and prefer service accounts.** A `wiki-sync@yourcompany.com` service account on Atlassian + GitHub + BookStack + Google Workspace is the single highest-leverage hardening step. Do this before the second PL is onboarded.

4. **Keep Jira as the source of truth.** Never let wiki release dates, BookStack revision history, or any external system drive the release gate. The routine refuses by design; the team should reinforce the same culturally.

5. **Use Claude Code only for setup, debugging, and implementation changes.** Daily operations are entirely through the claude.ai routines UI for PLs and the AUDIT SUMMARY / GitHub log / email for everyone else.

6. **Roll out gradually.** Validate the routine works on one project with one PL before expanding. Each new project adds a route via `routines/scaffold.py` — one command, full validation.

7. **Monitor the failure modes.** Daily check on the email reports. Weekly check on the Plan A Gmail token renewal. Quarterly check on token rotation. Annual check on whether to migrate from Pro plan to a higher tier if the fleet grows past the plan's trigger limits.

8. **Document new behaviours.** If a project has special exclusions or quirks, add them to `release-filter-policy.md` (for routine-level rules) or this guide (for operator-level guidance) — not in the per-routine prompt body, which is brittle.

The routine is designed so the boring path — release Jira, fire routine, get email, done — is the default. Manual actions are the exception, surfaced clearly, with a named owner. If you find yourself doing a lot of manual work outside this flow, that's a signal something is mis-configured; ping the Routine Owner.

---

## Appendix A — Cross-references

| Topic | Authoritative file | Section |
|---|---|---|
| Release gate (Jira-only) | `resources/release-filter-policy.md` | §1–§9 |
| Per-Epic project scan | `resources/release-filter-policy.md` | §15 |
| Dedup contract | `resources/release-filter-policy.md` | §10.3; `SKILL.md` §5-C.1–.5 |
| Bullet-form Scenario | `resources/specification-writing-guideline.md` | §2.2 / §2.4; `SKILL.md` §5-C.2 |
| UI section gallery-only rule | `resources/release-filter-policy.md` | §11.1-bis / §11.1-ter |
| Workflow steps | `resources/SKILL.md` | STEP 1–11 |
| Validation checks | `resources/SKILL.md` | STEP 6 (14 checks) |
| HTTP retry policy | `resources/SKILL.md` | Safety: HTTP retries |
| DRY_RUN support | `resources/SKILL.md` | STEP 1.1 / 7 / 9 / §9-G |
| Log filename pinning | `resources/SKILL.md` | STEP 9 |
| Email template | `resources/email_template.html` | + `SKILL.md` §9-A to §9-G |
| Secret rotation | `docs/SECURITY.md` | § "Rotation procedure" |
| Initial deployment | `docs/DEPLOY.md` | (entire) |
| Gmail OAuth setup | `docs/EMAIL_SETUP.md` | Plan A / Plan B |
| System architecture | `docs/ARCHITECTURE.md` | (entire) |
| New-project onboarding | `routines/scaffold.py` | `--help` |
| Smoke test (consistency validator) | `tests/smoke_test.py` | (entire) |

## Appendix B — Quick links

- Routine UI: `https://claude.ai/code/routines/<trigger_id>` (Routine Owner provides per project)
- GitHub repo: `https://github.com/<your-org>/ohrm-wiki-sync`
- BookStack: `https://enterprisewiki.orangehrm.com` (or your wiki base URL)
- Jira: `https://orangehrmenterprise.atlassian.net` (or your Jira base URL)
- Per-routine logs: `https://github.com/<your-org>/ohrm-wiki-sync/tree/main/logs/<routine_slug>`

## Appendix C — Glossary

- **ATC** — Acceptance Test Cases (the canonical 3-column table at the top of every spec page).
- **fixVersion** — Jira's version field; the routine's release gate.
- **release_scope** — the routine's configured fixVersion in `wiki_destination.json`.
- **STEP 5C** — the create-flow sub-routine that builds a new page from scratch when the configured page id returns 404.
- **PUT** — the BookStack API method used to update an existing page (vs POST for creating a new one).
- **STEP 6 check #N** — one of the 14 validation gates in `SKILL.md`; FAIL on any of them blocks the BookStack write.
- **CONFIRMED / SKIPPED / BLOCKED** — release gate outcomes from STEP 3.
- **SUCCESS / NO_CHANGE / SKIPPED / BLOCKED / FAILED** — overall run statuses.
- **manual_action** — an item the routine couldn't handle that needs human follow-up; surfaces in the email's red Manual Actions Required section.
- **DRY_RUN** — env var flag that skips STEP 7 (no BookStack write); everything else runs.
- **Routine Owner / Admin** — the person who configures the routine, holds the tokens, and debugs failures.
- **Project Lead (PL)** — the day-to-day operator who runs the routine for their project and actions manual_actions.

---

*End of guide. For questions or improvements, ping the Routine Owner. Last updated alongside commit `1b09efc` (UI gallery-only rule) + `512ce59` (PNP page_id update).*
