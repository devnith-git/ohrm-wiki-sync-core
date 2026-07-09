---
name: jira-wiki-spec-update
description: >
  Release-filtered universal routine that keeps a BookStack specification page
  in sync with a Jira project. Per fire it confirms the routine's configured
  fixVersion is released (Jira-only — never wiki/BookStack), filters to
  completed non-excluded stories at that fixVersion, composes a merged HTML
  patch using the release-filter-policy section schema (per-story sub-sections
  including `<h4>Interfaces (UIs)</h4>`), additively merges into the
  destination page, validates, writes one BookStack PUT, commits a per-run
  audit log to GitHub, and sends a notification email via Gmail API.
  Project-agnostic — works for any Jira project when wired via deploy.py.
---

# Jira-to-Wiki Specification Update — Release-Filtered Workflow

This skill is the runtime authority every scheduled routine reads at start of
run. The per-project routine prompts (`routines/<name>_daily_sync.prompt.md`)
are thin wrappers that carry only project-specific parameters; when the
prompt and this file disagree, **this file wins**.

**Default mode is read-only on every external system.** A write to BookStack
only happens after release confirmation + sanity gate + canonical-structure
validation all pass. Every write is pre-flighted with a GET to confirm the
target sits inside the Specification shelf.

---

## Authority order (when files disagree)

1. **`resources/release-filter-policy.md`** — top. Global Jira-only release
   eligibility rules; supersedes every other file.
2. `resources/specification-writing-guideline.md` — canonical structural
   authority for *anything not covered* by the release-filter policy
   (heading hierarchy, table rules when legacy tables remain on the page,
   forbidden headings, etc.).
3. `resources/SKILL.md` — this file. Workflow steps and validators.
4. `resources/WIKI_PAGE_RENDER.md` — HTML render mechanics (heading levels,
   list formatting, anchor naming).
5. `routines/<name>_daily_sync.prompt.md` — per-routine parameters
   (JIRA_PROJECT, FIRE_TIME, routine slug). May not override anything above.

If any of (1)–(4) is missing at STEP 2, abort `status=BLOCKED
reason='resources/ unreachable — cannot proceed without canonical rules'`.

---

## 0. Routine inputs

Routines do **not** ask the operator anything at run time — they're scheduled
jobs. Every input is derived from the trigger config + the cloned repo +
Jira.

| Input | How it's derived |
|---|---|
| Project name | `JIRA_PROJECT` constant in the routine prompt (`CM`, `PNP`, etc.) |
| Routine slug | `<jira_key>_daily_sync` (matches a key in `routine_destinations`) |
| Configured fixVersion (`release_scope`) | `routine_destinations.<slug>.release_scope` in `wiki_destination.json` |
| Wiki destination page | `routine_destinations.<slug>.page_id` in `wiki_destination.json` |
| Reference files | Auto-discovered in STEP 2 from the cloned repo's `resources/` directory |
| Credentials | Read from env vars (`WIKI_TOKEN_ID`, `WIKI_TOKEN_SECRET`, `ATLASSIAN_CLOUD_ID`, `WIKI_BASE_URL`, optional `GITHUB_TOKEN` + Gmail OAuth set) |

**No interactive prompts. No "ask the user". No defaults that depend on prior
sessions.** Every run is fully self-contained.

---

## 1. Resource file discovery

Locate every reference file by **filename only** under `resources/`. Never
use absolute paths anywhere in the workflow.

| Reference label | Filename | Required? |
|---|---|---|
| **Release-filter policy** | `release-filter-policy.md` | **Required (top of authority)** |
| Canonical structural authority | `specification-writing-guideline.{md,html,pdf,txt}` | At least one variant required |
| This skill | `SKILL.md` | Required |
| Render mechanics | `WIKI_PAGE_RENDER.md` | Required |
| Destination + scope map | `wiki_destination.json` | Required |

Secrets (`WIKI_TOKEN_ID`, etc.) are **never** stored in `resources/` — they
come from claude.ai routine env vars at fire time.

---

## STEP 1 — Env-var verification (Bash)

First action of every run. Run the snippet below in a Bash block. Abort
`status=FAILED reason='missing env var'` if any required var is empty.

```
for v in ATLASSIAN_CLOUD_ID WIKI_BASE_URL WIKI_TOKEN_ID WIKI_TOKEN_SECRET; do
  if [ -z "${!v}" ]; then echo "FATAL: env var $v is not set"; exit 1; fi
done
echo "env check: ATLASSIAN_CLOUD_ID len=${#ATLASSIAN_CLOUD_ID}  WIKI_BASE_URL=$WIKI_BASE_URL  WIKI_TOKEN_ID len=${#WIKI_TOKEN_ID}  WIKI_TOKEN_SECRET len=${#WIKI_TOKEN_SECRET}  GITHUB_TOKEN len=${#GITHUB_TOKEN}"
```

### 1.1. Optional flag env vars (read once at STEP 1)

In the same Bash block, read the **DRY_RUN** flag. The routine
recognises truthy values (`true`, `1`, `yes` — case-insensitive); any
other value (including unset) means a real run:

```
DRY_RUN_INPUT="${DRY_RUN:-false}"
case "$(echo "$DRY_RUN_INPUT" | tr '[:upper:]' '[:lower:]')" in
  true|1|yes) DRY_RUN_MODE=1 ;;
  *)          DRY_RUN_MODE=0 ;;
esac
echo "DRY_RUN_MODE=$DRY_RUN_MODE  (input=\"$DRY_RUN_INPUT\")"
```

When `DRY_RUN_MODE=1`:
- STEP 5 / 5C / 6 run normally (compose merged HTML + validate).
- STEP 7 **SKIPS** the BookStack PUT/POST — no write occurs.
- STEP 8 AUDIT SUMMARY adds the line `Dry-run: YES (no write to BookStack)`.
- STEP 9 YAML frontmatter sets `dry_run: true`.
- STEP 10 email subject is prefixed with `[DRY RUN]` and the email body
  includes a yellow banner above Run Conclusion via `{{finalStatusMessage}}`
  (see §9-G).
- STEP 11 final banner reads `DRY RUN — JOB DONE.` instead of
  `VOILA! JOB DONE.`

Use this for: previewing the effect of a resource-file change,
onboarding a new project before flipping the real cron, or debugging
a flaky run. The flag is per-fire, set in the routine's Environment
Variables in the claude.ai UI (or via a one-shot trigger override).

Construct `AUTH="Authorization: Token ${WIKI_TOKEN_ID}:${WIKI_TOKEN_SECRET}"`
as a shell variable; pass it via `-H "$AUTH"`. **Never echo AUTH. Never use
`set -x`.** Mask any logged curl as
`Authorization: Token <REDACTED>:<REDACTED>`.

The AUDIT SUMMARY `Credentials:` line MUST say
`from-env (lengths only — no values)`.

---

## STEP 2 — Repo-aware bootstrap (resource-folder preflight)

This step is **mandatory and globally identical** across every routine
(CM, PNP, Roster, etc.). The resource folder is the single source of
truth for all canonical rules; no routine is allowed to skip the scan
or to fall back to in-prompt heuristics.

1. `ls -la` to verify `resources/`, `automation/`, `routines/`, `docs/`.
2. Read **all six** canonical resource files in `resources/` (in this
   authority order):
   - `release-filter-policy.md` — top of authority
   - `specification-writing-guideline.md` (or html/pdf/txt variant)
   - `SKILL.md` (this file)
   - `WIKI_PAGE_RENDER.md`
   - `wiki_destination.json`
   - `email_template.html` — STEP 9 render mechanics
3. Print the **resource-bootstrap banner** (visible in every run log
   so operators can confirm the scan ran). Format:
   ```
   ==================== RESOURCE BOOTSTRAP ====================
     [✓] resources/release-filter-policy.md         (<N> bytes)
     [✓] resources/specification-writing-guideline.<ext>  (<N> bytes)
     [✓] resources/SKILL.md                          (<N> bytes)
     [✓] resources/WIKI_PAGE_RENDER.md               (<N> bytes)
     [✓] resources/wiki_destination.json             (<N> bytes)
     [✓] resources/email_template.html               (<N> bytes)
   Authority order (top wins):
     release-filter-policy.md
       > specification-writing-guideline.<ext>
         > SKILL.md
           > WIKI_PAGE_RENDER.md
             > routines/<slug>_daily_sync.prompt.md
   Mode: 'repo-aware' (git <short hash>)
   =============================================================
   ```
   If any file is missing or unreadable, render `[✗]` against it and
   abort `status=BLOCKED reason='resources/ unreachable — cannot
   proceed without canonical rules'`. **Never invent a rule from
   training data when a resource is unreachable; abort cleanly.**
4. Locate this routine's slug entry in `routine_destinations`. Capture:
   - `page_id` → `TARGET_PAGE_ID`
   - `release_scope` → `RELEASE_SCOPE`
   - `jira_project_key` → `JIRA_PROJECT_KEY`
   If `release_scope` is empty or missing → abort
   `status=BLOCKED reason='release_scope not configured for routine <slug>'`.
5. The banner above is REQUIRED — STEP 9 (audit log) validates that
   the run actually emitted it. A run that skipped the banner is
   recorded as `validation_warning: resource_bootstrap_banner_missing`
   in the log frontmatter (so it surfaces in the email).
6. **Refresh `specification_nav_tree`** per `release-filter-policy.md`
   §16 (strict global rule — applies to every routine, every fire).
   Fetch the live shelf with `GET /api/shelves/3` to obtain
   `LIVE_SPEC_BOOKS`, then walk each `book_id` via
   `GET /api/books/<book_id>` to capture every chapter and page with
   its live `sort_order` / `slug` / `name`. Diff against the stored
   `specification_nav_tree.books[]` in `wiki_destination.json` per
   §16.3 (additive append, deprecate on disappearance, rename in
   place). Update `node_count` + `last_synced_at` + `last_synced_run`
   per §16.4. Self-commit the refreshed block back to the current
   branch when the diff is non-empty (§16.5). The audit log MUST
   include a `## STEP 2.6 — Nav-Tree Sync` section enumerating every
   diff line plus the new `node_count` totals. Abort
   `status=BLOCKED reason='specification_nav_tree sync failed'` on
   any non-2xx during the walk.

   Agile routines have a fixed `page_id` configured per slug, so they
   consume the tree differently from the CS routine: instead of
   scoring candidates, they apply check NAV-2 at STEP 6 (the
   configured `TARGET_PAGE_ID` must still resolve to a live node in
   the refreshed tree). NAV-2 failure surfaces a manual_action so the
   operator knows their `routine_destinations.<slug>.page_id` is
   stale; the run still completes against the configured page (in
   case the deprecation was transient).

---

## STEP 3 — Release confirmation gate (Jira-primary)

**Authoritative reference: `release-filter-policy.md` §1–§6, plus §19 (Document
Release-Date Fallback).**

**Document fallback (§19):** Jira is primary. When a candidate `fixVersion` is
unreleased in Jira with no firm `releaseDate` (would be BLOCKED/SKIPPED), consult
`_core/resources/OrangeHRM_Enterprise_Release_Notes.docx` via
`python _core/automation/release_doc_fallback.py <docx>`: if the doc lists that
exact version with a firm `releaseDate <= today`, treat it as released with
`release_source = doc` (§19.2). Story-level: a no-`fixVersion` Story/Task may be
matched to a doc version by keyword (≥0.75) → apply with `release_source = doc`,
else WARNING + `manual_actions` (§19.3). Jira-confirmed data always wins (§19.5).

### 3-A. Fetch the configured fixVersion(s) from Jira

**`RELEASE_SCOPE` may be (a) a single version string, (b) a JSON array of
versions, or (c) the dynamic keyword `"all-released"`** (per
`release-filter-policy.md` §1). Treat a bare string as a one-element set.

- **Modes (a)/(b) — pinned set:** the set is exactly the configured
  version(s).
- **Mode (c) — `"all-released"` (dynamic):** first **enumerate every
  fixVersion in the project** (project-versions endpoint, paginate to
  completion, ignore `archived==true`). The candidate set is all of them;
  the §2–§6 gate below then keeps only the released ones. This is what lets
  the routine cover **all released release-lines** (e.g. every released
  Epic's fixVersion) without a config change when a new line ships. It ties
  into the §15 per-Epic scan — the versions that scan marks Released are
  exactly the ones that survive the gate here.

For **each** candidate version `V`, use the Atlassian MCP to get its version
object. Two equivalent paths:

- **Preferred:** call `getVisibleJiraProjects` / project-versions endpoint
  to list versions, then pick the one whose `name == V`.
- **Fallback:** call `searchJiraIssuesUsingJql` with
  `project = <KEY> AND fixVersion = "<V>"` requesting
  `fields=["fixVersions"]`, then inspect any returned issue's
  `fixVersions[]` for the entry whose `name == V`.

If a configured version object cannot be located → abort
`status=BLOCKED reason='configured fixVersion <V> not found in
project <KEY>'`. Record `Manual action required: create or rename the
fixVersion in Jira.`

### 3-B. Evaluate release confirmation

Today (`TODAY`) is the routine's execution timezone date (Asia/Colombo for
OHRM routines today; compute from UTC fire time + offset).

| `released` | `releaseDate` | Outcome | Status & log |
|---|---|---|---|
| `true` | * | **CONFIRMED** | log `Release confirmed - Jira fixVersion <V> for project <K> is marked as released.` — proceed |
| `false` | `<= TODAY` | **CONFIRMED** | log `Release confirmed - Jira fixVersion <V> for project <K> has a releaseDate in the past or today.` — proceed |
| `false` | `> TODAY` | **NOT YET** | `status=SKIPPED reason='fixVersion not released yet'`, log `Skipped - Configured fixVersion <V> for project <K> is not released yet because Jira releaseDate is in the future.` — proceed to STEP 8 (AUDIT) + STEP 9 (log) + STEP 10 (email), skip STEP 4–STEP 7. |
| `false` | empty/null/missing | **BLOCKED** | `status=BLOCKED reason='fixVersion not confirmed released'`, log `Blocked - Configured fixVersion <V> for project <K> is not confirmed as released in Jira because released=false and releaseDate is empty. Release Manager or Project Admin must either mark the version as released or set a valid releaseDate in Jira.` — same: proceed to STEP 8/9/10 only. |

**Apply this table per candidate version.** `CONFIRMED_VERSIONS` = every
version whose outcome is CONFIRMED. A NOT_YET / BLOCKED version records its
own verbatim log line but does NOT block the others. If
`CONFIRMED_VERSIONS` is empty, set the aggregate `release_gate` to the
worst per-version outcome (BLOCKED > NOT_YET), skip STEP 4–STEP 7, and
proceed to STEP 8/9/10. On NOT YET / BLOCKED outcomes, record the verbatim
log line(s) in the run log's `release_gate` field (see §STEP 9). The audit
email surfaces these so the Release Manager sees them.

### 3-C. On ≥1 CONFIRMED — query stories

Query the union of confirmed versions:

```jql
project = <JIRA_PROJECT_KEY> AND fixVersion in ("<V1>", "<V2>", ...)
```

(For a one-element `CONFIRMED_VERSIONS` this is equivalent to
`fixVersion = "<V1>"`.) Do **not** use the JQL `releasedVersions()`
function — it keys off the `released` flag only and would miss versions
that are released by past `releaseDate` with `released==false` (§6).

Fetch with `fields = ["summary","description","status","issuetype",
"resolution","labels","fixVersions","attachment","comment","priority",
"customfield_*"]`. Paginate with `nextPageToken` until `isLast=true`.

### 3-D. Per-Epic project scan (REQUIRED — informational)

**Authoritative reference: `release-filter-policy.md` §15.**

In addition to the fixVersion-scoped story query above, run a
**project-wide Epic scan**. This pass does NOT change which stories
get written to the wiki — it feeds the email's `Epic Release Status`
section so the Release Manager can see every Epic in the project and
which ones are released vs pending.

Run this scan on **every routine, every run**, regardless of the
STEP 3-B release-gate outcome (CONFIRMED / NOT_YET / BLOCKED). On
NOT_YET / BLOCKED runs the scan still executes so the email still
reports the project's Epic landscape.

1. **Query:**
   ```jql
   project = <JIRA_PROJECT_KEY> AND issuetype = Epic
   ```
   Fields: `["summary","status","resolution","fixVersions","labels"]`.
   Paginate to completion. Cap at 200 Epics — log
   `Note - epic scan capped at 200 results.` if exceeded.

2. **Classify each Epic** per §15.2:
   - **Released** (`✓`) — at least one `fixVersion.released==true` OR
     `fixVersion.releaseDate <= TODAY`.
   - **Pending** (`⚠`) — every fixVersion is `released==false` AND
     (no `releaseDate` OR `releaseDate > TODAY`).
   - **Unassigned** (`—`) — `fixVersions[]` is empty.
   - **Excluded** (`✗`) — `status.name` / `resolution.name` /
     `labels[]` contains any of the §9 exclusion tokens
     (`cancelled`, `deferred`, `dropped`, `duplicate`, `wont-do`,
     `won't do`, `moved`, `not-applicable`, `removed-from-scope`,
     `na`, `rejected`). The Excluded check wins over Released /
     Pending — a Cancelled Epic with a released fixVersion is still
     Excluded.

3. **Record** per-Epic data for the email (per §15.4):
   - `key`, `name` (Jira summary), `fix_versions` (comma-separated
     names or `—`), `status` (Released / Pending / Unassigned /
     Excluded), `symbol` (`✓` / `⚠` / `—` / `✗`).

4. **Update counters:**
   - `epics_scanned`, `epics_released`, `epics_pending`,
     `epics_unassigned`, `epics_excluded`. These go in the STEP 9
     log frontmatter AND populate the email's Epic Release Status
     summary line.

5. **Print one-line summary** to the run log:
   ```
   Epic scan: <epics_scanned> Epics in <project> — ✓ <released>  ⚠ <pending>  — <unassigned>  ✗ <excluded>
   ```

---

## STEP 4 — Per-issue eligibility filter

For each issue returned by STEP 3-C, run the buckets below **in order**.
The first bucket that matches wins; the issue is recorded in that
bucket's counter and never re-checked.

### 4-A.0. Issue-type bucket (`release-filter-policy.md §8`)

Classify by `issuetype.name`:

| Type | Bucket | Counter | Per-issue log |
|---|---|---|---|
| `Epic` | **excluded by type** | `epics_found` (no `epics_processed` — Epics never feed ATC rows) | `Excluded - <KEY> is an Epic; spec coverage flows through its child stories.` |
| `Story` | **processed** | `stories_processed` | — |
| `Task` | **processed** | `tasks_processed` | — |
| `Bug` | **excluded by type by default — but see the requirement-defect carve-out in `bug-requirement-filter-policy.md`. A Bug is PROMOTED to processing (treated like a Story for STEPs 4-A → 5) if it satisfies the §1 gate of that policy: any of (a) `Type Of Defect = Requirement`, (b) `[Requirement]` summary prefix, or (c) a qualifying comment per §1.3 of that file — AND all Story-gate checks (release confirmation, completion, non-exclusion, source-material). Otherwise the Bug stays excluded.** | `bugs_found` (plus `bugs_requirement_found` + `bugs_requirement_processed` per `bug-requirement-filter-policy.md` §5.2) | If excluded: `Excluded - <KEY> is a Bug; not a requirement defect (Type Of Defect='<value or unset>', summary has no [Requirement] prefix, no qualifying comment in last 50 comments).` If promoted: log line per `bug-requirement-filter-policy.md` §5.1 naming the signal that matched. |
| `Sub-task` | **excluded by type** | `subtasks_found` | `Excluded - <KEY> is a Sub-task; issue type not in spec coverage scope.` |
| `Improvement` / `Refactor` / `Spike` / anything else | **excluded by type** | `other_found` | `Excluded - <KEY> is a <Type>; issue type not in spec coverage scope.` |

The `*_found` counts always include processed entries — i.e.
`epics_found == epics_processed + epics_skipped + epics_blocked`. The
"found" counters are what populates the email's top-band Discovery
status bar.

If the issue is excluded by type, **stop here** — do not run 4-A / 4-B /
4-C. Move to the next issue.

**Exception for Bugs — STEP 4-A.0-bis (requirement-defect carve-out):**
before excluding a Bug, run the §1 gate of
`bug-requirement-filter-policy.md` (signals (a) `Type Of Defect = Requirement`,
(b) `[Requirement]` summary prefix, (c) qualifying comment per §1.3 of
that file). If ANY signal qualifies, the Bug is **promoted** — it joins
`ELIGIBLE_STORIES` and runs through 4-A / 4-B / 4-C / 5 exactly like a
Story. The per-issue log records which signal matched (§5.1 of that
file). If none qualify, the default exclusion applies. This applies to
**every routine** in this repo — CM, PNP, Roster, Orange Sign, and the
dynamic CS routine alike.

### 4-A. Story status is NOT a gate (`release-filter-policy.md §7`)

Per the §7 fixVersion-priority rule, the routine does **NOT** check a
story's workflow status. Any Epic / Story / Task that passed 4-A.0 and is
attached to a released `fixVersion` (STEP 3) proceeds — `New`,
`In Progress`, `Done`, `Closed`, `CPO/PM Accepted` all qualify. There is
no completion skip here; the only per-issue filters are 4-B (exclusion),
the §8.5 usage/telemetry-metrics exclusion, and the source-material
sanity gate.

### 4-B. Exclusion check (`release-filter-policy.md §9`)

Build a haystack from `resolution.name`, `status.name`, and `labels[]`
(lowercased). If the haystack contains any of the exclusion tokens:

`deferred`, `cancelled`, `rejected`, `removed-from-scope`, `dropped`,
`duplicate`, `wont-do`, `won't do`, `moved`, `not-applicable`, `na`

→ record `Skipped - Story is excluded from release scope.` and skip to next.

### 4-B.1. Comment intelligence — deprioritization gate (`release-filter-policy.md §10.5`)

Beyond the label/resolution haystack above, read the issue's comments
(`GET /rest/api/3/issue/<KEY>/comment?expand=renderedBody&maxResults=50&orderBy=-created`,
newest-first; reuse any fetch the bug-requirement carve-out already did
this run; ignore bot authors per bug-requirement §1.3). If the **latest
disposition** on the work is a deprioritization / de-scope per the §10.5
phrase set (`deprioriti[sz]ed`, `de-scoped`, `out of scope`, `dropped
from the release`, `moved to the backlog`, `pushed to the next sprint`,
`won't do`, `parked`, `shelved`, …) → record `Excluded - <KEY>
deprioritized per comment <id> by <author> (<date>): "<excerpt>"` and skip
to next. A later re-prioritizing comment overrides an earlier
deprioritization (recency guard); the negative guard ignores quoted /
negated phrases. Comment-voiced **scope changes** (§10.5 bucket 2) are NOT
handled here — they are carried into STEP 5 as §10.4 CRUD evidence.

### 4-C. Source-material sanity gate (per-story)

Inspect the issue's `description`:

**Jira is the only source of truth.** The routine never fetches, opens,
or reads any external document (Google Drive, Google Docs, Figma,
Sketch, Confluence link, etc.). External links present in a Jira
description are treated as plain-text noise and ignored silently — no
log line, no warning, no "partial update" note. The routine extracts
only the inline Jira text and uses it as the source for canonical-table
updates.

| Description state | Action |
|---|---|
| Empty / null / `[]` ADF | record `Blocked - Jira description is empty. Add a textual description of the released behavior to the Jira ticket.` — skip story |
| No extractable behavior text (only external links, attachments, or non-text content) | record `Blocked - Jira description has no extractable behavior text. Add a textual description of the released behavior to the Jira ticket.` — skip story |
| Any usable behavior text (with or without external links alongside it) | keep story — process per STEP 5 |

The **per-issue Notes** log line for a kept story describes the
**actual canonical-table changes** the routine made, in the form
`Updated - <change summary>.` Examples:

- `Updated - ATC row #13 added; Form row added for 'Pay Grade'.`
- `Updated - ATC row #15 Feature name corrected: 'Salary Screen' → 'Salary Structure'.`
- `Updated - ATC row #18 scenario re-rendered to canonical bullet form; Audit Trail row added for 'Delete Pay Grade'.`

The Notes line is **never** about what the routine ignored or did not
read — it reports what changed in the spec page. If no canonical-table
change resulted (e.g. all bullets were already byte-equivalent), log
`No change - <S.key> already up to date.` instead.

For comments (per `release-filter-policy.md §10.5`): include text from a
comment as **behavior content** only when it's unambiguously final
(e.g. "Confirmed by PL", "Final UI per design review", explicit yes/no on
a question — §10.5 bucket 1). Uncertain or discussion comments are logged
`Skipped comment <commentId> - Not confirmed as final behavior.` A comment
that **changes a previously-stated requirement** (§10.5 bucket 2 — new
default/validation/option, renamed field, or a dropped sub-behaviour) is
**§10.4 CRUD evidence**: a changed value drives an Update (replace the
bullet/cell, log `Updated - … per comment <id>: <old> → <new>`); an
explicitly dropped behaviour drives an evidence-gated removal (op-4),
citing the comment. The story itself still flows through STEP 5+.

The **surviving** set (call it `ELIGIBLE_STORIES`) goes to STEP 5.

---

## STEP 5 — Compose merged HTML (STRICT CANONICAL — 5 tables + UI section)

**Authoritative references in this order:**
1. `specification-writing-guideline.md` — the 5 canonical tables and the
   UIs-at-end rule. **This file is the structural authority.** The
   routine MUST NOT author anything outside what the guideline allows.
2. `release-filter-policy.md` §10 / §10.1 / §10.2 / §11 — release-column
   on ATC, link-to-ATC for other tables, UI merge algorithm.
3. `WIKI_PAGE_RENDER.md` §2 / §3 — exact HTML shapes per table.

### 5-A. Read existing page state

`GET /api/pages/<TARGET_PAGE_ID>` to fetch the current HTML body and the
`updated_at` timestamp. Cache as `PRIOR_HTML` and `PRIOR_REV`.

Pre-flight verification (refuse to proceed if any drift):
- response `name` matches `routine_destinations.<slug>.page_name`.
- response `book_id` matches `routine_destinations.<slug>.book_id`.
- response `chapter_id` matches `routine_destinations.<slug>.chapter_id`
  (or null on both sides).
- the page's book is in shelf `id=3`.

### 5-B. Locate (or initialise) the 5 canonical tables and the UI section

Parse `PRIOR_HTML` to find:
- `ATC_TABLE` — the first `<table>` whose header row text is exactly
  `#  Feature  Scenario` (allowing for whitespace / `<strong>`). 3
  columns, canonical.
- `LIST_TABLE` — the first `<table>` whose header row matches
  `Column Name  Sort-able?  Description`. May be absent.
- `SEARCH_TABLE` — header `Field Name  Type  Available Options  Default Value  Field Behavior`. May be absent.
- `FORM_TABLE` — header `Field Name  Type  Default Value  Validation(s)  Validation Message(s)  Field Behavior`. May be absent.
- `AUDIT_TABLE` — header `#  Action  How it is tracked in Audit Trail`. May be absent.
- `UI_SECTION` — the `<h2>User Interfaces (UIs)</h2>` block at end of
  page (case-insensitive; also accept `<h2>Interfaces (UIs)</h2>` or
  `<h2>User Interfaces</h2>`). May be absent.

If a table is absent and Jira data needs it, the routine **creates** it
at the canonical position (before the UI section, in the canonical
order: ATC → List → Search → Form → Audit Trail). Each new table is
emitted in the exact column shape from `WIKI_PAGE_RENDER.md` §2.

**Never extend a canonical table with extra columns.** If a page is
encountered with an ATC table that has 4+ columns (an artefact of a
prior wrong-policy run), the routine treats anything beyond the
canonical 3 as legacy content to preserve verbatim — it does NOT
author new data in the 4th column on subsequent runs.

### 5-C. Map each eligible issue to canonical table rows

For each issue in `ELIGIBLE_STORIES` (Epic / Story / Task that passed
STEP 4):

1. **Match & idempotency lookup** (canonical de-duplication contract —
   see §5-C.1 / §5-C.2 below; policy-level statement in
   `release-filter-policy.md` §10.3). The lookup runs in this strict
   order; the **first** match wins, and the issue's contribution merges
   into the matched row:

   - **(a) Jira-key match (strict).** Scan `ATC_TABLE` for any row
     whose Feature cell carries `{S.key}` inside its parenthetical key
     list. A row may carry one key (`(CM-2)`) or many
     (`(CM-100, CM-200)`) when multiple stories contributed to the
     same feature. If matched, the row is `ATC_ROW`; UPDATE in place
     per §5-C.2 (do NOT append the key — it is already there).

   - **(b) Semantic Feature/Topic match.** If (a) did not match,
     compute `normalized_feature(name) = lowercase(strip_key_list(trim(name)))`
     with internal whitespace collapsed to single spaces. Compare the
     normalized intended Feature name for `S` against every existing
     row's normalized Feature cell. Match if either:
     - Names are equal after normalization, OR
     - Both names belong to the same synonym group per §5-C.1.

     If matched: the row is `ATC_ROW`; UPDATE in place per §5-C.2
     **AND** append `, {S.key}` to the existing Feature-cell key list
     (so future runs match by (a)). The canonical Feature name in the
     cell stays as it was — only the key list grows.

   - **(c) No match.** Append a new row at the end of `ATC_TABLE`. The
     Feature cell ends with ` ({S.key})`.

2. **Compose the ATC row** for issue `S` (3 cells — canonical):
   - `#` — next sequential integer (max existing `#` + 1).
   - `Feature` — short title in title case, ending with `(<S.key>)`.
     Source: Jira `summary`, trimmed and de-prefixed (strip leading
     `Bug -`, `Story:`, `Task:` if present).
   - `Scenario` — a **bulleted list** in present tense per
     `specification-writing-guideline.md` §2.2 (*"Use bullet points
     for multiple details inside table cells"*). One `<li>` per
     distinct test case / released behavior point. Plain text inside
     each `<li>` — quotation marks around UI strings, button labels,
     tooltips, and inline messages are kept verbatim. Source: distil
     from Jira `description` + confirmed-final comments. Author the
     cell as:
     ```html
     <ul>
       <li>{first test case / behavior point}</li>
       <li>{second test case / behavior point}</li>
     </ul>
     ```
     A feature with a single test case still uses `<ul><li>...</li></ul>`
     (one item) — the bullet shape is canonical regardless of count.
     **Never** author a paragraph or run-on sentences in this cell;
     **never** merge multiple test cases into one `<li>`.

   No `Release` cell. fixVersion is not part of page content — Jira
   owns the question "which release did this ship in".

3. **Decide which non-ATC tables this issue contributes to** based on
   Jira content:

   | Jira content describes… | Add row(s) to… |
   |---|---|
   | A list view (with sortable columns) | `LIST_TABLE` |
   | A search / filter section | `SEARCH_TABLE` |
   | A form (fields, validations, defaults) | `FORM_TABLE` |
   | An auditable action (create / update / delete that's tracked) | `AUDIT_TABLE` |

   If none of these apply (e.g. an Epic whose only contribution is the
   ATC row), the issue is fully represented by its ATC row alone. That
   is acceptable and the routine logs `Note - <S.key> contributes ATC
   row only; no List/Search/Form/Audit content extracted.`

4. **Compose non-ATC rows** (one per applicable table). The non-ATC
   dedup contract (§5-C.3) applies — match the row by the table's
   match cell first (Jira-key then semantic name), UPDATE in place on
   match or APPEND on no match. Each row's leftmost cell carries
   `(ATC #<n>)` (linking to the owning ATC row's `#` from step 2)
   followed by the parenthetical Jira-key list — e.g.
   `Pay Grade Code (ATC #4) (CM-2)` on first contribution, growing to
   `Pay Grade Code (ATC #4) (CM-2, CM-7)` when a later story
   contributes to the same field. Column shapes are STRICT — see
   `WIKI_PAGE_RENDER.md` §2.2 / §2.3 / §2.4 / §2.5.

5. **Idempotency on re-runs**: when `ATC_ROW` is matched in step 1.a or
   1.b, compose `MERGED_SCENARIO` per §5-C.2. If `MERGED_SCENARIO` is
   byte-equivalent to the existing Scenario cell after whitespace
   normalization, NO-OP and log
   `No change - <S.key> ATC row already up to date.` Otherwise,
   REPLACE the Scenario cell value with `MERGED_SCENARIO`, preserving
   the `#`. The Feature cell keeps its canonical name; only its
   parenthetical key list may have grown (per step 1.b).

#### 5-C.1 Synonym Set — semantic equivalence for Feature / Topic / Field / Action names

Two names that refer to the same feature in the user's mental model
(same screen, same data, same behavior) MUST collapse to ONE row.
The list below is the canonical synonym set — non-exhaustive; when in
doubt, lean toward **merge** (one row, merged scenario) rather than
**split**. Merging is reversible if a later iteration finds the items
really were separate; splitting leaves duplicate rows the spec author
has to consolidate manually.

| Canonical name (kept verbatim in the cell) | Synonyms folded into the canonical row |
|---|---|
| Audit Trail | Audit Log, Audit History, Activity Log, Change History |
| Pay Grade | Salary Grade, Compensation Grade |
| Snapshot | Snap Shot, History View, Salary History (when context = compensation snapshot) |
| List View | Grid View, Table View, Listing (when context = data list) |
| Search | Filter, Filters, Search & Filter |
| Form | Add/Edit Form, Input Form, Modal Form |
| User Interfaces (UIs) | UI, Screens, User Interface (singular) |
| Add Employee Wizard | New Employee Wizard, Employee Onboarding Wizard |
| Salary Structure | Salary Screen, Salary Configuration (legacy names) |

**Rule for unlisted names:** normalize both candidate names (lowercase,
strip key list, collapse whitespace, drop trailing punctuation) and
treat them as equal if (i) they describe the same screen / data /
action in the spec author's reading, or (ii) one is a singular form of
the other (`Filter` vs `Filters`), or (iii) one is a casing/spacing
variant (`SnapShot` vs `Snap Shot` vs `Snapshot`).

**Separate rows are allowed ONLY when** the specification clearly
treats two names as distinct features (e.g. `Audit Trail` for HR and
`Audit Trail` for Finance with disjoint scopes on the same page).
Record the distinction in the Scenario / Description cell so a future
run can re-match correctly.

#### 5-C.2 Scenario merge rule — preserve coverage, reflect latest behavior (bullet-form)

**Format authority: `specification-writing-guideline.md` §2.2** — multi-detail
table cells use bullets. The Scenario cell is rendered as a `<ul>` of
`<li>` items, one bullet per distinct test case / behavior point. Merges
operate at the **bullet-item granularity**, not at the sentence level.

When step 1.a or 1.b matches an existing row, compose
`MERGED_SCENARIO_BULLETS` from `OLD_BULLETS` (the existing list of `<li>`
items) and `NEW_BULLETS` (the list of bullet items distilled from the
current Jira description + confirmed-final comments — one bullet per
distinct test case / behavior point):

1. **Legacy paragraph-form repair** — if `OLD_SCENARIO` is a paragraph
   (no `<ul>` / `<li>`, or a single `<li>` containing multiple distinct
   sentences), it is **out-of-format legacy content from earlier runs**.
   Split it into discrete `<li>` items along sentence boundaries (one
   distinct test case per item), then proceed with the merge below. Log
   `Updated - <S.key> scenario re-rendered from paragraph to canonical bullet form.`
   This is the only path that rewrites legacy content; the prohibition
   on dropping coverage in step 4 still applies.

2. **For each item in `NEW_BULLETS`:**

   a. **Byte-equivalent bullet already present** — `new_item` matches
      an existing `<li>` in `OLD_BULLETS` after whitespace normalization.
      Keep that `<li>` as-is. Log
      `No change - <S.key> scenario bullet already covered.` (Quiet on
      a per-bullet basis; the row-level summary still logs.)

   b. **Same test case, updated wording** — `new_item` describes the
      same test case as an existing `<li>` but with newer terminology
      (e.g. `Salary Screen` → `Salary Structure`, `Pay Grade Name` →
      `Pay Grade Label`). REPLACE the matching `<li>` with `new_item`.
      Topic-match heuristic: shared keyphrases (≥ 60% token overlap on
      content words after stopword removal) or shared `<UI string>` /
      `<button label>` references between old and new. Log
      `Updated - <S.key> scenario bullet reworded to reflect latest released behavior.`

   c. **New test case for the same feature** — `new_item` describes a
      distinct test case (different rule, edge case, or behavior of the
      same feature). APPEND it as a new `<li>` at the end of the list.
      Log `Updated - <S.key> scenario bullet added.`

   d. **Supersession (evidence-gated removal — per `release-filter-policy.md`
      §10.4 op 4)** — the Jira issue **explicitly** states that an
      existing behaviour no longer applies (trigger phrasing: *removed,
      no longer, deprecated, discontinued, replaced by, renamed to,
      dropped, withdrawn, retired, superseded by*, mapping clearly to a
      specific existing `<li>`). REMOVE that matching `<li>`. Log
      `Removed - <S.key> scenario bullet superseded: "<old bullet>"`.
      This is the ONLY path that removes a bullet — it requires explicit
      Jira evidence naming the superseded behaviour; mere omission never
      triggers it.

3. **For each `<li>` in `OLD_BULLETS` not matched by any `new_item`:**
   KEEP verbatim — it represents earlier-confirmed released behavior.
   **Never drop existing bullets** just because the current Jira
   description omits them; that would silently shrink coverage. (The
   sole exception is step 2.d above — explicit, evidence-gated
   supersession — which removes a *named* bullet on Jira evidence, not on
   omission. Absence ≠ removal.)

4. **Bullet hygiene per item** — every `<li>`:
   - Is plain text (present tense, declarative). `<strong>` and `<em>`
     allowed for inline emphasis on field / button / tooltip labels.
     `<br>` allowed only to wrap intentionally long bullet text.
   - Keeps UI strings, tooltips, button labels, inline messages, and
     navigation paths in double quotes verbatim (e.g.
     `"Cannot delete a pay grade in use by current employees."`).
   - Does NOT contain nested `<ul>` / `<ol>` unless the bullet has
     genuine sub-detail per `specification-writing-guideline.md` §2.2
     Sample bulleting (Level 2 detail). Two levels max.
   - Does NOT contain `<img>` (UI screenshots belong in the global
     User Interfaces (UIs) section, not in table cells).

5. **No item-count cap** — the bullet list grows naturally as a feature
   accumulates test cases across releases. The 3-sentence soft cap from
   prior SKILL.md versions is **withdrawn**; coverage MUST NOT be
   trimmed to fit a count.

6. **Empty Scenario** — never emit an empty `<ul></ul>`. If a story has
   no extractable test case (e.g. description is only an external Drive
   link — handled earlier at STEP 4-C), the routine logs
   `Blocked - Jira description provides no extractable test case for <S.key>.`
   and skips the row.

This rule applies identically to the free-text cell of every non-ATC
table per §5-C.3 — the bullet-form shape is **non-negotiable for all
of these cells** regardless of whether the cell currently has one or
many behaviour points:

| Table | Cell | Shape | Example (single bullet — yes, still `<ul><li>`) |
|---|---|---|---|
| List | `Description` | `<ul><li>...</li></ul>` | `<ul><li>By default, the list is sorted ascending by this column.</li></ul>` |
| Search | `Field Behavior` | `<ul><li>...</li></ul>` | `<ul><li>Filters the list to entries whose Pay Grade matches the selected value.</li></ul>` |
| **Form** | **`Field Behavior`** | **`<ul><li>...</li></ul>`** | `<ul><li>Based on the selected currency in this field, the currency symbol appears in all amount fields within the Salary tab.</li></ul>` (single bullet — still `<ul><li>`, NEVER plain text) |
| Audit Trail | `How it is tracked in Audit Trail` | `<ul><li>...</li></ul>` (or the canonical multi-paragraph Section / Performed Screen / Action Description / Sample Audit format per `specification-writing-guideline.md` §2.4 Audit Trail when applicable) | `<ul><li>Section: Compensation. Performed Screen: Salary. Action Description: ...</li></ul>` |

**Why every cell, even single-bullet:** mixing plain-text cells with
`<ul><li>` cells in the same table column produces visual inconsistency
across rows on the rendered BookStack page (different vertical
spacing, different left margins, different bullet visibility). The
shape MUST be consistent so the column reads as a coherent vertical
stack. Spec authors who scan a column for related behaviours need to
see them in the same shape, not "some bulleted, some prose".

**The Form table has TWO exception cells** that DO NOT use `<ul><li>`
— per `specification-writing-guideline.md` §2.4 Form note, those use
`-` (hyphen + space) prefixed plain-text lines separated by `<br>`
within a single `<td>`:

- Form `Validation(s)` — e.g. `- Required<br>- Maximum length: 50<br>- Allowed characters: alphanumeric + space`
- Form `Validation Message(s)` — e.g. `- "Pay Grade is required"<br>- "Maximum 50 characters"`

These two columns are the **only** free-text cells across all five
canonical tables that are NOT `<ul><li>`. Every other free-text cell
(including Form's Field Behavior) uses bullets.

**Legacy plain-text repair (parallels §5-C.2 step 1 for ATC):** when
the routine encounters an existing Form / List / Search / Audit Trail
row whose free-text cell is plain text (no `<ul>` / `<li>`, or a
single `<li>` containing multiple distinct behaviours separated by
`. ` / `;`), it is **out-of-format legacy content from earlier runs**.
Split it into discrete `<li>` items along sentence / clause boundaries
(one distinct behaviour per item), then proceed with the §5-C.2 merge.
Log `Updated - <table> row '<match cell>' free-text cell re-rendered
from paragraph to canonical bullet form.` This repair is the only path
that rewrites legacy content; the prohibition on dropping coverage
(§5-C.2 step 3) still applies.

#### 5-C.3 Non-ATC tables — same dedup contract, per-table match cell

The match & merge contract from §5-C step 1 / §5-C.2 applies to every
canonical table. The match cell differs per table:

| Table | Match cell | Free-text cells (use §5-C.2 merge) | Enumerated cells (latest Jira wins) |
|---|---|---|---|
| **ATC** | `Feature` | `Scenario` | — |
| **List** | `Column Name` | `Description` | `Sort-able?` |
| **Search** | `Field Name` | `Field Behavior` | `Type`, `Available Options`, `Default Value` |
| **Form** | `Field Name` | `Field Behavior`, `Validation Message(s)` | `Type`, `Default Value`, `Validation(s)` |
| **Audit Trail** | `Action` | `How it is tracked in Audit Trail` | — |

For each non-ATC table the routine touches in this run:

1. Apply §5-C step 1 (Jira-key match → semantic match → no match) using
   the table's match cell.
2. On match: UPDATE in place. Free-text cells merge per §5-C.2.
   Enumerated cells: latest Jira value wins; on conflict log
   `Updated - <table> row <name>: <field> changed: <old> → <new>` and
   apply.
3. On no match: append a new row per the canonical column shape
   (`WIKI_PAGE_RENDER.md` §2.2 / §2.3 / §2.4 / §2.5). The leftmost
   cell ends with ` (ATC #<n>)` (linking to the owning ATC row) and
   carries a parenthetical key list — typically just the one
   contributing Jira key on first creation.

   Example List-table row leftmost-cell format:
   `Pay Grade Code (ATC #4) (CM-2)`. On a future run where `CM-7`
   also describes the same `Pay Grade Code` column, the cell becomes
   `Pay Grade Code (ATC #4) (CM-2, CM-7)`.

#### 5-C.4 Cross-table field-completeness check

After §5-C.1 / §5-C.2 / §5-C.3 dedup is applied, run a completeness
pass:

1. For each Field / Action / Topic name extracted from this run's
   `ELIGIBLE_STORIES`, determine the set of applicable canonical
   tables based on what the Jira content describes:
   - List — if the field is a sortable / displayed column on a list view.
   - Search — if the field is filtered or searched on.
   - Form — if the field appears in an add / edit form (with type,
     default, validations).
   - Audit Trail — if the field's create / update / delete is audited.
2. For each (field, applicable table) pair, check whether the field
   already has a row in that table (using the table's match cell per
   §5-C.3, with synonym folding per §5-C.1).
3. If a field is described by Jira but missing from an applicable
   table, the routine ADDS the row in this same run (per §5-C.3
   step 3) — even if the field's "primary" story contributed only an
   ATC row.
4. The completeness pass is **informational on `NO_CHANGE` runs** (no
   new Jira content → no new rows to add); it actively appends on
   `SUCCESS` runs and logs each append as
   `Updated - <table> row added for field <name> by <S.key> (cross-table completeness).`

This ensures spec pages stay complete: if a story adds a field to a
form, the Form table gets a row even if the story's main contribution
was elsewhere.

#### 5-C.5 First-fire bootstrap & destination self-commit (canonical pattern for new-module routines)

`wiki_destination.json` is the source of truth for which BookStack
page a routine writes to. The dedup contract operates within that
configured page.

There are three scenarios where the destination is incomplete or missing:

**(a) Slug has no entry in `routine_destinations.<slug>`** (configuration miss):
Abort at STEP 2 per §STEP 2 step 4 with
`status=BLOCKED reason='release_scope not configured for routine <slug>'`
and record a manual_action listing the slug, the inferred project key,
and a suggested destination (book + chapter under `SPECS_SHELF_ID = 3`
matching the project module). The operator wires the destination via
`routines/deploy.py --update` (or `routines/scaffold.py`) and re-fires.

**(b) Slug's `page_id` is configured but the page is 404 on BookStack**
(deleted or moved between deploys): fall through to STEP 5C
(create-flow), which builds the canonical scaffold (5 canonical empty
tables + empty UI section) at the configured `book_id` + `chapter_id`
from `wiki_destination.json`, then `POST /api/pages`. After success,
the routine **self-commits** the new `page_id` to `wiki_destination.json`
on `main` (see §5-C.5.2 self-commit rule below).

**(c) Slug's `book_id` is 0 AND/OR `page_id` is 0** (sentinel values —
new-module routine on its first fire ever): run the
**FIRST-FIRE BOOTSTRAP** pattern documented below in §5-C.5.1. This
pattern creates a new book + new page from scratch in shelf 3 and
self-commits the IDs back to the destination map.

##### 5-C.5.1 FIRST-FIRE BOOTSTRAP — canonical algorithm

Runs at the end of STEP 2 (after the resource bootstrap banner,
before STEP 3) when `routine_destinations.<slug>.book_id == 0` OR
`page_id == 0`. The per-routine prompt sets project-specific values
(book name, page name, descriptions); the algorithm below is the
canonical implementation that EVERY first-fire routine MUST follow.

1. **Confirm shelf 3 exists.** `GET $WIKI_BASE_URL/api/shelves/3`. On
   404 abort
   `status=BLOCKED reason='Specification shelf id=3 not found on BookStack'`.
   Otherwise capture the existing `books[]` array — needed in step 4.

2. **Book-name idempotency check.** Iterate the shelf's `books[]`
   array. If any book has `name == <BOOK_NAME>` (case-insensitive),
   USE THAT BOOK — set `NEW_BOOK_ID = book.id`. Skip step 3.

3. **Create the new book** (only if step 2 found none). `POST
   $WIKI_BASE_URL/api/books` with body
   `{"name":"<BOOK_NAME>","description":"<routine-specific description>"}`.
   Capture `NEW_BOOK_ID = response.id`. On non-2xx abort
   `status=FAILED reason='POST /api/books failed during first-fire bootstrap'`
   and log the response body.

4. **Attach the book to shelf 3** (only if step 3 created one — skip
   if step 2 found an existing attached book). `PUT
   $WIKI_BASE_URL/api/shelves/3` with body
   `{"books":[<existing book ids from step 1>, <NEW_BOOK_ID>]}`. On
   failure abort `status=FAILED`.

5. **Page-name idempotency check + create**. Before creating, query
   the book for existing pages and check whether a page with the
   target `<PAGE_NAME>` already exists. This is the safeguard that
   prevents duplicate pages on bootstrap re-fires:

   - `GET $WIKI_BASE_URL/api/books/<NEW_BOOK_ID>` (returns the book
     with its `contents` array of pages and chapters).
   - Iterate the book's pages/contents. If any has
     `name == <PAGE_NAME>` (case-insensitive) AND
     `type == "page"`, USE THAT PAGE — set `NEW_PAGE_ID = page.id`.
     Log `Note - first-fire bootstrap: existing page "<PAGE_NAME>"
     (id <NEW_PAGE_ID>) found in book; reusing instead of creating
     duplicate.` Skip the POST.
   - Otherwise, `POST $WIKI_BASE_URL/api/pages` with body
     `{"book_id":<NEW_BOOK_ID>,"name":"<PAGE_NAME>","html":"<canonical empty scaffold>"}`
     where the scaffold is `<h3>Acceptance Test Cases</h3><table border="1">...</table><h2>User Interfaces (UIs)</h2>`
     per STEP 5C. Capture `NEW_PAGE_ID = response.id`.

6. **Set local `TARGET_PAGE_ID` to `NEW_PAGE_ID`** for the rest of
   this fire. STEP 5 / 6 / 7 run against the newly created (or
   newly-reused) page on the same run.

7. **Self-commit the destination update to `wiki_destination.json` on
   `main`** (see §5-C.5.2 below for the safety rules). Patch the
   routine's own destination entry: set `book_id` to `NEW_BOOK_ID`,
   `page_id` to `NEW_PAGE_ID`, `last_verified` to the current
   ISO8601 UTC timestamp, replace the `_bootstrap` sentinel field
   with a `_history` field that records the creation. Commit message:
   `chore(wiki_destination): <slug> first-fire bootstrap — book_id 0→<id>, page_id 0→<id>`.
   On commit failure: log a manual_action telling the operator to
   commit the change manually, but do NOT abort the fire (the
   BookStack writes have already succeeded; the run continues).

8. **Log bootstrap completion** in the run log:
   `Note - first-fire bootstrap completed: book "<BOOK_NAME>" (id <NEW_BOOK_ID>)
   and page "<PAGE_NAME>" (id <NEW_PAGE_ID>) in shelf 3. Destination
   self-commit: <SHA> (or "failed — see manual_actions"). Standard
   STEP 3+ workflow now runs against the new page.`

After this, proceed with STEP 3 (release confirmation) and the rest
of the workflow normally. **Once `wiki_destination.json` is updated**
(by step 7), the bootstrap gate is SKIPPED on every subsequent fire
(`book_id != 0` AND `page_id != 0`), and the routine runs the
standard workflow.

##### 5-C.5.2 Self-commit rule (constrained mutation of `wiki_destination.json`)

The routine MAY mutate `wiki_destination.json` on `main` ONLY in the
two scenarios above (FIRST-FIRE BOOTSTRAP step 7, and STEP 5C
create-flow after the page-recreation case). Outside these scenarios
the routine MUST treat `wiki_destination.json` as read-only.

**Constraints for the self-commit:**

- **Single-entry scope:** the routine may modify ONLY
  `routine_destinations.<own_slug>` — never any other routine's entry,
  never `specification_shelf`, `specification_books`, `wiki`, or any
  other top-level key. Diffs that touch outside this scope MUST be
  refused before the PUT.
- **Allowed field changes:** `page_id` (from 0 or stale to new),
  `book_id` (from 0 to new), `chapter_id` (from null to new if a new
  chapter was created in STEP 5C), `last_verified` (timestamp),
  `_history` (append-only — record the creation event), removal of
  `_bootstrap` field (once sentinel is resolved). Any other field
  change is refused.
- **Target branch:** the commit MUST target `main` directly via the
  GitHub Contents API's `branch` parameter — not the per-fire feature
  branch (logs go to feature branches; destination map goes to main
  so the NEXT fire reads the updated values from the resources/
  it clones at fire time).
- **Pre-flight check:** before the PUT, `GET /repos/.../contents/resources/wiki_destination.json?ref=main`
  to capture the current SHA. Use that SHA in the PUT to detect
  concurrent edits (Contents API returns 409 if SHA mismatch). On
  409, re-fetch, re-apply the constrained change, retry once. After
  one retry: log a manual_action and continue.
- **Author and commit-message format:** the commit uses the routine's
  `GITHUB_TOKEN` (so the author appears as the token's owner) and the
  message starts with `chore(wiki_destination):` for grep-ability.
- **Audit trail:** every self-commit appends a `_history` entry to
  the routine's destination block. Multiple self-commits accumulate;
  the field is append-only string concatenation, never overwritten.

This is the ONLY case where the routine writes to `resources/`. All
other resource-file changes are operator-driven through normal git
commits / PR review.

### 5-D. UI merge — extract → upload → compare → replace/add

**Authoritative: `release-filter-policy.md §11.1`.**

1. **Extract** UI assets from each story `S`:
   - Attachments with image MIME or image extension.
   - Embedded image URLs in description / confirmed-final comments.
   - Design-tool URLs (Figma / Sketch / etc.) → **IGNORED** per
     `release-filter-policy.md` §11.0 (never extracted, linked, or
     rendered — globally out of wiki scope for all projects).

2. **Re-host every Jira image binary on BookStack** (MANDATORY — never
   link Atlassian URLs directly in `<img>` / `<a>` tags):

   **Pipeline: curl → write to /tmp/ → multipart POST → delete temp.
   At no point is the image binary read into the routine session's
   Claude API context.** Authoritative reference for the full
   algorithm: `release-filter-policy.md` §11.1 (downloads + uploads +
   failure modes).

   For each Jira attachment (mime `image/*`) and each embedded
   description image:

   - **Download to disk via curl** (Atlassian sites are in the env
     outbound allowlist as of 2026-05-18 — direct HTTP works):
     ```bash
     LOCAL_PATH="/tmp/${FILENAME}"
     HTTP_CODE=$(curl -sS -o "$LOCAL_PATH" -w "%{http_code}" \
                      -H "Authorization: Bearer $JIRA_API_TOKEN" \
                      -H "Accept: */*" \
                      "$ATTACHMENT_CONTENT_URL")
     # On non-200: log "UI download failed - <filename> for <S.key>: HTTP <code>"
     # and SKIP this asset (no Atlassian URL fallback).
     ```
     **NEVER use the `Read` tool on `$LOCAL_PATH`.** The Read tool
     loads images into the session's multimodal context; if the API
     can't process the binary (corrupt, partial, unusual encoding,
     oversized), it returns
     `"API Error: an image in the conversation could not be processed
     and was removed"` and silently drops the image from context,
     which can derail the rest of the run. The bytes are **opaque**:
     download → upload → delete, never inspect.

   - **Upload to BookStack image-gallery** (curl streams from disk —
     no in-context bytes):
     ```bash
     curl -sS -X POST "$WIKI_BASE_URL/api/image-gallery" \
       -H "$AUTH" \
       -F "type=gallery" \
       -F "uploaded_to=$TARGET_PAGE_ID" \
       -F "image=@$LOCAL_PATH;type=$MIME;filename=$FILENAME"
     ```
     Response is JSON: `{ id, name, url, thumbs:{ gallery, display } }`.
     Capture `(filename, response.url, response.thumbs.display)` —
     these are short strings, safe for context.

   - **Delete the temp file** after the upload (success or failure):
     `rm -f "$LOCAL_PATH"`. Keeps temp space clean and prevents any
     later diagnostic step from accidentally Read'ing the binary.

   - If the upload returns a non-2xx code, **skip this UI for this
     run** and log `UI upload failed - <filename> for <S.key>: <error>`.
     Do NOT fall back to writing the Atlassian URL — that produces
     broken images for readers (HTTP 403 from Jira to unauthenticated
     wiki readers).

   - Re-upload is one-shot per attachment. Subsequent runs see the
     BookStack URL in the existing `UI_SECTION` and the filename-match
     check below makes them no-op.

3. **Parse `UI_SECTION`** (if it exists) into a map
   `WIKI_UIS = { lowercase_filename → (h6_text, href_url, img_src) }`.
   If a prior run left a `Design References` sub-block or any design-tool
   link, mark it for **removal** per §11.0 (§10.4 op-4) — it is no longer
   permitted.

4. **For each Jira UI asset** (filename `fn`, BookStack url
   `bs_url` from step 2, BookStack thumb `bs_thumb`, screen name
   `screen`):
   - **`fn` not in `WIKI_UIS`** → ADD a new `<h6>{screen}</h6>` +
     `<a href="{bs_url}"><img src="{bs_thumb}" alt="{screen}"></a>` at
     the end of `UI_SECTION`. Log `UI added - {fn} for {S.key}` and
     include the BookStack URL in the log (not the Atlassian one).
   - **`fn` in `WIKI_UIS`, both URLs identical to BookStack values** →
     NO-OP. Log `No change - UI {fn} already present.`
   - **`fn` in `WIKI_UIS` but the wiki entry uses an Atlassian URL OR
     a stale BookStack URL** → REPLACE the `<a href>` and `<img src>`
     with the fresh BookStack values. This is what fixes the broken
     images written by the 2026-05-16 run. Log
     `UI replaced - {fn} URL updated for {S.key}.`

5. **Wiki entries not referenced by any Jira story this run** → KEEP
   verbatim. No log line. (Existing canonical Salary screenshots from
   2024-11 stay in place.)

6. **If `UI_SECTION` doesn't exist yet** and at least one UI is being
   added, create the section at the end of the page body:
   ```html
   <h2>User Interfaces (UIs)</h2>
   ```
   followed by the new `<h6>` + `<a><img>` entries.

7. **Design-tool URLs are EXCLUDED (§11.0).** Never author a
   `<h6>Design References</h6>` sub-block or any Figma / Sketch link. If a
   prior run wrote one, remove it (step 3) and log `Removed - design-tool
   reference(s) — out of global spec scope per §11.0`.

8. **No per-story UI heading is ever emitted.** All UIs live in the
   one global UI section at the end of the page.

### 5-E. Assemble `NEW_HTML`

`NEW_HTML` is built by:
- Replacing each canonical table's HTML block in `PRIOR_HTML` with
  its updated form (with new / updated rows appended at the bottom).
- Replacing `UI_SECTION` with its merged form.
- Preserving everything else verbatim — every other `<h2>`, `<h3>`,
  `<h4>`, paragraph, list, image, table outside the canonical 5.

If `NEW_HTML == PRIOR_HTML` (byte-equal after whitespace
normalization) → `status=NO_CHANGE`, log `No Change - Specification
already up to date.` Proceed straight to STEP 8.

---

## STEP 5C — Canonical page builder (create-flow)

Used only when the destination page in `wiki_destination.json` doesn't
yet exist (`GET /api/pages/<TARGET_PAGE_ID>` returns 404). Rare under
the release-filter policy because destinations are pre-configured.

If invoked, build a minimal scaffold containing the 5 canonical
tables (each with header row only) followed by the empty UI section:

```html
<h3>Acceptance Test Cases</h3>
<table border="1">
  <colgroup><col style="width:15%"><col style="width:42%"><col style="width:43%"></colgroup>
  <tbody>
    <tr><td><strong>#</strong></td><td><strong>Feature</strong></td><td><strong>Scenario</strong></td></tr>
  </tbody>
</table>

<!-- List / Search / Form / Audit Trail tables emitted only if any
     row is being added for them in this run; otherwise omit them. -->

<h2>User Interfaces (UIs)</h2>
```

Then `POST /api/pages` with `book_id` + `chapter_id` from
`wiki_destination.json`. The routine never mutates
`wiki_destination.json` mid-run — record any new page_id as a
`manual_action` for an operator commit.

---

## STEP 6 — Validation (STRICT CANONICAL)

Run **all** of the following checks against `NEW_HTML`. Any FAIL blocks
the write.

| # | Check | FAIL condition |
|---|---|---|
| 1 | **Canonical table shapes** | Every authored table matches exactly one of: ATC (3 cols: `#  Feature  Scenario`), List (3 cols), Search (5 cols), Form (6 cols), Audit Trail (3 cols). FAIL if a new table outside this list was authored, or if column count is wrong (e.g. an extra `Release` / `Status` / `Notes` column). |
| 2 | **ATC header order** | ATC table header row is exactly `# \| Feature \| Scenario` (in that order). No 4th header cell. |
| 3 | **Jira key idempotency suffix** | Every ATC row authored or updated this run has its Feature cell ending in a parenthetical key list: ` (<KEY>)` for a single contributor or ` (<KEY>, <KEY2>, ...)` for multiple. Each `<KEY>` matches `[A-Z]+-\d+`. Whitespace around commas is normalized to `, `. |
| 4 | **ATC key uniqueness** | No Jira key appears in more than one ATC row's key list. (A single row may carry multiple keys; the same key MUST NOT appear in two different rows — that is the symptom of a missed dedup match.) |
| 5 | **Non-ATC tables link to ATC** | Every authored non-ATC row's leftmost cell ends with `(ATC #<n>)` referencing an existing ATC row. The Jira-key list (if present) follows the `(ATC #<n>)` suffix in a second parenthetical group. |
| 2-HDR | **Canonical section heading present above each authored table** | Every canonical table in `NEW_HTML` is immediately preceded by its canonical section heading per `WIKI_PAGE_RENDER.md` §1.1: `<h3>Acceptance Test Cases</h3>` before ATC, `<h3>List</h3>` before List, `<h3>Search</h3>` before Search, `<h3>Form</h3>` before Form, `<h3>Audit Trail</h3>` before Audit Trail, and `<h2>User Interfaces (UIs)</h2>` before the UI gallery. FAIL if a table is present but its heading is missing, its heading text differs (e.g. `<h3>ATC</h3>` / `<h3>Acceptance Tests</h3>` / `<h3>Acceptance Test Cases (HT-965)</h3>` — appending a key list is forbidden, the heading is generic), the heading level is wrong (`<h2>Form</h2>`, `<h4>Form</h4>`), or there is intervening content (a `<p>` / image / divider) between the heading and its `<table>`. Applies to **every routine in this repo** (CM, PNP, Roster, Orange Sign, the dynamic CS routine, and any future routine inheriting STEP 6). |
| 6 | **No invented headings authored** | The routine authored ZERO new `<h2>` / `<h3>` / `<h4>` / `<h5>` outside the single `<h2>User Interfaces (UIs)</h2>`, the five canonical `<h3>` table-section headings from check #2-HDR, and `<h6>` entries inside the UI section. Forbidden authored headings include but are not limited to: `Overview`, `Business Requirement`, `Expected System Behavior`, `Rules / Validations`, `User Stories`, `Acceptance Criteria` (as a heading — the table is the AC), `Interfaces (UIs)` as `<h3>`/`<h4>`, `Notes / Dependencies / Limitations`, `<h2>{fixVersion}</h2>`, `Pilot`, `Pilot Releases`, `Issues Affecting Scope`, `Migration Notes`, `Change Log`, `Implementation Notes`, internal project names. |
| 7 | **UI section position and shape (gallery-only — `release-filter-policy.md` §11.1-bis)** | If a UI section is authored, it is `<h2>User Interfaces (UIs)</h2>` (case-insensitive), positioned LAST in the page body. Its content is **strictly** `<h6>{Topic Name}</h6>` immediately followed by `<a href><img></a>` — one h6+image pair per UI screen, in that order. **FAIL conditions:** (a) ANY `<p>` / `<ul>` / `<ol>` / `<li>` / `<table>` inside the UI section — including any `Design References` / Figma / Sketch sub-block, which is globally forbidden per `release-filter-policy.md` §11.0 (a surviving design-tool link is itself a FAIL and must be removed). (b) Any `<h6>` not immediately followed by `<a><img></a>`. (c) Any `<a><img></a>` without a preceding `<h6>` topic name (orphan image). (d) Topic name reads as a sentence/description — contains period+space, exceeds 6 words, or starts with `The `/`This `/`When `/`A `. (e) Heading level inside the UI section is anything other than `<h6>` (no `<h4>`/`<h5>`/`<h3>` captions, no inline `<strong>UI:</strong>` labels). Topic name MUST be a short noun-phrase label (`Salary History`, `Pay Grade Configuration`), taken from Jira per the §11.1-ter source priority. |
| 8 | **Form table sanity — strict 6-cell row alignment** | Every Form-table data row has **exactly 6 `<td>` cells** in the canonical column order: (1) Field Name, (2) Type, (3) Default Value, (4) Validation(s), (5) Validation Message(s), (6) Field Behavior. FAIL conditions: (a) a row has fewer or more than 6 `<td>` cells (a 5-cell row visually collapses one header and slides every cell after it into the wrong column — the symptom the spec author reported on 2026-05-18 where `Field Behavior` content appeared under the `Validation Message(s)` header); (b) any cell renders as truly empty `<td></td>` — empty cells MUST contain `—` (em-dash, U+2014) so the column structure visibly persists across rows regardless of content; (c) `<img>` inside any `<td>`; (d) any `Save` / `Cancel` row (per `specification-writing-guideline.md` §2.4 Form note); (e) `<ul>` / `<ol>` / `<li>` inside the Validation(s) or Validation Message(s) cells — multi-validation lines use `-` (hyphen + space) prefix per the §2.4 Form note; (f) content positionally misaligned to its header (e.g. a validation rule sitting in the Field Behavior cell, or vice versa). |
| 9 | **Structural preservation + evidence-gated CRUD (`release-filter-policy.md` §10.4)** | Every `<h2>`, `<h3>`, `<h4>`, `<h5>`, `<h6>` text present in `PRIOR_HTML` is still present in `NEW_HTML`, and no whole canonical table or the UI section was deleted (the structural floor). **Row / bullet / cell content MAY be removed or replaced** relative to `PRIOR_HTML` — but ONLY via an evidence-gated §10.4 op-4 supersession that the run log records with a `Removed - …` / `Updated - … <old> → <new>` line citing the driving `<KEY>`. FAIL if a heading, whole table, or the UI section disappeared, OR if any row/bullet/cell content was removed/replaced without a matching evidence-gated log line (silent shrink — absence is never removal). |
| 9-ORPH | **No orphaned ATC back-references after removal** | After any §10.4 row-level removal, every `(ATC #<n>)` back-reference in every non-ATC row still points at an existing ATC `#` in `NEW_HTML`, and ATC `#`s are contiguous from 1. FAIL if a removed ATC row left a dangling `(ATC #<n>)` or a numbering gap. |
| 10 | **No change markers** | No `style="background-color:..."` / `[New — KEY]` / `[Updated — KEY]` / yellow tints / diff-class spans in authored content. |
| 11 | **Idempotency** | Running STEP 5 a second time against `NEW_HTML` produces byte-identical output. |
| 12 | **Semantic ATC uniqueness (§5-C.1)** | No two ATC rows share a normalized Feature/Topic name. Normalization: lowercase, strip the parenthetical key list, collapse internal whitespace, fold synonyms per §5-C.1. FAIL surfaces as `validation failed: duplicate ATC row for feature '<normalized name>' (#<a> vs #<b>)` — the routine must merge them into one row (combined key list, merged Scenario per §5-C.2) before retrying. |
| 13 | **Semantic non-ATC uniqueness** | Same check as #12 applied per-table to List (`Column Name`), Search (`Field Name`), Form (`Field Name`), and Audit Trail (`Action`). Within each table, no two rows share a normalized leftmost-cell name after synonym folding. |
| 14 | **Scenario cell bullet format (§5-C.2 + guideline §2.2) — applies to ALL free-text cells across ALL canonical tables** | The bullet-form rule is enforced **identically** for: ATC `Scenario`, List `Description`, Search `Field Behavior`, Form `Field Behavior`, Audit Trail `How it is tracked in Audit Trail`. Every such cell is a `<ul>` containing one or more `<li>` items (one bullet per distinct test case / behaviour point). FAIL conditions: (a) cell contains raw text or `<p>` outside a `<ul><li>` (paragraph-form — including a single-sentence cell that should still be `<ul><li>...</li></ul>` for vertical-shape consistency with bulleted rows in the same column); (b) cell contains multiple distinct behaviour points inside a single `<li>` separated by `. ` / `;` (run-on bullet); (c) cell contains `<img>` or `<table>`; (d) cell is empty (`<ul></ul>`); (e) the cell is positionally a free-text cell of one of the five canonical tables above but uses any other shape than `<ul><li>`. The Form `Validation(s)` and `Validation Message(s)` columns are the **only** canonical exception — they use `-`-prefixed plain-text lines separated by `<br>` per `specification-writing-guideline.md` §2.4 Form note. The exception applies to those two specific columns only; the Form `Field Behavior` column follows the bullet rule like everything else. |
| NAV-1 | **Nav-tree sync ran** | The audit log contains a `## STEP 2.6 — Nav-Tree Sync` section AND `specification_nav_tree.last_synced_at` was updated to a timestamp ≥ run start. FAIL if missing (per `release-filter-policy.md` §16.6). |
| NAV-2 | **Nav-tree consistency for configured destination** | `routine_destinations.<slug>.page_id` (where non-zero) corresponds to an `id` in `specification_nav_tree` (either as a chapter page or an orphan_page) with `deprecated_at == null`. FAIL surfaces as a manual_action: `Manual action: configured TARGET_PAGE_ID=<n> is not present in specification_nav_tree (deprecated_at=<ts>). Wiki admin may have moved or deleted the page — refresh routine_destinations.<slug>.page_id.` The run still attempts the configured page (the deprecation may be transient); if BookStack returns 404 the existing STEP 5C create-flow handles the missing page. |
| CHANGELOG-1 | **Per-run Excel changelog updated** (`release-filter-policy.md §17`) | The audit log contains a `## STEP 9 — Changelog` section with a `CHANGELOG-OK` or `CHANGELOG-SKIP` line; on a real run that changed content, `logs/changelog/wiki_sync_changelog.xlsx` is in the STEP 9 commit. `CHANGELOG-SKIP` is a soft pass (run not failed) but surfaces as a `manual_action`. |

If any check FAILs, set `status=FAILED reason='validation failed: check
<#> — <message>'`, skip STEP 7, proceed to STEP 8 / 9 / 10. The most
common cause of failure is the routine slipping into the invented
prose schema — re-read `specification-writing-guideline.md` §2.4
before retrying.

---

## STEP 7 — Diff-aware write

**Dry-run check (first action of STEP 7):** if `DRY_RUN_MODE=1` (set
in STEP 1.1 from the `DRY_RUN` env var), skip the write entirely.
Record `Note - DRY_RUN=true; skipped BookStack PUT for page <id>; NEW_HTML
preserved in memory for log artefact only.` `status` stays at the
natural outcome — `SUCCESS` if `NEW_HTML != PRIOR_HTML`, `NO_CHANGE`
otherwise — because dry-run is conveyed by the YAML `dry_run: true`
flag (STEP 9), the email banner (§9-G), and the AUDIT SUMMARY
`Dry-run:` line (STEP 8), NOT by adding new status enum values.
Continue to STEP 8 / 9 / 10 — the AUDIT SUMMARY, log file, and email
all reflect the dry-run outcome. **DO NOT** touch BookStack at STEP 7
in dry-run mode under any circumstance.

For real runs (DRY_RUN_MODE=0):

`PUT /api/pages/<TARGET_PAGE_ID>` with body:
```json
{
  "name": "<page_name from wiki_destination.json>",
  "html": "<NEW_HTML>"
}
```

Pre-flight: re-GET the page; refuse if `updated_at != PRIOR_REV`
(concurrent edit). On 409 / 412 retry once after re-reading. For
transient 5xx / network errors, follow the HTTP retry policy in the
Safety rails section below.

One write per run. No POST under STEP 7 (POST belongs only to STEP 5C
create-flow).

---

## STEP 8 — AUDIT SUMMARY block

Print this block as the routine's structured output (in addition to
narrative text). Format:

```
==================== AUDIT SUMMARY ====================
Routine            : <routine name>
Run UTC            : <ISO8601 UTC fire time>
Run local          : <Asia/Colombo localized>
Mode               : repo-aware (git <short hash>)
Credentials        : from-env (lengths only — no values)
Jira project       : <JIRA_PROJECT_KEY>
fixVersion         : <RELEASE_SCOPE>
fixVersion.released: <true|false>
fixVersion.releaseDate: <YYYY-MM-DD or empty>
Release gate       : <CONFIRMED|NOT_YET|BLOCKED — verbatim policy log line>
Target page        : <TARGET_PAGE_ID> (<page_name>) in book <book_id>:<book_name>
Stories checked    : <N>
Stories updated    : <U>
Stories no-change  : <NC>
Stories skipped    : <S>
Stories blocked    : <B>
Manual actions     : <0 or comma-separated Jira keys>
Status             : <SUCCESS|NO_CHANGE|SKIPPED|BLOCKED|FAILED>
Email send         : <SENT|PARTIAL|FAILED|SKIPPED  N_OK/N_TOTAL>
GitHub log         : <log_html_url or empty>
========================================================
```

`Manual actions` is the list of Jira keys whose log status is `Blocked` —
the Release Manager / PL needs to act on these.

---

## STEP 9 — GitHub audit log (email-ready hybrid)

Skip silently if `GITHUB_TOKEN` is unset.

Commit one file per run to
`logs/<routine_slug>/<UTC_TIMESTAMP>.md` via the GitHub Contents API.

**STEP 9 also updates the shared changelog (mandatory — `release-filter-policy.md §17`).**
The changelog is canonical on **`main`** (CSV ledger `logs/changelog/changelog.csv`
+ rendered `wiki_sync_changelog.xlsx`). Pull the current `main` `changelog.csv`,
build the payload JSON (schema atop `routines/update_changelog.py`) from this
run's per-issue / per-destination CRUD, run
`python routines/update_changelog.py <payload.json>`, then commit **BOTH files
to `main`** via the GitHub Contents API (`branch=main`, current sha + retry on
conflict — §17.0), **even if this run's `.md` log commits to a different
branch**. Record the helper's `CHANGELOG-OK` / `CHANGELOG-SKIP` line under a
`## STEP 9 — Changelog` section. A NO_CHANGE / SKIPPED / BLOCKED run still
writes one summary row. Validated by STEP 6 check `CHANGELOG-1`.

**Canonical timestamp format (pinned):** `<UTC_TIMESTAMP>` MUST be
`YYYY-MM-DDTHHMMSSZ` — hyphenated date, literal `T` separator,
six-digit time WITHOUT colons, trailing `Z`. Examples:
- ✓ `logs/cm_daily_sync/2026-05-18T013000Z.md`
- ✓ `logs/pnp_daily_sync/2026-05-18T003000Z.md`
- ✗ `logs/cm_daily_sync/2026-05-18T01:30:00Z.md` (colons not allowed)
- ✗ `logs/cm_daily_sync/20260518T013000Z.md` (date needs hyphens)
- ✗ `logs/cm_daily_sync/2026-05-18T01-30-00Z.md` (time must be flat HHMMSS)

The format mirrors the YAML `run_utc` value with the `:` separators
stripped from the time and the trailing `Z` preserved. Routines that
write filenames in any other shape silently produce out-of-order
listings on GitHub and break `glob`-based log tooling — STEP 9
self-validates the filename it is about to commit and aborts the
commit (logging `Failed - log filename format violation: <name>`) if
it does not match `^\d{4}-\d{2}-\d{2}T\d{6}Z\.md$`.

The log file body is:

```yaml
---
routine: <routine_slug>
project_key: <JIRA_PROJECT_KEY>
fix_version: <RELEASE_SCOPE>
fix_version_released: <true|false>
fix_version_release_date: <YYYY-MM-DD or empty>
release_gate: <CONFIRMED|NOT_YET|BLOCKED>
release_gate_log: <verbatim policy log line>
run_utc: <ISO8601>
status: <SUCCESS|NO_CHANGE|SKIPPED|BLOCKED|FAILED>
dry_run: <true|false>            # true when DRY_RUN env var was truthy at STEP 1
target_page_id: <id>
target_page_name: <name>

# Discovery counts (every issue returned by the fixVersion query,
# classified by §8 issue-type filter — drives the email status bar).
total_issues_found: <N>
epics_found: <N>
epics_processed: <N>
stories_found: <N>
stories_processed: <N>
tasks_found: <N>
tasks_processed: <N>
bugs_found: <N>            # reported in summary cards only, not in story-level results table
subtasks_found: <N>        # reported, not processed
other_found: <N>           # Improvements / Refactors / Spikes / other

# Per-Epic project scan (STEP 3-D / release-filter-policy §15) —
# informational. Independent of the fixVersion-scoped story query.
epics_scanned: <N>
epics_released: <N>
epics_pending: <N>
epics_unassigned: <N>
epics_excluded: <N>
epic_scan_summary:
  - key: <KEY>
    name: <Jira summary>
    fix_versions: <"8.0, 8.0.2" or "—">
    status: <Released|Pending|Unassigned|Excluded>
    symbol: <"✓"|"⚠"|"—"|"✗">

# Outcome counts (per processed issue — Epic/Story/Task only).
stories_updated: <U>
stories_no_change: <NC>
stories_skipped: <S>
stories_blocked: <B>

manual_actions: [<jira-keys>]
email_subject: "OHRM Wiki Sync — <routine_slug> — <STATUS> — <YYYY-MM-DD>"
email_send_status: PENDING       # updated by STEP 10 to SENT|PARTIAL|FAILED|SKIPPED
log_html_url: ""                 # filled in by STEP 9 itself
---

# OHRM Wiki Sync log — <routine_slug>

- **Run UTC**: <ISO8601>
- **Project / fixVersion**: <KEY> / <V>  (<release_gate>)
- **Target**: <page_id> <page_name>
- **Discovery**: <total> issues found — Epics <e_f>, Stories <s_f>, Tasks <t_f>, Bugs <b_f>, Other <o_f>
- **Coverage**: processed <epics_p+stories_p+tasks_p> / excluded by type <b_f+sub_f+other_f>
- **Outcomes**: updated <U> / no-change <NC> / skipped <S> / blocked <B>
- **Status**: <STATUS>

## Per-issue results
| Jira key | Type | Status | Sub-sections touched | Notes |
|---|---|---|---|---|
| <KEY> | Epic | Updated | Overview, Acceptance Criteria, Interfaces (UIs) | |
| <KEY> | Story | Updated | Overview, Expected System Behavior, Interfaces (UIs) | |
| <KEY> | Task | Updated | Overview, Acceptance Criteria, Interfaces (UIs) | |
| <KEY> | Bug | Excluded | — | Excluded - <KEY> is a Bug; issue type not in spec coverage scope. |
| <KEY> | Sub-task | Excluded | — | Excluded - <KEY> is a Sub-task; issue type not in spec coverage scope. |
| <KEY> | Story | Skipped | — | Skipped - Story is excluded from release scope. |
| <KEY> | Story | Blocked | — | Blocked - Jira description is empty. |

(Every issue returned by the STEP 3-C JQL appears here. Excluded /
Skipped / Blocked rows are required for transparency.)

<!-- EMAIL_BODY_START -->
{rendered email body — see §9-A through §9-E below}
<!-- EMAIL_BODY_END -->
```

### 9-A. Email template file (the master)

The routine does NOT inline an HTML template here. The template lives
in **`_core/resources/email_template.html`** (the copy cloned into
`_core/` at STEP 2; in the legacy single-repo layout it was
`resources/email_template.html`) — a single reusable HTML file with
documented placeholders. STEP 9 reads **that exact file**, substitutes
placeholders per §9-B / §9-C / §9-D / §9-E, and writes the substituted
result between the `<!-- EMAIL_BODY_START -->` / `<!-- EMAIL_BODY_END -->`
markers in the log file.

**MANDATORY — never improvise the email body.** The emitted EMAIL_BODY
MUST be the *complete* `email_template.html` after substitution: it MUST
begin with the template's `<html>` / `<body>` root and retain EVERY
section and table the template defines (header, status-summary table,
Stories / List / Search / Form / Audit tables as applicable, Epic
Release Status, Spec Files, Manual Actions, footer). You MUST NOT
hand-author, summarize, shorten, or restructure the body, and MUST NOT
emit a body made of loose `<h2>` / `<h3>` / `<ul>` fragments in place of
the template. If `_core/resources/email_template.html` cannot be read,
do NOT invent a body — set `email_send_status: FAILED
reason='email_template.html unreadable'` and skip the send.

This makes the template:
- **Project-agnostic** — same template renders for CM, PNP, and any
  future routine.
- **Editable without touching SKILL.md** — design changes go to
  `resources/email_template.html` only.
- **Auditable** — the rendered HTML in each log file is a snapshot of
  the substitution.

### 9-B. Placeholder contract — values

The following placeholders are substituted with the run's values:

| Placeholder | Source |
|---|---|
| `{{routineName}}` | Human name of the routine (e.g. `CM Daily Spec Sync`). Default: title-case `routine_slug` if no human name configured. |
| `{{routineSlug}}` | The slug key (e.g. `cm_daily_sync`). |
| `{{projectKey}}` | `JIRA_PROJECT_KEY` from `wiki_destination.json`. |
| `{{projectName}}` | Human name from the slim prompt (`PROJECT_NAME`, e.g. `Compensation Management`). |
| `{{fixVersion}}` | `RELEASE_SCOPE` verbatim (e.g. `8.0`). |
| `{{runDateTime}}` | `YYYY-MM-DD HH:MM (Asia/Colombo)` — derived from UTC fire time. |
| `{{overallStatus}}` | The run status, mapped to human label: `SUCCESS` → `Completed` / `NO_CHANGE` → `Completed (No Changes)` / `BLOCKED` → `Blocked` / `FAILED` → `Failed` / `SKIPPED` → `Skipped`. Use `Completed with Warnings` when status is `SUCCESS` AND `manual_actions` is non-empty. |
| `{{statusBadgeBg}}`, `{{statusBadgeFg}}`, `{{statusBarColor}}` | Status colors per the palette in §9-F. |
| `{{totalStoriesChecked}}` | `total_issues_found` from the YAML. |
| `{{updatedCount}}` | `stories_updated`. |
| `{{noChangeCount}}` | `stories_no_change`. |
| `{{skippedCount}}` | `stories_skipped`. |
| `{{blockedCount}}` | `stories_blocked`. |
| `{{bugsReportedCount}}` | `bugs_found` from the YAML (count only — bugs are NEVER rendered in the story-level results table). |
| `{{githubFilesUpdatedCount}}` | Count of distinct BookStack pages this run wrote to (typically 1, equal to `TARGET_PAGE_ID`). 0 on `NO_CHANGE` / `SKIPPED` / `BLOCKED` runs. |
| `{{manualActionsRequiredCount}}` | `len(manual_actions)`. |
| `{{epicsScannedCount}}` | `epics_scanned` from the per-Epic scan (STEP 3-D). |
| `{{epicsReleasedCount}}` | `epics_released`. |
| `{{epicsPendingCount}}` | `epics_pending`. |
| `{{epicsUnassignedCount}}` | `epics_unassigned`. |
| `{{epicsExcludedCount}}` | `epics_excluded`. |
| `{{finalStatusMessage}}` | One of the 4 variants in §9-G, selected by `status` + `manualActionsRequiredCount`. |
| `{{wikiPageName}}` | The BookStack page name from `routine_destinations.<slug>.page_name` (or from the BookStack GET response on `TARGET_PAGE_ID`; both equal). Same value as YAML `target_page_name`. Always filled — every run reaches at least STEP 2 where this is captured. |
| `{{wikiPageUrl}}` | The canonical BookStack URL of `TARGET_PAGE_ID`. Source: the `url` field returned by `GET /api/pages/<TARGET_PAGE_ID>`. **The routine MUST GET the page early enough that this placeholder is filled on every outcome** — SUCCESS, NO_CHANGE, SKIPPED, BLOCKED, FAILED. On CONFIRMED runs this happens at STEP 5-A already; on SKIPPED / BLOCKED outcomes (where STEP 5 is skipped) the routine performs a one-shot GET in STEP 2 immediately after looking up the destination, purely to capture `name` + `url` for the email. If even that GET fails (page truly 404 or BookStack unreachable), fall back to `<WIKI_BASE_URL>/pages/<TARGET_PAGE_ID>` so the placeholder is never left empty. |
| `{{gitSha}}` | Short git hash captured at STEP 2. |
| `{{logHtmlUrl}}` | The same value as YAML `log_html_url`. |

### 9-C. Placeholder contract — repeating row blocks

Four placeholders hold ROWS that are repeated per entry. The routine
renders each row from a template and concatenates.

#### `{{storyRows}}` — one `<tr>` per processable Jira issue

**Render exclusion rule:** Only issues whose `issuetype.name` is
`Story` or `Task` are rendered here. The following types are NEVER
rendered as story rows (their counts surface elsewhere in the email):

| Excluded type | Where it surfaces instead |
|---|---|
| `Epic` | Epic Release Status section (§9-D conditional block) — every Epic appears there with its release status |
| `Bug` | `{{bugsReportedCount}}` summary card only — bugs are out of scope for spec coverage and clutter the change list |
| `Sub-task` | not rendered anywhere (folds into parent story); counted in `subtasks_found` for the log only |
| `Improvement` / `Refactor` / `Spike` / other | not rendered; counted in `other_found` for the log only |

This keeps the change list focused on what the spec author / Release
Manager needs to action — stories and tasks. Bug noise is reduced to
a single count card.

Row template:

```html
        <tr style="background:{{rowBg}};">
          <td style="padding:11px 10px;font-size:13px;color:#1f2937;font-weight:600;border-bottom:1px solid #e2e8f0;vertical-align:top;">{{jiraKey}}</td>
          <td style="padding:11px 10px;font-size:13px;color:#1f2937;border-bottom:1px solid #e2e8f0;vertical-align:top;line-height:1.4;">{{storyName}}</td>
          <td style="padding:11px 10px;border-bottom:1px solid #e2e8f0;vertical-align:top;"><span style="display:inline-block;padding:3px 10px;border-radius:11px;background:{{badgeBg}};color:{{badgeFg}};font-size:11px;font-weight:700;letter-spacing:.3px;">{{statusLabel}}</span></td>
          <td style="padding:11px 10px;font-size:12px;color:#475569;border-bottom:1px solid #e2e8f0;vertical-align:top;line-height:1.5;">{{reason}}</td>
          <td style="padding:11px 10px;font-size:12px;color:#475569;border-bottom:1px solid #e2e8f0;vertical-align:top;font-family:Consolas,monospace;">{{specFile}}</td>
          <td style="padding:11px 10px;font-size:12px;color:#475569;border-bottom:1px solid #e2e8f0;vertical-align:top;line-height:1.5;">{{updatedSections}}</td>
          <td style="padding:11px 10px;font-size:12px;color:#475569;border-bottom:1px solid #e2e8f0;vertical-align:top;line-height:1.5;">{{requiredAction}}</td>
        </tr>
```

Per-cell semantics:
- `{{jiraKey}}` — `CM-31`, `PNP-37`, etc.
- `{{storyName}}` — Jira `summary` verbatim (no truncation).
- `{{statusLabel}}` — `Updated` / `No Change` / `Skipped` / `Blocked`
  / `Excluded`. (`Excluded` is for bugs/sub-tasks/etc. removed by §8.)
- `{{badgeBg}}`, `{{badgeFg}}` — per §9-F palette.
- `{{rowBg}}` — alternate `#ffffff` and `#f8fafc` for zebra striping.
- `{{reason}}` — the verbatim per-issue log line from STEP 4 / STEP 5
  describing what happened to this issue (e.g.
  `Excluded - CM-17 is a Bug; issue type not in spec coverage scope.`,
  `Updated - ATC row #13 added; Form row added for 'Pay Grade'.`,
  `No change - CM-2 already up to date.`, or
  `Blocked - Jira description is empty. Add a textual description of the released behavior to the Jira ticket.`).
  The line describes **what the routine did to the canonical tables**,
  not what it ignored or did not read.
- `{{specFile}}` — for processed rows, the BookStack page identifier
  (e.g. `Salary (page 360)`). For excluded / skipped / blocked rows
  with no write: `N/A`.
- `{{updatedSections}}` — comma-separated list of canonical
  sub-elements actually written (e.g. `ATC row #14; Form rows (Base Pay)`).
  For non-writes: `N/A`.
- `{{requiredAction}}` — one of: `No action required.`,
  `Release Manager must mark fixVersion as released.`,
  `PL must update Jira description.`,
  `PL must attach UI screenshots.`,
  or a custom action sentence derived from the per-issue log.

#### `{{manualActionRows}}` — one `<tr>` per item needing manual action

Row template:

```html
        <tr><td style="padding:14px 18px;border-bottom:1px solid #fecaca;">
          <p style="margin:0 0 6px;color:#991b1b;font-size:13px;font-weight:700;">{{seq}}. {{jiraKey}} — {{storyName}}</p>
          <p style="margin:0;color:#7f1d1d;font-size:12px;line-height:1.5;"><strong>Action Required:</strong> {{actionRequired}}</p>
        </td></tr>
```

`{{seq}}` is a 1-based counter. Source rows: every story flagged
`Blocked` plus any non-blocked story with a non-empty `requiredAction`
other than `No action required.` Release-gate `BLOCKED` or `NOT_YET`
also produces one virtual row at the top (`jiraKey` = the fixVersion,
`storyName` = `fixVersion gate`, `actionRequired` = the verbatim
policy log line).

#### `{{epicRows}}` — one `<tr>` per Epic returned by STEP 3-D

Row template:

```html
        <tr style="background:{{rowBg}};">
          <td style="padding:11px 10px;font-size:13px;color:#1f2937;font-weight:600;border-bottom:1px solid #e2e8f0;vertical-align:top;font-family:Consolas,monospace;">{{epicKey}}</td>
          <td style="padding:11px 10px;font-size:13px;color:#1f2937;border-bottom:1px solid #e2e8f0;vertical-align:top;line-height:1.4;">{{epicName}}</td>
          <td style="padding:11px 10px;font-size:12px;color:#475569;border-bottom:1px solid #e2e8f0;vertical-align:top;">{{epicFixVersions}}</td>
          <td style="padding:11px 10px;text-align:center;font-size:13px;color:{{epicStatusColor}};font-weight:700;border-bottom:1px solid #e2e8f0;vertical-align:top;white-space:nowrap;">{{epicStatusSymbol}}&nbsp;{{epicStatusLabel}}</td>
        </tr>
```

Per-cell semantics:
- `{{epicKey}}` — Jira key (e.g. `CM-1`).
- `{{epicName}}` — Jira `summary` verbatim (no truncation).
- `{{epicFixVersions}}` — comma-separated `fixVersion.name` values
  (e.g. `8.0, 8.0.2`). Render `—` (em-dash) if the Epic has no
  fixVersions attached.
- `{{epicStatusLabel}}` — `Released` / `Pending` / `Unassigned` /
  `Excluded`.
- `{{epicStatusSymbol}}` — `✓` / `⚠` / `—` / `✗` per §15.2.
- `{{epicStatusColor}}` — palette below.
- `{{rowBg}}` — alternate `#ffffff` and `#f8fafc` for zebra striping.

Epic-status color palette:

| Status | `epicStatusColor` |
|---|---|
| `Released` | `#15803d` (green) |
| `Pending` | `#b45309` (amber) |
| `Unassigned` | `#64748b` (gray) |
| `Excluded` | `#991b1b` (red) |

Epics appear in the email in `key` order (e.g. `CM-1`, `CM-2`, …).

#### `{{githubFileRows}}` — one `<tr>` per distinct spec file written

Row template:

```html
        <tr>
          <td style="padding:11px 12px;font-size:12px;color:#1f2937;border-bottom:1px solid #e2e8f0;font-family:Consolas,monospace;">{{filePath}}</td>
          <td style="padding:11px 12px;font-size:12px;color:#475569;border-bottom:1px solid #e2e8f0;">{{updatedByStories}}</td>
          <td style="padding:11px 12px;font-size:12px;color:#475569;border-bottom:1px solid #e2e8f0;">{{sectionsUpdated}}</td>
        </tr>
```

- `{{filePath}}` — BookStack page identifier (e.g.
  `Salary (page 360)`) — same format as `{{specFile}}` above.
- `{{updatedByStories}}` — comma-separated Jira keys (e.g.
  `CM-2, CM-3, CM-9`).
- `{{sectionsUpdated}}` — comma-separated canonical-table names with
  row counts (e.g. `ATC (+6), Form (+3), Audit Trail (+1), User Interfaces (+8)`).

### 9-D. Conditional sections

Three sections appear only when their count is non-zero:

- **Epic Release Status** — the entire `<tr>` block between
  `{{epicScanBlockStart}}` and `{{epicScanBlockEnd}}` markers in
  `resources/email_template.html` is REMOVED if
  `epicsScannedCount == 0`. When present, `{{epicRows}}` is
  substituted per §9-C.
- **Manual Actions Required** — the entire `<tr>` block between
  `{{manualActionsBlockStart}}` and `{{manualActionsBlockEnd}}` markers
  is REMOVED if `manualActionsRequiredCount == 0`. (The markers
  themselves are also removed; the row gap is filled by the
  surrounding rows naturally.)
- **Specification Files Updated** — same conditional removal between
  `{{specFilesBlockStart}}` and `{{specFilesBlockEnd}}` if
  `githubFilesUpdatedCount == 0`.

When present, the markers themselves are removed from the output but
the block they wrap is kept verbatim with placeholders substituted.

### 9-E. After substitution

After running the substitutions above on `_core/resources/email_template.html`:
1. Strip the `{{epicScanBlockStart}}` / `{{epicScanBlockEnd}}` marker
   lines (whether the block is kept or removed).
2. Strip the `{{manualActionsBlockStart}}` / `{{manualActionsBlockEnd}}`
   marker lines similarly.
3. Strip the `{{specFilesBlockStart}}` / `{{specFilesBlockEnd}}` marker
   lines similarly.
4. Verify no `{{...}}` placeholders remain (this guarantees no leaked
   unrendered variable hits the recipient). If any remain, abort the
   email step with `email_send_status: FAILED reason='unrendered
   placeholder in template: <name>'`.
5. **Structure self-check (MANDATORY).** Confirm the rendered body
   begins with the template root (`<html` … `<body`) and contains the
   template's status-summary table plus its section `<h2>` headers. If it
   does NOT (e.g. it starts with a bare `<h2>`, or is a short
   hand-written summary), you did NOT render the template — discard it,
   re-read `_core/resources/email_template.html`, substitute again, and
   re-check. NEVER emit a non-template body.
6. Emit the result between `<!-- EMAIL_BODY_START -->` and
   `<!-- EMAIL_BODY_END -->` in the log file.

### 9-F. Status color palette

| Status | `statusBadgeBg` | `statusBadgeFg` | `statusBarColor` (header bottom-border) |
|---|---|---|---|
| `Completed` | `#dcfce7` | `#166534` | `#16a34a` |
| `Completed (No Changes)` | `#e2e8f0` | `#475569` | `#64748b` |
| `Completed with Warnings` | `#fef3c7` | `#92400e` | `#f59e0b` |
| `Skipped` | `#fef3c7` | `#92400e` | `#f59e0b` |
| `Blocked` | `#fee2e2` | `#991b1b` | `#dc2626` |
| `Failed` | `#fee2e2` | `#991b1b` | `#dc2626` |

Story-row badge palette (`{{badgeBg}}` / `{{badgeFg}}`):

| Story status | `badgeBg` | `badgeFg` |
|---|---|---|
| `Updated` | `#dcfce7` | `#166534` |
| `No Change` | `#e2e8f0` | `#475569` |
| `Skipped` | `#fef3c7` | `#92400e` |
| `Blocked` | `#fee2e2` | `#991b1b` |
| `Excluded` | `#f1f5f9` | `#64748b` |

### 9-G. Final-status-message variants

Select one based on `status` + `manualActionsRequiredCount`:

| Condition | `{{finalStatusMessage}}` |
|---|---|
| `status == SUCCESS` AND `manualActionsRequiredCount == 0` | `The routine completed successfully and the relevant specification page was updated.` |
| `status == NO_CHANGE` | `The routine completed successfully. No specification updates were required because all eligible stories were already up to date.` |
| `status == SUCCESS` AND `manualActionsRequiredCount > 0` | `The routine completed with warnings. Some stories were updated, while others require manual action. Please review the Manual Actions Required section above.` |
| `status == BLOCKED` (release-gate) | `The routine did not update the specification because the configured fixVersion is not confirmed as released in Jira. Please see the Manual Actions Required section above.` |
| `status == FAILED` | `The routine failed before completing. No specification updates were made. The full error trail is in the run log linked below.` |
| `status == SKIPPED` (release-gate) | `The routine did not run because the configured fixVersion's release date is in the future. The next scheduled run after the release date will resume processing.` |

**Dry-run banner overlay:** when `dry_run == true`, the routine
prepends the following to `{{finalStatusMessage}}` regardless of the
underlying status:

```
[DRY RUN] No BookStack write was performed. The page-update results
described below show what the routine WOULD have written. Re-fire
without the DRY_RUN env var (or set DRY_RUN=false) to apply the
changes for real.
```

The email subject is also prefixed with `[DRY RUN] ` and the AUDIT
SUMMARY contains a `Dry-run: YES (no write to BookStack)` line. The
underlying `status` value is unchanged.

---

## STEP 10 — Send notification email (UNCONDITIONAL)

Invoke `python routines/send_notification.py <local_log_path>`. **Run on
every status — SUCCESS, NO_CHANGE, SKIPPED, BLOCKED, FAILED — without
exception.**

The script:
1. Reads the YAML frontmatter from the log file.
2. POSTs one HTTPS request per recipient to
   `https://api.resend.com/emails` with `Authorization: Bearer <RESEND_API_KEY>`.
3. Patches the log's `email_send_status` to `SENT` / `PARTIAL` / `FAILED`
   / `SKIPPED`.
4. Returns exit 0 always; exit 6 only if `RESEND_API_KEY` is unset
   (`SKIPPED`).

**`PENDING` is not a valid final status — if you record `PENDING`, you
didn't run the script. Run it.**

Send failures do NOT abort the run; the log is already on GitHub. Record
the result on the `Email send:` line of the AUDIT SUMMARY.

---

## STEP 11 — Final banner

Print the **`VOILA! JOB DONE.`** banner — ASCII only — on
`status=SUCCESS` or `status=NO_CHANGE`. **Never** print the banner on
`SKIPPED`, `BLOCKED`, or `FAILED` (the AUDIT SUMMARY conveys the
non-success outcome).

Banner layout:
```
========================================
            VOILA! JOB DONE.
========================================
Routine : <routine_slug>
Status  : <SUCCESS|NO_CHANGE>
Wiki    : <TARGET_PAGE_ID> r<new_rev>
Email   : <SENT N_OK/N_TOTAL>
Log     : <log_html_url>
========================================
```

---

## Safety rails

- **Refuse any write whose pre-flight check fails.** Set `status=FAILED`.
- Every POST/PUT/DELETE must pre-flight with a GET. The page → chapter →
  book chain MUST roll up to a book inside shelf `id=3`. Refuse otherwise.
- **Never** PUT a page whose current name was NOT the matched destination
  from `wiki_destination.json`.
- **Never** touch a book/chapter/page outside the Specification shelf.
- **Updates are additive** — never delete or strip existing wiki content
  except for in-place replacement of a sub-section body inside an
  existing `<h3>` story node when Jira clearly provides a newer released
  update (per `release-filter-policy.md §10`).
- **Never** print `WIKI_TOKEN_ID`, `WIKI_TOKEN_SECRET`, `GITHUB_TOKEN`,
  `RESEND_API_KEY`, or the AUTH header value. The AUDIT SUMMARY
  `Credentials:` line MUST say
  `from-env (lengths only — no values)`.
- **NEVER use wiki, BookStack, wiki catalogs, or wiki release dates to
  determine release status.** Release confirmation is Jira-only per
  `release-filter-policy.md`. Wiki reads remain permitted only for
  composing write payloads and diffing against `PRIOR_HTML`.
- Do NOT push to or modify the cloned source repository.
- **HTTP retry policy (idempotent operations only).** The default
  on-exception rule below is the LAST resort — first apply the retry
  policy in §Safety: HTTP retries.
- On any **unrecoverable** exception (4xx response, validation FAIL,
  unhandled error after retries exhausted): print a traceback with
  secrets redacted, set `status=FAILED`, exit cleanly.

---

## Safety: HTTP retries

External calls (Jira API, BookStack API, GitHub Contents API, Gmail
API) occasionally fail transiently — a single 502 from BookStack or a
30-second network blip at fire time would otherwise tank the whole
run and produce a false-positive `FAILED`. The routine MUST retry
**idempotent** operations under the following policy:

### Retryable (apply backoff and retry up to 3 times)
- `GET` on any external resource (Jira issue, BookStack page,
  BookStack image upload status).
- `PUT /api/pages/<id>` — idempotent at the URL+body level (same body
  twice has the same effect; pre-flight `updated_at` check happens
  before each retry).
- `POST /api/image-gallery` — semantically retryable (the routine
  matches by filename in §11.1, so a duplicate upload from a successful
  but mis-attributed first attempt is detected by the next merge).
- `POST https://api.resend.com/emails` per recipient — retried only
  on transient (5xx / network) errors, NOT on 4xx (`401 invalid_key`,
  `403`, `422`).
- HTTP status codes that are always retryable: **502**, **503**, **504**.
- Network conditions that are always retryable: connection-reset,
  read-timeout, DNS resolution failure.

### Non-retryable (FAIL immediately, no retry)
- `4xx` responses (401, 403, 404, 409, 412, 422, 429-with-no-Retry-After).
  These are deterministic — retrying won't change the outcome.
- Validation failures (STEP 6 checks). These are content errors, not
  transport errors.
- `POST /api/pages` (page create — non-idempotent; a successful
  retry could create two pages). On any failure: FAIL the run, record
  the response, and let an operator manually verify before retry.

### Retry mechanics
- **Attempts:** at most 3 total (initial + 2 retries) for any single
  HTTP call.
- **Backoff:** exponential — 1s before retry 1, 3s before retry 2.
  Total wall-clock budget per call: ~4 seconds of waits + the actual
  HTTP timeouts. Cap the cumulative wait at 30 seconds; if the budget
  is exhausted before retry 3, abort that call with FAILED.
- **`429 Too Many Requests`:** if the response carries a `Retry-After`
  header, honour it exactly (single retry, no exponential). If no
  `Retry-After`, fall through to the default exponential.
- **Logging:** every retry emits a one-line log entry —
  `Retry <n>/3 — <method> <path> — <last_outcome> — sleeping <s>s`.
  The final outcome (success or exhausted-FAIL) emits a summary line.

### What does NOT change
- The safety allowlist (per-run `ALLOWED_WRITES`) still gates every
  request shape. Retries hit the same allowlisted (method, path) only.
- The pre-flight GET before any PUT still runs once per retry attempt
  (re-verifies `updated_at`, page chain, shelf membership).
- Idempotency at the content level (§10.3 dedup contract) holds
  regardless of retries — a successful retry of a `PUT /api/pages/<id>`
  with the same body is a no-op against the same content.

---

## Allowed writes

**BookStack** (only inside `SPECS_SHELF_ID = 3`):
- `POST /api/books` — only if STEP 5C create-flow needs a missing module
  book.
- `PUT  /api/shelves/3` — only to attach a newly created book.
- `POST /api/chapters` — only if STEP 5C needs to create a chapter.
- `POST /api/pages` — only on STEP 5C create-flow.
- `PUT  /api/pages/<TARGET_PAGE_ID>` — STEP 7 update.

**GitHub**:
- `PUT /repos/devnith-git/ohrm-wiki-sync/contents/logs/<routine_slug>/<ts>.md`
  (STEP 9 only — per-run log)
- `PUT /repos/devnith-git/ohrm-wiki-sync/contents/resources/wiki_destination.json`
  (FIRST-FIRE BOOTSTRAP §5-C.5.1 step 7 + STEP 5C page-recreation case
  only — destination self-commit per §5-C.5.2 constraints: target branch
  MUST be `main`, diff MUST touch ONLY `routine_destinations.<own_slug>`,
  diff MUST be confined to the allowed field set per §5-C.5.2)

**Resend HTTPS API** (STEP 10 only):
- N HTTPS POST requests to `https://api.resend.com/emails`
  (N = recipient count), each with `Authorization: Bearer <RESEND_API_KEY>`.

Every other write MUST be refused before the request leaves the agent.

---

## Common mistakes (do NOT do)

- Calling the OHRM Wiki MCP or BookStack `/api/...` to determine whether
  a fixVersion is released. The release gate is **Jira-only**.
- Authoring narrative paragraphs after a heading without a corresponding
  sub-section `<h4>`. Bodies hang off the canonical sub-section list.
- Emitting an `<h4>Interfaces (UIs)</h4>` outside the per-story `<h3>`
  scope. UIs always live inside their story.
- Forgetting the per-story empty-state line `<p>No UI references were
  available in Jira for this story.</p>` when no UI assets exist.
- Using an internal project name (`Compensation 2.0`, `Phase 2`) as the
  release-section `<h2>` text. The release `<h2>` is the fixVersion
  string verbatim.
- Skipping STEP 10 because the run was `NO_CHANGE` or `BLOCKED`. The
  email is the operator's notification channel and runs on every status.
- Treating Jira `released:false` + past `releaseDate` as not-released.
  Past `releaseDate` IS released per policy §6.
- Treating Jira `released:false` + empty `releaseDate` as released. That
  is **BLOCKED** per policy §3.
- Embedding `<img>` inside `<td>` cells (legacy table content stays as
  text references — image links go in the Interfaces (UIs) sub-section).
- Highlighting changes with yellow `<tr style="background-color:#fff7d6;">`
  or inline `[New — KEY]` spans. The canonical guideline has none.
- Creating a new `Audit Trail` ATC row when `Audit Log` or `Audit History`
  already exists in the table — they are the same feature per §5-C.1.
  Update the existing row's Scenario instead, and append the new Jira key
  to the row's parenthetical key list.
- Splitting one feature across multiple ATC rows because two Jira stories
  used different wordings for it (e.g. `Salary Screen` for CM-3 and
  `Salary Structure` for CM-17). The semantic-match step (§5-C step 1.b)
  exists precisely to prevent this — merge to one row, scenario combines
  the released wording from both.
- Dropping bullets from an existing Scenario cell just because the current
  Jira description doesn't repeat them. The prior bullets are
  earlier-confirmed released behavior and must be preserved (§5-C.2 step 3
  — never silently shrink coverage).
- Adding a Form / Search / Audit Trail row for a field while ignoring
  whether the field already has a row in that table. Apply §5-C.3 dedup
  per table — match cell is `Field Name` for Form / Search, `Action`
  for Audit Trail, `Column Name` for List.
- Skipping the cross-table completeness pass (§5-C.4) on `SUCCESS` runs
  — if Jira adds a field to a form, the Form table gets a row even if
  the contributing story's primary contribution was the ATC row.
- **Writing the Scenario cell as a paragraph or as run-on prose.** The
  guideline §2.2 mandates bullet points for multi-detail table cells —
  the Scenario cell must always be a `<ul>` of `<li>` items, one bullet
  per distinct test case. The CM run on 2026-05-17 produced rows like
  `Pay Grade Soft Delete (CM-2)` and `Salary Structure (CM-3, CM-27)`
  in paragraph form; on the next run, §5-C.2 step 1 (legacy
  paragraph-form repair) splits each into discrete `<li>` items by
  sentence boundary and the merge proceeds.
- **Cramming multiple test cases into one `<li>`.** Each distinct
  behavior, edge case, or rule is its own bullet. A bullet describes
  one assertion the QA engineer would verify in one test pass — not
  three.
- **Using `<ul>` / `<ol>` in the Form table's `Validation(s)` or
  `Validation Message(s)` columns.** Those two columns are the canonical
  exception (`specification-writing-guideline.md` §2.4 Form note): they
  use `-`-prefixed plain-text lines, not bullets.

---

## Authority recap

```
release-filter-policy.md         ← TOP
specification-writing-guideline  (markdown / html / pdf / txt — any variant)
SKILL.md                          (this file)
WIKI_PAGE_RENDER.md
routines/<slug>_daily_sync.prompt.md
```

When in doubt, re-read top of stack.
