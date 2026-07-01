---
name: cs-feature-routing
description: >
  CS-feature-only workflow authority. Reads CS Jira issues, splits each into
  per-affected-area scopes, dynamically discovers the correct Enterprise Wiki
  Specification destination per scope (inside shelf id=3), and applies the
  canonical specification-writing guideline to update each destination
  additively. This file is the workflow authority for the CS routine in the
  same role that SKILL.md plays for agile project routines — for CS, this
  file SUPERSEDES SKILL.md. Hard-isolated: refuses to run for any routine
  other than `cs_features_daily_sync` / `routine_type=cs_feature`.
---

# CS Feature Routing — Universal Workflow for Cross-Product CS Specifications

This skill is the runtime authority for the CS routine. CS features
(customer-specific features) cross product-area boundaries — one Jira
issue can affect Leave + Attendance, Performance + Employee Profile,
Recruitment + Onboarding, etc. The agile routines (CM, PNP, Roster,
Orange Sign) each target a single fixed BookStack page (e.g. CM →
`Salary`, PNP → `Performance Core`). CS does not — its destination is
**discovered per scope at fire time** inside the Specification shelf.

This file therefore replaces `SKILL.md` as the workflow authority for
the CS routine, while continuing to defer to the three behavior
resources that are universal across every routine in this repo:

- `release-filter-policy.md` — TOP of authority (release eligibility,
  per-issue completion/exclusion checks, ATC + canonical-table contract,
  UI gallery rule, run-log fields).
- `specification-writing-guideline.md` — canonical table shapes, heading
  hierarchy, bullet-form contract, Form Note exception.
- `WIKI_PAGE_RENDER.md` — exact HTML rendering for the 5 canonical
  tables and the User Interfaces (UIs) gallery.

When this file disagrees with any of the three above, **they win**. This
file only adds CS-specific behavior — scope splitting, destination
discovery, multi-page write fan-out — and tightens validation for those
additions.

---

## 0. Hard isolation guard (runtime — abort if invoked by non-CS routine)

The FIRST executable check of every fire that loads this file is the
isolation guard. The routine reads its own slug from
`routine_destinations.<slug>` and its declared routine type from the
prompt parameters. Both MUST match the CS sentinel values; if either
fails the guard, the routine MUST abort immediately, before any Jira
or BookStack call.

```
# Pseudocode — implement in Bash at STEP 1 or inline in the routine prompt.
if [ "$ROUTINE_SLUG" != "cs_features_daily_sync" ] || [ "$ROUTINE_TYPE" != "cs_feature" ]; then
  echo "BLOCKED: CS_FEATURE_ROUTING_SKILL.md invoked by non-CS routine"
  echo "  routine_slug=$ROUTINE_SLUG (expected: cs_features_daily_sync)"
  echo "  routine_type=$ROUTINE_TYPE (expected: cs_feature)"
  # Set status=BLOCKED reason='CS feature routing skill invoked by non-CS routine'
  # Skip every subsequent step. Proceed only to STEP 8 (AUDIT) / STEP 9 (log) /
  # STEP 10 (email) so the abort is recorded.
  exit_with_blocked
fi
```

This guard exists because the CS skill carries fan-out logic that would
write to multiple unrelated wiki pages if invoked from an agile routine
that expects a single fixed destination. There is no override flag and
no debug bypass — if the guard fires, the routine aborts.

The audit log and notification email for a guard-triggered abort
contain the verbatim BLOCKED line:

```
Blocked - CS feature routing skill invoked by non-CS routine.
```

---

## 1. Authority order (when files disagree)

1. **`resources/release-filter-policy.md`** — top. Global Jira-only
   release eligibility rules; supersedes every other file.
2. `resources/specification-writing-guideline.md` — canonical structural
   authority for table shapes, heading hierarchy, bullet-form, and the
   Form Note exception.
3. **`resources/CS_FEATURE_ROUTING_SKILL.md`** — THIS file. CS-specific
   workflow (scope splitting, destination discovery, multi-page write).
4. `resources/WIKI_PAGE_RENDER.md` — HTML rendering mechanics.
5. `routines/cs_features_daily_sync.prompt.md` — thin wrapper carrying
   only CS routine parameters. May not override anything above.

`SKILL.md` is **not** in the CS authority stack. The CS routine MUST
NOT read or follow `SKILL.md` — every CS workflow rule lives here.

If any of (1), (2), (4) is missing at STEP 2, abort
`status=BLOCKED reason='resources/ unreachable — cannot proceed without canonical rules'`.

---

## 2. CS-specific routine inputs

The routine reads these once at STEP 2 from
`routine_destinations.cs_features_daily_sync` in
`wiki_destination.json` and from its prompt parameters:

| Input | Source | Notes |
|---|---|---|
| `ROUTINE_SLUG` | constant `cs_features_daily_sync` | Hard-coded; used by §0 isolation guard. |
| `ROUTINE_TYPE` | constant `cs_feature` | Hard-coded; used by §0 isolation guard. |
| `JIRA_PROJECT_KEY` | `routine_destinations.cs_features_daily_sync.jira_project_key` | The Jira project key that hosts CS features. |
| `RELEASE_SCOPE` | `routine_destinations.cs_features_daily_sync.release_scope` | The CS-specific fixVersion. Standard release-gate rules from `release-filter-policy.md` §2-§6 apply. |
| `CS_JQL_FILTER` | `routine_destinations.cs_features_daily_sync.cs_feature_jql_filter` | Verbatim JQL fragment that identifies CS features (e.g. `labels in (cs-feature, customer-specific)`, or `"Feature Type" = "CS"`). Combined with the release-scope JQL via `AND`. |
| `SPECS_SHELF_ID` | constant `3` | Only writes inside this shelf are allowed. |
| `DESTINATION_MODE` | `routine_destinations.cs_features_daily_sync.destination_mode` (`dynamic_by_affected_area`) | Tells the routine NOT to use `page_id` as a fixed target — discover per scope instead. |

There is **no `TARGET_PAGE_ID`** for this routine. Every CS scope
discovers its own destination at fire time. The `page_id` / `book_id`
fields in `wiki_destination.json` for this slug are explicitly `0` and
the routine MUST treat any attempt to use them as a fixed write target
as a bug (validation FAIL).

---

## STEP 1 — Env-var verification (Bash)

First action of every run. Identical to the agile routines:

```
for v in ATLASSIAN_CLOUD_ID WIKI_BASE_URL WIKI_TOKEN_ID WIKI_TOKEN_SECRET; do
  if [ -z "${!v}" ]; then echo "FATAL: env var $v is not set"; exit 1; fi
done
echo "env check: ATLASSIAN_CLOUD_ID len=${#ATLASSIAN_CLOUD_ID}  WIKI_BASE_URL=$WIKI_BASE_URL  WIKI_TOKEN_ID len=${#WIKI_TOKEN_ID}  WIKI_TOKEN_SECRET len=${#WIKI_TOKEN_SECRET}  GITHUB_TOKEN len=${#GITHUB_TOKEN}"
```

Read the optional **`DRY_RUN`** flag (`true` / `1` / `yes` → DRY_RUN
mode). The flag's effect on STEP 7 and STEP 9 is identical to the
agile routines — preview only, no BookStack write.

Construct `AUTH="Authorization: Token ${WIKI_TOKEN_ID}:${WIKI_TOKEN_SECRET}"`.
**Never echo AUTH. Never `set -x`.** Audit log Credentials line MUST say
`from-env (lengths only — no values)`.

Immediately after env-var verification, run the **§0 hard isolation
guard**. Abort with the verbatim BLOCKED line if the guard fails.

---

## STEP 2 — Repo-aware bootstrap

1. `ls -la` to verify `resources/`, `routines/`.
2. Read the **five** canonical resource files in this authority order:
   - `release-filter-policy.md`
   - `specification-writing-guideline.md` (or html / pdf / txt variant)
   - `CS_FEATURE_ROUTING_SKILL.md` (this file)
   - `WIKI_PAGE_RENDER.md`
   - `wiki_destination.json`
   - `email_template.html` (STEP 9)
3. Print the resource-bootstrap banner (CS variant):
   ```
   ==================== RESOURCE BOOTSTRAP (CS) ====================
     [✓] resources/release-filter-policy.md         (<N> bytes)
     [✓] resources/specification-writing-guideline.<ext>  (<N> bytes)
     [✓] resources/CS_FEATURE_ROUTING_SKILL.md      (<N> bytes)
     [✓] resources/WIKI_PAGE_RENDER.md              (<N> bytes)
     [✓] resources/wiki_destination.json            (<N> bytes)
     [✓] resources/email_template.html              (<N> bytes)
   Authority order (top wins):
     release-filter-policy.md
       > specification-writing-guideline.<ext>
         > CS_FEATURE_ROUTING_SKILL.md
           > WIKI_PAGE_RENDER.md
             > routines/cs_features_daily_sync.prompt.md
   Mode: 'repo-aware (CS)' (git <short hash>)
   ===================================================================
   ```
   On any missing file, render `[✗]` against it and abort
   `status=BLOCKED reason='resources/ unreachable'`.
4. Locate this routine's slug entry in `routine_destinations`. Capture:
   - `release_scope` → `RELEASE_SCOPE`
   - `jira_project_key` → `JIRA_PROJECT_KEY`
   - `jira_project_lock` → `JIRA_PROJECT_LOCK`
   - `cs_feature_jql_filter` → `CS_JQL_FILTER`
   - `destination_mode` → `DESTINATION_MODE` (MUST be
     `dynamic_by_affected_area` — abort if anything else)
   - `allowed_destination_shelf_id` → `SPECS_SHELF_ID` (MUST be `3` —
     abort if anything else)

4-bis. **Project-lock enforcement (HARD — CS features come ONLY from
   the Hightower / HT Jira project).** This guard is independent of
   the §0 isolation guard and runs at every fire. It exists because
   CS features are deliberately sourced from one project (`HT`) — a
   routine that suddenly starts querying a different project would
   contaminate the canonical specification pages with non-CS content.

   - **Constant:** `CS_PROJECT_LOCK = "HT"` (Hightower). Hard-coded
     here in the skill file. Operators MUST NOT change this constant
     to retarget the routine at a different project; if a future
     CS-source project is added, scaffold a SEPARATE routine for it
     (e.g. `cs_features_<newproject>_daily_sync.prompt.md`) with its
     own destination entry and its own constant.
   - **Check 1 — JSON value matches constant:** `JIRA_PROJECT_KEY`
     read from `routine_destinations.cs_features_daily_sync.jira_project_key`
     MUST equal `CS_PROJECT_LOCK`. If not → abort
     `status=BLOCKED reason='CS routine is locked to project HT
     (Hightower); routine_destinations.cs_features_daily_sync.jira_project_key
     = <actual> is not permitted.'` and surface as a manual_action.
   - **Check 2 — redundant lock field present and matches:**
     `JIRA_PROJECT_LOCK` read from
     `routine_destinations.cs_features_daily_sync.jira_project_lock`
     MUST equal `CS_PROJECT_LOCK`. This field is a tamper-evidence
     guard — an edit that silently changes `jira_project_key` will
     also have to change `jira_project_lock`, doubling the chance
     of a code-review catch. On mismatch → abort
     `status=BLOCKED reason='CS routine project-lock tamper: jira_project_lock
     = <X> does not match the in-skill constant HT.'`
   - **Check 3 — every JQL the routine emits is bound to HT:** at
     STEP 3-C the routine MUST construct the story-level JQL as
     `project = HT AND fixVersion = "<RELEASE_SCOPE>" AND ( <CS_JQL_FILTER> )`.
     The `project = HT` clause is literal — NOT
     `project = <JIRA_PROJECT_KEY>` (string-substituted from JSON).
     Same at STEP 3-D Epic scan: `project = HT AND issuetype = Epic`.
     This is belt-and-braces: even if check 1 and 2 were bypassed,
     the JQL still cannot escape HT because the project clause is
     hard-coded. Any code path that emits a JQL with a different
     `project = ...` clause is a routine bug — STEP 6 validates that
     the actual JQL used at STEP 3-C / STEP 3-D contains the literal
     `project = HT` substring before any wiki write is accepted.

5. **Re-confirm the §0 isolation guard.** The runtime values now read
   from JSON must agree with the hard-coded slug constants. If
   `ROUTINE_SLUG != cs_features_daily_sync` or
   `ROUTINE_TYPE != cs_feature`, abort BLOCKED.
6. **Fetch the live Specification shelf** for STEP 4-CS-D destination
   discovery: `GET /api/shelves/3`. Capture the `books[]` array as
   `LIVE_SPEC_BOOKS`. Abort `status=BLOCKED` on 404 / non-2xx.
7. **Refresh `specification_nav_tree`** per `release-filter-policy.md`
   §16 (the global strict rule — applies to every routine, every
   fire). Walk each `book_id` in `LIVE_SPEC_BOOKS` via
   `GET /api/books/<book_id>`, capture every chapter and page with its
   live sort_order / slug / name, diff against the stored
   `specification_nav_tree.books[]` in `wiki_destination.json`, and
   self-commit the refreshed block back to the current branch when the
   diff is non-empty. The §4-CS-D candidate enumeration at STEP
   4-CS-D.1 then reads the freshly refreshed tree instead of re-walking
   the API (the live tree IS the candidate list, minus disqualifiers).
   Abort `status=BLOCKED reason='specification_nav_tree sync failed'`
   on any non-2xx during the walk. The audit log MUST include a
   `## STEP 2.7 — Nav-Tree Sync (CS)` section per §16.5 listing every
   diff line plus the new `node_count` totals.

---

## STEP 3 — Release confirmation gate (Jira-only)

**Authoritative reference: `release-filter-policy.md` §1–§6.**

### 3-A. Fetch the configured fixVersion

Use the Atlassian MCP to load the `fixVersion` object for `RELEASE_SCOPE`
in project `JIRA_PROJECT_KEY`. If not found → abort
`status=BLOCKED reason='configured fixVersion <RELEASE_SCOPE> not found in
project <KEY>'`.

### 3-B. Evaluate per `release-filter-policy.md` §2–§6

Identical to the agile routines. CONFIRMED → proceed. NOT_YET / BLOCKED
→ skip STEP 4–STEP 7, still run STEP 3-D + STEP 8 + STEP 9 + STEP 10.

### 3-C. On CONFIRMED — query CS-feature stories

The CS routine combines the release-scope JQL with the CS-feature
filter. **The project clause is the literal token `HT`**, never a
template substitution — see §2 step 4-bis check 3.

```jql
project = HT
  AND fixVersion = "<RELEASE_SCOPE>"
  AND ( <CS_JQL_FILTER> )
```

The parentheses around `<CS_JQL_FILTER>` are mandatory — the filter
fragment may contain its own `OR` operators and must bind as a single
clause inside the outer `AND`.

Fetch with `fields = ["summary","description","status","issuetype",
"resolution","labels","components","fixVersions","attachment","comment",
"priority","customfield_*"]`. Paginate with `nextPageToken` until
`isLast=true`.

### 3-D. Per-Epic project scan (informational)

Run the standard project-wide Epic scan per `release-filter-policy.md`
§15. CS Epics may have CS labels themselves; the scan reports every
Epic in the Hightower project regardless of label. The query is
literal — `project = HT AND issuetype = Epic` (NOT
`project = <JIRA_PROJECT_KEY>` — see §2 step 4-bis check 3). Output
is the `epic_scan_summary` array — identical fields to the agile
routines. Runs on every outcome (CONFIRMED / NOT_YET / BLOCKED).

---

## STEP 4 — Per-issue eligibility filter

Run the standard buckets from `release-filter-policy.md` §7 / §8 / §9
**in order**:

1. **Issue-type bucket** (§8) — Epic is container-only (no ATC row,
   walked for child stories), Story / Task are processed, Sub-task /
   Improvement / Refactor / Spike are excluded by type. **Bug — EVERY Bug
   returned by the CS JQL is evaluated, never skipped by type.** For each
   Bug, apply the requirement-defect carve-out
   (`bug-requirement-filter-policy.md` §1) AND read its comments (§1.3
   signal (c) + `release-filter-policy.md` §10.5). Decision:
   - **RECORD** in the wiki (promote — treated like a Story for
     STEPs 4-CS → 5) when the Bug updates/changes a requirement: any of
     (a) `Type Of Defect = Requirement`, (b) `[Requirement]` summary
     prefix, or (c) a qualifying PO/QA/triage comment per §1.3 that accepts
     the bug as a requirement/spec change. Count `bugs_requirement_processed`;
     log the matched signal (incl. comment id/author/excerpt for (c)).
   - **PASS** (exclude) when no requirement signal is present (pure defect
     fix, no spec impact) OR §10.5 bucket 3 shows the bug was
     deprioritized. Log `Excluded - <KEY> Bug passed; not a requirement
     change (no Type-Of-Defect=Requirement, no [Requirement] prefix, no
     qualifying comment).` so every Bug's record-vs-pass verdict is visible.
2. **Completion check** (§7) — `statusCategory.key == "done"` or
   `status.name in {Done, Closed, Completed, Released, CPO/PM Accepted}`.
3. **Exclusion check** (§9) — resolution / status / labels match any of
   `deferred`, `cancelled`, `rejected`, `removed-from-scope`, `dropped`,
   `duplicate`, `wont-do`, `won't do`, `moved`, `not-applicable`, `na`.
4. **Source-material sanity gate** — description not empty, contains
   extractable behavior text (not solely Drive/Figma links).
5. **Comment intelligence — deprioritization gate** (`release-filter-policy.md`
   §10.5 bucket 3) — read the issue's comments
   (`GET /rest/api/3/issue/<KEY>/comment?expand=renderedBody&maxResults=50&orderBy=-created`,
   reusing any fetch the bug-requirement carve-out already did this run;
   ignore bot authors). If the latest disposition on the work is a
   deprioritization / de-scope per the §10.5 phrase set, the issue is
   **EXCLUDED this run** (no scope, no routing) — log `Excluded - <KEY>
   deprioritized per comment <id> by <author> (<date>): "<excerpt>"`. A
   later re-prioritizing comment overrides an earlier deprioritization
   (recency guard). For a promoted Bug, this gate overrides the carve-out
   (a deprioritized requirement-defect Bug stays excluded).

Survivors → `ELIGIBLE_ISSUES` (Story / Task / promoted requirement-defect
Bug that passed all buckets — Epics are walked but never themselves enter
ELIGIBLE_ISSUES). Scope changes voiced in comments (§10.5 bucket 2) are
NOT applied here — they are carried forward and applied at STEP 5 as
§10.4 CRUD evidence.

---

## STEP 4-CS — Affected-area scope splitting (CS-specific)

For each issue in `ELIGIBLE_ISSUES`, the routine builds one or more
**CS scopes**. A scope is the unit at which destination discovery,
canonical-table updates, and ATC rows operate — one scope produces one
destination decision and one (or more, on cross-product features) ATC
row contributions.

### 4-CS.1 Scope object shape

```yaml
issue_key: <e.g. CS-42>
issue_summary: <Jira summary verbatim>
scope_name: <short human label — one per scope, distinct within an issue>
affected_area: <one of: Leave | Attendance | Performance | Employee Profile |
                Recruitment | Onboarding | Time Tracking | Reports | Career
                Development | Configurations | Profile Settings | Goals |
                HR Administration | other-as-discovered-from-live-shelf>
source_evidence:
  - <verbatim quote(s) from Jira that justified the scope split>
  - <e.g. "Description heading: 'Leave Module' (line 14)">
  - <e.g. "Jira component: 'Attendance'">
  - <e.g. "Screen reference: 'Leave Apply' on line 22">
behavior_bullets:
  - <one canonical-table-ready bullet per distinct test case / behavior point>
candidate_destinations:        # populated at STEP 4-CS-D
  - book_id: <id>
    book_name: <name>
    chapter_id: <id or null>
    chapter_name: <name or null>
    page_id: <id>
    page_name: <name>
    score: <integer>
    score_evidence: [<reasons that contributed to the score>]
selected_destination:          # populated at STEP 4-CS-D; null if blocked
  page_id: <id>
  page_name: <name>
  book_id: <id>
  confidence: <score>
canonical_changes:             # populated at STEP 5
  atc_row: <composed row HTML / null>
  list_rows: [...]
  search_rows: [...]
  form_rows: [...]
  audit_rows: [...]
  ui_assets: [...]
```

### 4-CS.2 Split triggers — when one issue becomes multiple scopes

Split an issue into multiple scopes when Jira content **clearly**
describes multiple areas. Triggers (any one is sufficient):

- Description headings group behavior by module
  (`## Leave Module ... ## Attendance Module`).
- Issue has multiple Jira `components` and the description references
  each separately.
- Description references multiple distinct screens or API routes that
  belong to different product areas (e.g. `/leave/apply` AND
  `/attendance/punch`).
- Description explicitly enumerates affected modules
  (`Affected modules: Leave, Attendance`).
- A custom Jira field (e.g. `Affected Areas` / `Modules`) lists
  multiple values.

When a split trigger fires, the routine emits one scope per area, each
carrying ONLY the behavior bullets that belong to that area (sourced
from the same description by section/heading/component association).

### 4-CS.3 Single-scope cases

If none of the triggers in §4-CS.2 fires, the issue produces ONE scope
whose `affected_area` is inferred from (in priority order):

1. Single Jira `component` if exactly one is set.
2. Description-heading topic if the description has exactly one top-level
   heading (e.g. `## Leave Apply Modal`).
3. Screen / API route domain inferred from the description content.
4. Issue summary topic if no other signal is present.

### 4-CS.4 Ambiguous-multi-area block

If the issue clearly affects multiple areas but the Jira text does NOT
separate the behavior cleanly enough to attribute each bullet to a
single area (no heading split, no per-area component, no enumerated
section), the routine MUST block the issue:

```
Blocked - CS feature affects multiple product areas but Jira does not
provide enough scope separation to safely update wiki pages. Add
per-module headings (e.g. '## Leave Module', '## Attendance Module')
or per-area Jira components to the ticket and re-fire.
```

The issue surfaces in the email's Manual Actions Required section with
this verbatim line. The routine does NOT guess the split.

---

## STEP 4-CS-D — Destination discovery (CS-specific, per scope)

For each scope produced by STEP 4-CS, discover the destination
BookStack page inside Specification shelf id=3. The discovery is
**live** — uses the `LIVE_SPEC_BOOKS` captured at STEP 2 step 6,
NEVER a fallback to `GET /api/books` at the wiki root.

### 4-CS-D.1 Candidate enumeration

Candidates are read **directly from the freshly refreshed
`specification_nav_tree`** captured at STEP 2 step 7 (per
`release-filter-policy.md` §16). The routine MUST NOT re-walk
`GET /api/books/<id>` here — the STEP 2 walk is authoritative for this
fire. This guarantees the candidate set is consistent with what STEP
2.7 logged and committed.

For every book in `specification_nav_tree.books[]` where
`deprecated_at == null`:

1. Iterate the book's `chapters[]` (live chapters only — skip those
   with `deprecated_at != null`); each chapter's `pages[]` contributes
   one (book, chapter, page) tuple per live page.
2. Iterate the book's `orphan_pages[]` (live only); each contributes
   one (book, null, page) tuple.
3. Build the candidate list from these tuples. Every candidate inside
   shelf 3 is in scope; nothing outside shelf 3 is reachable from the
   tree.

Each candidate carries:
- `book_id`, `book_name`
- `chapter_id`, `chapter_name` (or null if the page sits directly under
  the book)
- `page_id`, `page_name`
- `page_description` (optional, if returned)
- `book_topics` from `specification_books[]` in `wiki_destination.json`
  (TOPIC SEED HINTS only — additive, not authoritative)

### 4-CS-D.2 Disqualifiers (applied first — drop the candidate)

A candidate is REMOVED from consideration if any of these hold:

- The candidate's `page_name` matches `exclusions.version_suffix_regex`
  in `wiki_destination.json` (e.g. `Salary - Compensation Management 1.0`).
- The candidate's `book_name` is `Other (For internal Use Only)` (book
  id=33) — that book contains internal guideline pages, never spec
  destinations.
- The candidate is the `canonical_guideline_page` per
  `wiki_destination.json`.
- The candidate's page name contains internal markers (`draft`, `wip`,
  `archive`, `obsolete`, `legacy`) as standalone tokens.

### 4-CS-D.3 Scoring (additive — sum per signal)

For each surviving candidate, accumulate a score from the signals
below. A signal contributes ONCE per scope/candidate pair — never
double-counts.

| Signal | Points |
|---|---|
| Explicit Jira destination label / custom field text equals the candidate's `page_name` (case-insensitive) | **+100** |
| Jira `components` value equals the candidate's book `name` or page `name` (exact, case-insensitive) | **+80** |
| The scope's `scope_name` equals the candidate's `page_name` (case-insensitive) | **+75** |
| The scope's screen reference / API route strongly matches the candidate's `page_name` (case-insensitive substring, length ≥ 6 chars) | **+65** |
| Jira `components` value matches one of the candidate book's `topics[]` (case-insensitive token match) | **+55** |
| Scope description keywords match the candidate's `page_name` or book topic (token overlap ≥ 2 distinct content words) | **+25** |
| The candidate page already contains an ATC row whose Feature/Topic/Field/Action equals one in `scope.behavior_bullets` (synonym-folded per `SKILL.md` §5-C.1 — same rules apply; the matching logic is identical) | **+20** |
| **Cross-shelf existence signal** — the scope's `scope_name` (or its head noun) matches an existing page's `name` anywhere in `specification_nav_tree` even when the page is in a DIFFERENT book than the topic-matching one. Apply once per scope: the matched existing page gets **+40** added to its score, so the routine prefers extending an existing page over creating a new one in a topic-matching but currently empty book. This signal exists to suppress duplicate creates when (e.g.) a Leave-related feature already has a page nested under Configurations & Management Tools — the existing page wins over a brand-new page in book 12. | **+40** |

The score is the SUM of every applicable signal. A candidate can score
above 100 (e.g. explicit label match +100 plus existing ATC presence
+20 = 120).

### 4-CS-D.4 Acceptance bands

After scoring every surviving candidate, sort by score descending.

| Top candidate's score | Decision |
|---|---|
| **≥ 80** | **ACCEPT** the top candidate as `selected_destination`. Confidence = score. |
| **60 – 79** | Accept ONLY if the top candidate's score is at least **25 points above** the second-best candidate. Otherwise BLOCK. |
| **< 60** | **BLOCK** for manual review. |

### 4-CS-D.5 Blocked destination

When a scope cannot be safely routed, emit:

```
Blocked - Could not identify a safe wiki destination for <KEY> scope
"<scope_name>". Manual destination mapping required.
```

Record the top 3 candidates and their score evidence in the audit log
(`scope.candidate_destinations[0..2]`). The scope contributes NO write
this run. The blocked scope surfaces in the email's Manual Actions
Required section.

### 4-CS-D.6 Same-destination grouping

Multiple scopes (from the same issue or different issues) may resolve
to the same `page_id`. Group them per destination — the routine writes
each touched page ONCE per fire (STEP 7), with all grouped scopes'
canonical-table changes merged into a single PUT body.

---

## STEP 5 — Compose merged HTML per accepted destination

For each destination identified at STEP 4-CS-D with at least one
accepted scope, repeat the read-merge-validate-write loop. The
canonical-table rules below are deferred verbatim to
`release-filter-policy.md` §10 and `specification-writing-guideline.md`
— this section adds NO new structural rules, it only describes the
loop.

### 5-A. Read existing page state

`GET /api/pages/<destination.page_id>` to fetch `PRIOR_HTML` and
`PRIOR_REV`.

Pre-flight verification:
- Response `book_id` rolls up to a book inside shelf 3.
- Response page name is NOT in the §4-CS-D.2 disqualifier list (defence
  in depth — catches a page that was reclassified between candidate
  enumeration and write).

#### 5-A.1 Destination content confirmation (per `release-filter-policy.md` §10.4 op 0)

The §4-CS-D score chose this page by **name / metadata / topic** signals.
Before writing, confirm at the **content** level that `PRIOR_HTML` is
actually about the same feature the scope concerns — compare the scope's
`scope_name`, screen references, and field names against the page's
existing ATC Feature cells, table contents, and headings:

- **Confirmed** when at least one holds: a same-key or synonym-folded
  Feature/Topic row already exists on the page (per the §4-CS-D.3 ATC /
  §5-C match rules); OR the scope's screen/field references already
  appear in the page's canonical tables; OR the page's subject
  (book / chapter / page name) is the unambiguous home for the feature.
  → proceed to STEP 5-B.
- **Not confirmed** — the page's content is about a different feature
  (the name/topic matched but the body diverges). Do NOT write this
  scope to this page. Demote the current top candidate and re-run the
  §4-CS-D.4 acceptance bands on the remaining candidates; if none clears,
  BLOCK the scope per §4-CS-D.5 with reason `destination page <id>
  content does not match scope "<scope_name>" — re-routed/blocked at
  content confirmation`. Record the demotion in
  `scope.candidate_destinations`.

This is the content-level safety net that the HT-1011 → page 554 episode
exposed: a high name-score is necessary but not sufficient — the page
body must corroborate the routing before any CRUD runs.

### 5-B. Locate (or initialise) the 5 canonical tables and the UI section

Identical to the agile flow:
- `ATC_TABLE` — 3 cols (`# | Feature | Scenario`).
- `LIST_TABLE` — 3 cols.
- `SEARCH_TABLE` — 5 cols.
- `FORM_TABLE` — 6 cols.
- `AUDIT_TABLE` — 3 cols.
- `UI_SECTION` — `<h2>User Interfaces (UIs)</h2>` at end of page.

If a table is absent and the scope needs it, create it at the canonical
position (before the UI section, in the canonical order ATC → List →
Search → Form → Audit Trail) per `WIKI_PAGE_RENDER.md` §2.

### 5-C. Map each scope to canonical rows

For each scope grouped at this destination:

1. **Match & idempotency** (universal contract — `release-filter-policy.md`
   §10.3 and the synonym-set tables it references):
   - **(a) Jira-key match (strict)** — scan `ATC_TABLE` for any row
     whose Feature cell carries `{issue_key}` in its parenthetical
     key list. On match → UPDATE in place.
   - **(b) Semantic Feature/Topic name match** — normalize the scope's
     intended Feature name (lowercase, strip key list, collapse
     whitespace) and compare against every existing row. Apply synonym
     folding (`Audit Trail` = `Audit Log` = `Audit History`, etc.). On
     match → UPDATE in place AND append `, {issue_key}` to the existing
     Feature-cell key list.
   - **(c) No match** — append a new row at the end of `ATC_TABLE` with
     Feature cell ending in ` ({issue_key})`.
   - **(d) Supersession (evidence-gated CRUD — `release-filter-policy.md`
     §10.4 op 4)** — when the issue **explicitly** states existing
     behaviour is gone (trigger phrasing: *removed, no longer,
     deprecated, discontinued, replaced by, renamed to, dropped,
     withdrawn, retired, superseded by*, mapping clearly to specific
     existing content): on the matched row, REMOVE the superseded
     `<li>`(s) from the Scenario cell, REPLACE a changed enumerated
     value, or — if the issue removes the **entire** feature — REMOVE the
     ATC row and cascade-remove every non-ATC row carrying its `(ATC #n)`
     then renumber. Rename-in-place for a renamed feature (never
     delete-and-recreate — preserves the key list). Log the matching
     `Removed - …` / `Updated - … <old> → <new>` line. **Mere omission by
     the issue removes nothing (absence ≠ removal).** This is the only
     path that deletes CS content.
     **Evidence sources for (d):** the trigger phrasing may appear in the
     Jira **description OR in a comment** (`release-filter-policy.md` §10.5
     bucket 2 — requirement/scope changes voiced in comments). A comment
     that changes a value drives an Update (op-3); a comment that drops a
     behaviour drives a removal (op-4). Cite the comment id / author /
     ≤160-char excerpt in the CRUD log line. Respect the §10.5 recency
     guard — a later comment that reverses the change wins.

2. **Compose the ATC row** (3 cells — canonical):
   - `#` — next sequential integer.
   - `Feature` — `<scope_name> (<issue_key>)` (or extended key list on
     match path (b)).
   - `Scenario` — bullet-form per
     `specification-writing-guideline.md` §2.2: `<ul><li>...</li>...</ul>`,
     one `<li>` per distinct test case / behavior point. UI strings,
     button labels, and tooltips kept in double quotes verbatim. NEVER
     a paragraph; NEVER multiple test cases in one `<li>`.

3. **Non-ATC tables — decide & compose** based on scope content:
   - LIST_TABLE if the scope describes a list view.
   - SEARCH_TABLE if it describes a search / filter field.
   - FORM_TABLE if it describes a form field (must be 6 cells:
     `Field Name | Type | Default Value | Validation(s) | Validation Message(s) | Field Behavior`).
   - AUDIT_TABLE if it describes an auditable action.

   Each non-ATC row's leftmost cell ends with ` (ATC #<n>)` linking to
   the owning ATC row, followed by the parenthetical key list. The
   per-table match cell is the leftmost named column (`Column Name` /
   `Field Name` / `Field Name` / `Action`).

4. **Empty-cell rule** — any free-text cell that has no content for a
   row MUST contain `—` (em-dash, U+2014). Never `<td></td>`.

5. **Form Note exception (`specification-writing-guideline.md` §2.4
   Form note)** — the Form `Validation(s)` and `Validation Message(s)`
   columns are the ONLY canonical-table cells that do NOT use
   `<ul><li>`. They use `-`-prefixed plain-text lines separated by
   `<br>` within the `<td>`. Form `Field Behavior` follows the bullet
   rule like every other free-text cell.

6. **Cross-table field completeness (`release-filter-policy.md §10.3` +
   `SKILL.md §5-C.4` — same algorithm)** — when a scope describes a
   field, that field must appear in every applicable canonical table.
   The routine adds the missing rows in the same run.

### 5-D. UI merge — extract → upload → compare → replace/add

Per `release-filter-policy.md` §11.1:

1. Extract image attachments + embedded image URLs from each scope's
   evidence. **Design-tool URLs (Figma / Sketch / etc.) are IGNORED per
   `release-filter-policy.md` §11.0 — never extracted, linked, or
   rendered.**
2. Re-host every Jira attachment binary on BookStack via the
   curl → multipart POST → delete-temp pipeline. **NEVER use the Read
   tool on the downloaded binary.** **NEVER link Atlassian URLs
   directly in `<img>`.**
3. Build `WIKI_UIS` map from existing `UI_SECTION`. For each new UI:
   ADD `<h6>{topic}</h6>` + `<a><img></a>` if not present; REPLACE
   `<a>`/`<img>` URLs if filename matches but URL differs; NO-OP if
   identical.
4. Topic name source priority per `release-filter-policy.md §11.1-ter`:
   description heading → bold/strong label → attachment filename
   title-cased → cleaned issue summary → `Untitled UI <n>` (with
   validation_warning).
5. The UI section is a **gallery-only** block. Forbidden inside it:
   `<p>` of ANY kind (including any Design References / Figma / Sketch
   sub-block — globally excluded per §11.0), `<ul>`, `<ol>`, `<li>`,
   `<table>`, any heading level other than `<h6>`, narrative connective
   text. See `release-filter-policy.md §11.0 / §11.1-bis`.

### 5-E. Assemble `NEW_HTML` per destination

Each touched destination produces one `NEW_HTML`. If
`NEW_HTML == PRIOR_HTML` (byte-equal after whitespace normalization)
for a destination, that destination's outcome is `NO_CHANGE` and STEP 7
skips it.

---

## STEP 6 — Validation (STRICT CANONICAL — per destination + CS additions)

Run **all** of the following checks against each `NEW_HTML`. Any FAIL
on any destination blocks that destination's write (other destinations
that pass are still written).

**Inherited checks** (same as the 14 in SKILL.md STEP 6 — re-stated
here for completeness because CS does not load SKILL.md):

| # | Check | FAIL condition |
|---|---|---|
| 1 | Canonical table shapes | Tables match exactly ATC (3), List (3), Search (5), Form (6), Audit Trail (3). No extra tables, no extra columns. |
| 2 | ATC header order | `# \| Feature \| Scenario` in that order, no 4th cell. |
| 3 | Jira-key idempotency suffix | Every authored / updated ATC row's Feature cell ends in a parenthetical key list `(<KEY>)` or `(<KEY>, <KEY2>, ...)`. |
| 4 | ATC key uniqueness per destination | No Jira key appears in more than one ATC row's key list **on the same destination page** (a key may appear once on Leave's page and once on Attendance's page — that is the cross-product split). |
| 5 | Non-ATC tables link to ATC | Every authored non-ATC row's leftmost cell ends with `(ATC #<n>)`. |
| 6 | No invented headings | Routine authored ZERO `<h2>`/`<h3>`/`<h4>`/`<h5>` outside the single `<h2>User Interfaces (UIs)</h2>` and `<h6>` entries inside the UI section. **Forbidden headings (verbatim, this list overrides any general intuition):** `Overview`, `Business Requirement`, `Expected System Behavior`, `Rules / Validations`, `User Stories`, `Notes / Dependencies / Limitations`, `Customer Specific`, `CS Feature`, `CS-Specific`, `Release`, `Fix Version`, `Pilot`, `Change Log`, `Migration Notes`, `Implementation Notes`, internal project names, any `<h2>{fixVersion}</h2>`. |
| 7 | UI section position + shape | `<h2>User Interfaces (UIs)</h2>` is LAST in the page body. Its content is strictly `<h6>{topic}</h6>` immediately followed by `<a><img></a>` — no `<p>`/`<ul>`/`<ol>`/`<li>`/`<table>` of any kind. Any `Design References` / design-tool link is a FAIL and must be removed (globally excluded per `release-filter-policy.md` §11.0). Topic name ≤ 6 words, no sentence punctuation. |
| 8 | Form table sanity | Every Form-table data row has exactly **6 `<td>` cells** in the canonical order. Empty cells use `—`. NO `<img>` in any cell. NO `Save`/`Cancel` row. NO `<ul>`/`<ol>`/`<li>` in Validation(s) or Validation Message(s) cells — those use `-`-prefixed plain-text lines per the §2.4 Form note. |
| 9 | Structural preservation + evidence-gated CRUD (`release-filter-policy.md` §10.4) | Every `<h2>` / `<h3>` / `<h4>` / `<h5>` / `<h6>` text in `PRIOR_HTML` is still present in `NEW_HTML`, and no whole canonical table or the UI section was deleted (structural floor). Row / bullet / cell content MAY be removed or replaced — but ONLY via an evidence-gated §10.4 op-4 supersession the audit log records with a `Removed - …` / `Updated - … <old> → <new>` line citing the driving `HT-` key. FAIL if a heading/table/UI-section disappeared, OR if any row/bullet/cell was removed/replaced with no matching evidence-gated log line (silent shrink). |
| 9-ORPH | No orphaned ATC back-references after removal | After any §10.4 row-level removal, every `(ATC #<n>)` in every non-ATC row still points at an existing ATC `#` in `NEW_HTML`, and ATC `#`s are contiguous from 1. FAIL on a dangling reference or numbering gap. |
| 10 | No change markers | No yellow tints, `[New — KEY]`, `[Updated — KEY]`, diff-class spans in authored content. |
| 11 | Idempotency | Running STEP 5 a second time against `NEW_HTML` produces byte-identical output. |
| 12 | Semantic ATC uniqueness per destination | No two ATC rows on the same destination share a normalized Feature/Topic name (synonym-folded). |
| 13 | Semantic non-ATC uniqueness per destination | Same per-table on List (`Column Name`), Search (`Field Name`), Form (`Field Name`), Audit Trail (`Action`). |
| 14 | Bullet-form contract | Every free-text cell across all 5 canonical tables uses `<ul><li>` (one bullet per distinct point). Exceptions: Form `Validation(s)` and `Validation Message(s)` only — those use `-`-prefixed plain-text lines. |

**CS-specific additions** (always run, in addition to checks 1–14):

| # | Check | FAIL condition |
|---|---|---|
| CS-1 | Destination in Specification shelf | Every accepted `selected_destination.page_id` was reached via shelf 3 (`book_id` in `LIVE_SPEC_BOOKS`). FAIL on any destination outside shelf 3. |
| CS-2 | Destination confidence | `selected_destination.confidence >= 80` OR (`>= 60` AND ≥ 25 points above the second-best candidate). FAIL otherwise (the scope should have been blocked at STEP 4-CS-D). |
| CS-3 | No CS-only sections authored | The authored content contains no `<h2>`/`<h3>`/`<h4>` titled `Customer Specific`, `CS Feature`, `CS-Specific`, `Special Behavior`, `CS Implementation`, `Customer-Only`, or any synonym. CS-feature spec content lives inside the canonical 5 tables and the global UI gallery — never under a CS-only heading. |
| CS-4 | No release/fixVersion as page content | The fixVersion string (`RELEASE_SCOPE`) MUST NOT appear as a heading or as a column header anywhere in `NEW_HTML`. fixVersion is a routine input, never page content. |
| CS-5 | No screenshots inside table cells | No `<img>` inside any `<td>` of the 5 canonical tables. (Inherited check 8 covers Form specifically; CS-5 enforces it across all 5 tables for clarity.) |
| CS-6 | Same Jira key not duplicated across ATC rows on the SAME destination | A CS issue split into multiple scopes that resolve to the same destination must collapse into ONE ATC row at that destination (via semantic match) — never two ATC rows on the same page carrying the same key. (Multiple ATC rows on DIFFERENT destinations are allowed and expected — that is the cross-product split.) |
| CS-7 | Project-lock honoured at JQL emit | Every JQL the routine emitted at STEP 3-C and STEP 3-D contains the literal substring `project = HT`. FAIL if any emitted JQL has a different `project = ...` clause (even if it happens to also be `HT` via substitution — the check is on the literal source, not the resolved value). This guards against a future code change that accidentally re-introduces `project = <JIRA_PROJECT_KEY>` substitution. |
| CS-8 | No Jira key from outside HT in canonical content | Every Jira key authored in any canonical-table cell on `NEW_HTML` matches `^HT-\d+$`. FAIL if a key from any other project (e.g. `CM-`, `PNP-`, `RV-`, `ROS-`) appears in CS-authored content. This is final defence-in-depth: even if upstream filters were bypassed, no non-HT key can land in a CS-authored row. (Inherited rows that already carry non-HT keys from prior runs are preserved — the check applies to keys this run added or updated, not legacy content.) |
| CS-9 | Destination content confirmed before write (`release-filter-policy.md` §10.4 op 0 / §5-A.1) | Every accepted `selected_destination` passed the STEP 5-A.1 content-confirmation gate — `PRIOR_HTML` corroborates the scope (existing matching row, OR scope screen/field references present, OR page subject is the unambiguous home). FAIL (and the scope must have been re-routed or blocked) if a destination was written on name/topic score alone while its body was about a different feature. |
| CS-10 | Comment intelligence ran (`release-filter-policy.md` §10.5) | The audit log records `comments_scanned` for every eligible issue (Stories, Tasks, promoted requirement-defect Bugs), and any deprioritization exclusion (bucket 3) or comment-driven scope change (bucket 2) cites the qualifying comment id / author / excerpt. FAIL if an eligible issue's comments were not scanned, or if a comment-driven removal/replacement landed in `NEW_HTML` without a citing log line (ties into check #9 — every removal needs evidence). |
| NAV-1 | Nav-tree sync ran | The audit log contains a `## STEP 2.7 — Nav-Tree Sync (CS)` section AND `specification_nav_tree.last_synced_at` was updated to a timestamp ≥ run start. FAIL if missing (per `release-filter-policy.md` §16.6). |
| NAV-2 | Nav-tree consistency for destinations | Every accepted `selected_destination.page_id` AND every `known_destinations[<i>].page_id` (where non-zero) corresponds to an `id` in `specification_nav_tree` with `deprecated_at == null`. FAIL surfaces as a manual_action (operator must refresh `routine_destinations` / `known_destinations` mapping) — the run continues. |
| CHANGELOG-1 | Per-run Excel changelog updated (`release-filter-policy.md §17`) | The audit log contains a `## STEP 9 — Changelog` section with a `CHANGELOG-OK` / `CHANGELOG-SKIP` line; on a real run that changed content, `logs/changelog/wiki_sync_changelog.xlsx` is in the STEP 9 commit. `CHANGELOG-SKIP` is a soft pass (run not failed) but surfaces as a `manual_action`. |

If any check FAILs on a destination, set that destination's status to
`FAILED` with the verbatim reason. Other destinations that pass STEP 6
still proceed to STEP 7. The run's overall status is `SUCCESS` if any
destination wrote successfully and none failed validation; `BLOCKED` if
every destination was blocked at STEP 4-CS-D; `FAILED` if any
destination failed STEP 6 validation.

---

## STEP 7 — Diff-aware write (per destination, fan-out)

**Dry-run check (first action of STEP 7):** if `DRY_RUN_MODE=1`, skip
all writes. Record per-destination
`Note - DRY_RUN=true; skipped BookStack PUT for page <id>; NEW_HTML
preserved in memory for log artefact only.` Continue to STEP 8 / 9 / 10.

For real runs:

For each destination that passed STEP 6:

1. **Pre-flight GET** — re-fetch the page; refuse if
   `updated_at != PRIOR_REV` (concurrent edit). On 409 / 412 retry once
   after re-reading. For transient 5xx / network errors, follow the
   HTTP retry policy (3 attempts, exponential backoff, max 30s
   cumulative wait).
2. **Verify shelf membership** — re-confirm the page's `book_id` is in
   `LIVE_SPEC_BOOKS`. Refuse the write on mismatch.
3. **`PUT /api/pages/<destination.page_id>`** with body
   `{"name":"<page_name>","html":"<NEW_HTML>"}`.

**One PUT per touched destination.** A single fire may PUT multiple
pages (typical for cross-product CS features). No POST under STEP 7 —
POST belongs only to a STEP 5C create-flow, and the CS routine does
**NOT** create pages (CS destinations must already exist; if none of
the candidates score high enough, the scope is BLOCKED — the routine
never invents a new CS spec page).

---

## STEP 8 — AUDIT SUMMARY block

```
==================== AUDIT SUMMARY (CS) ====================
Routine            : cs_features_daily_sync
Routine type       : cs_feature
Run UTC            : <ISO8601 UTC fire time>
Run local          : <Asia/Colombo localized>
Mode               : repo-aware (CS) (git <short hash>)
Credentials        : from-env (lengths only — no values)
Jira project       : <JIRA_PROJECT_KEY>
fixVersion         : <RELEASE_SCOPE>
fixVersion.released: <true|false>
fixVersion.releaseDate: <YYYY-MM-DD or empty>
Release gate       : <CONFIRMED|NOT_YET|BLOCKED — verbatim policy log line>
CS JQL             : project = <KEY> AND fixVersion = "<V>" AND ( <CS_JQL_FILTER> )
Issues checked     : <N>
Issues eligible    : <N>
Scopes identified  : <S>
Scopes routed      : <R>
Scopes blocked     : <SB>  (destination ambiguous / no candidate ≥ 60)
Destinations touched: <D>  (distinct page_ids written this run)
Pages updated      : <U>
Pages no-change    : <NC>
Pages failed       : <F>   (STEP 6 validation failures)
Manual actions     : <0 or comma-separated Jira keys>
Status             : <SUCCESS|NO_CHANGE|SKIPPED|BLOCKED|FAILED>
Email send         : <SENT|PARTIAL|FAILED|SKIPPED  N_OK/N_TOTAL>
GitHub log         : <log_html_url or empty>
=============================================================
```

---

## STEP 9 — GitHub audit log

Skip silently if `GITHUB_TOKEN` is unset.

Commit one file per run to
`logs/cs_features_daily_sync/<UTC_TIMESTAMP>.md` via the GitHub
Contents API. Timestamp format `YYYY-MM-DDTHHMMSSZ` (canonical — same
as agile routines).

**STEP 9 also updates the shared changelog (mandatory — `release-filter-policy.md §17`).**
The changelog is canonical on **`main`** (CSV ledger `logs/changelog/changelog.csv`
+ rendered `wiki_sync_changelog.xlsx`). Pull the current `main` `changelog.csv`,
build the payload JSON (schema atop `routines/update_changelog.py`;
`project` = `"CS Features (HT)"`) from this run's per-scope CRUD (CRUD op,
before/after content, outcome, routing confidence, any §10.5 comment evidence),
run `python routines/update_changelog.py <payload.json>`, then commit **BOTH
files to `main`** via the GitHub Contents API (`branch=main`, current sha +
retry on conflict — §17.0), **even if this run's `.md` log commits to a
different branch**. Record the helper's `CHANGELOG-OK` / `CHANGELOG-SKIP` line
under a `## STEP 9 — Changelog` section. A NO_CHANGE / SKIPPED / BLOCKED run
still writes one summary row. Validated by STEP 6 check `CHANGELOG-1`.

YAML frontmatter — CS-specific fields:

```yaml
---
routine: cs_features_daily_sync
routine_type: cs_feature
project_key: <JIRA_PROJECT_KEY>
fix_version: <RELEASE_SCOPE>
fix_version_released: <true|false>
fix_version_release_date: <YYYY-MM-DD or empty>
release_gate: <CONFIRMED|NOT_YET|BLOCKED>
release_gate_log: <verbatim policy log line>
run_utc: <ISO8601>
status: <SUCCESS|NO_CHANGE|SKIPPED|BLOCKED|FAILED>
dry_run: <true|false>
cs_jql: 'project = <KEY> AND fixVersion = "<V>" AND ( <CS_JQL_FILTER> )'

# Discovery counts
total_issues_found: <N>
epics_found: <N>
stories_found: <N>
stories_processed: <N>
tasks_found: <N>
tasks_processed: <N>
bugs_found: <N>
bugs_requirement_processed: <N>   # Bugs promoted via the bug-requirement carve-out (STEP 4 bucket 1)
subtasks_found: <N>
other_found: <N>

# Comment intelligence (release-filter-policy.md §10.5)
comments_scanned: <N>                 # total non-bot comments read across eligible issues
issues_excluded_by_comment: <N>       # bucket 3 — deprioritized/de-scoped per latest comment
scope_changes_from_comments: <N>      # bucket 2 — comment-driven Update/Delete applied at STEP 5
comment_actions:                      # one entry per bucket-2 / bucket-3 action (empty list if none)
  - issue_key: <KEY>
    bucket: <2|3>
    comment_id: <id>
    author: <display name>
    date: <YYYY-MM-DD>
    excerpt: <"≤160-char excerpt">
    action: <"excluded" | "updated <table> row '<name>'" | "removed <table> row/bullet '<name>'">

# Per-Epic project scan (STEP 3-D)
epics_scanned: <N>
epics_released: <N>
epics_pending: <N>
epics_unassigned: <N>
epics_excluded: <N>
epic_scan_summary:
  - key: <KEY>
    name: <Jira summary>
    fix_versions: <"V1, V2" or "—">
    status: <Released|Pending|Unassigned|Excluded>
    symbol: <"✓"|"⚠"|"—"|"✗">

# CS-specific scope + destination breakdown
scopes_identified: <S>
scopes_routed: <R>
scopes_blocked: <SB>
destinations_touched: <D>
destination_decisions:
  - issue_key: <KEY>
    scope_name: <name>
    affected_area: <area>
    selected_destination:
      page_id: <id>
      page_name: <name>
      book_id: <id>
      book_name: <name>
      confidence: <score>
    top_candidates:           # top 3 in score order
      - page_id: <id>
        page_name: <name>
        score: <int>
        score_evidence: [...]
      - ...
      - ...

# Per-issue fan-out — EVERY destination touched on each Jira issue's
# behalf. Critical for multi-area CS features: one CS-42 ticket that
# affects Leave + Attendance produces ONE entry here with TWO
# destinations under it. This is the authoritative "what changed where
# for this ticket" record — spec authors and PLs read this first when
# auditing a fire. NEVER collapse to a single destination per issue;
# always render every page touched.
issue_fan_out:
  - issue_key: <KEY>
    issue_summary: <Jira summary verbatim>
    affected_areas: [<area1>, <area2>, ...]   # one per scope this issue produced
    destinations_touched: <N>                  # count of distinct pages this issue contributed to
    destinations:
      - page_id: <id>
        page_name: <name>
        book_name: <name>
        scope_names: [<scope1>, ...]           # scopes from this issue that landed here
        rows_added:
          atc: <N>           # new ATC rows added by this issue at this destination
          list: <N>
          search: <N>
          form: <N>
          audit_trail: <N>
        rows_updated:        # in-place row updates (per dedup contract §5-C step 1.a/1.b)
          atc: <N>
          list: <N>
          search: <N>
          form: <N>
          audit_trail: <N>
        ui_assets_added: <N>
        ui_assets_replaced: <N>
        outcome: <Updated|No Change|Failed|Blocked>
        change_summary: <"ATC #14, #15 added; Form +2 rows (Leave Type, Half Day); UI +1">

# Per-destination change map — single-page view, ordered by page_id.
# Same row-count data viewed from the OTHER axis (page → contributing
# issues) so a spec author can answer "what landed on the Leave page
# this run?" without scanning the per-issue fan-out.
destination_row_counts:
  - page_id: <id>
    page_name: <name>
    book_name: <name>
    contributing_issues: [<KEY>, <KEY>, ...]    # every CS issue that wrote here
    rows_added:
      atc: <N>
      list: <N>
      search: <N>
      form: <N>
      audit_trail: <N>
    rows_updated:
      atc: <N>
      list: <N>
      search: <N>
      form: <N>
      audit_trail: <N>
    ui_assets_added: <N>
    ui_assets_replaced: <N>
    outcome: <Updated|No Change|Failed>
    change_summary: <"ATC +2, Form +1, UI +3 — contributed by CS-42, CS-44">

# Outcome counts (per destination touched)
pages_updated: <U>
pages_no_change: <NC>
pages_failed: <F>

manual_actions: [<jira-keys>]
email_subject: "OHRM Wiki Sync — cs_features_daily_sync — <STATUS> — <YYYY-MM-DD>"
email_send_status: PENDING
log_html_url: ""
---

# OHRM Wiki Sync log — cs_features_daily_sync

- **Run UTC**: <ISO8601>
- **Project / fixVersion**: <KEY> / <V>  (<release_gate>)
- **CS JQL**: <jql>
- **Discovery**: <total> issues found — Stories <s_f>, Tasks <t_f>, Bugs <b_f>, Other <o_f>
- **Scopes**: identified <S> / routed <R> / blocked <SB>
- **Destinations**: <D> distinct pages touched (updated <U> / no-change <NC> / failed <F>)
- **Status**: <STATUS>

## Per-scope routing decisions

| Jira key | Scope | Affected area | Destination | Confidence | Outcome | Notes |
|---|---|---|---|---|---|---|

## CS feature fan-out (multi-area visibility)

**This table is the audit authority for cross-product CS features.** One
row per `(issue, destination)` pair. A CS-42 ticket that affects Leave
AND Attendance produces TWO rows here — one under CS-42 → Leave page,
one under CS-42 → Attendance page — so the spec author / PL can see
the complete fan-out at a glance. A single-area CS issue produces ONE
row. Rows are sorted by Jira key ascending; within a Jira key, by
`page_id` ascending.

| Jira key | Summary | Affected area | Wiki page | Book | Rows added (ATC/List/Search/Form/Audit) | Rows updated | UI added | UI replaced | Outcome |
|---|---|---|---|---|---|---|---|---|---|

## Destination change map (per-page roll-up)

Same data viewed from the other axis: one row per touched destination,
listing every CS issue that contributed. Use this to answer "what
landed on the Leave page this run?" without scanning the fan-out.

| Wiki page | Book | Contributing CS issues | Rows added (ATC/List/Search/Form/Audit) | Rows updated | UI added | UI replaced | Outcome |
|---|---|---|---|---|---|---|---|

## Per-page write results

| Page | Book | Scopes contributed | Status | Notes |
|---|---|---|---|---|

<!-- EMAIL_BODY_START -->
{rendered email body — see §10}
<!-- EMAIL_BODY_END -->
```

The email-rendering placeholders are inherited from
`resources/email_template.html` and `SKILL.md` §9-A through §9-G — CS
adds these additional placeholders:

- `{{csJql}}` — the CS-feature JQL fragment.
- `{{scopesIdentifiedCount}}`, `{{scopesRoutedCount}}`,
  `{{scopesBlockedCount}}`, `{{destinationsTouchedCount}}`.
- `{{routingRows}}` — one row per scope with destination + confidence
  + outcome. Rendered inside a section that appears between the
  Discovery counts and the Manual Actions section.

The `{{wikiPageName}}` / `{{wikiPageUrl}}` placeholders are overloaded
to a comma-separated list when multiple destinations are touched;
`SKILL.md`'s single-page assumption is relaxed for the CS routine only.

---

## STEP 10 — Send notification email (UNCONDITIONAL)

Invoke `python routines/send_notification.py <local_log_path>`. Same as
the agile routines — runs on every status (SUCCESS / NO_CHANGE /
SKIPPED / BLOCKED / FAILED), with `PENDING` as an invalid final state.

### 10.1 Mandatory email sections (CS-specific)

The CS email is the operator's primary visibility channel for
multi-area writes. The agile routines' single-destination layout is
insufficient — a CS-42 ticket touching Leave + Attendance must be
visible AS such, not collapsed to one row. The email MUST contain
these sections, in this order, populated from the STEP 9 YAML data:

1. **Discovery summary** — issues checked, eligible, scopes identified,
   scopes routed, scopes blocked, destinations touched. Standard
   summary-card block.

2. **CS Feature Fan-Out (REQUIRED — `{{fanOutRows}}`)** — one `<tr>`
   per `(issue, destination)` pair from `issue_fan_out[].destinations[]`.
   A multi-area CS issue produces N rows under the same Jira key;
   adjacent rows for the same Jira key are visually grouped (same
   light background, the Jira-key cell merged via `rowspan` or repeated
   with a `↳` indent for cross-client safety).

   Columns: `Jira key | Summary | Affected area | Wiki page | Book |
   Rows added | Rows updated | UI | Outcome`.

   "Rows added" and "Rows updated" render as a compact tuple
   `ATC <a>/List <l>/Search <s>/Form <f>/Audit <au>` — zero entries
   shown as `—` for visual scan. The Outcome cell uses the standard
   badge palette (Updated green / No Change gray / Failed red /
   Blocked red).

   This section is what makes the routine's tracking VISIBLE per
   the CS requirement. It MUST NOT be suppressed even on
   `NO_CHANGE` runs (a NO_CHANGE run shows every issue with all
   rows at zero — proving the routine found the destinations and
   determined nothing needed updating, not that it failed to look).

3. **Destination Change Map (REQUIRED — `{{changeMapRows}}`)** — one
   `<tr>` per touched destination, from `destination_row_counts[]`.
   Columns: `Wiki page | Book | Contributing CS issues | Rows added |
   Rows updated | UI | Outcome`. The "Contributing CS issues" cell
   is a comma-separated Jira-key list (each key linked to its Jira
   ticket URL).

4. **Per-issue results table (`{{storyRows}}`)** — inherited from the
   agile email layout, one row per processable CS Story / Task with
   the standard `jiraKey / storyName / statusLabel / reason /
   specFile / updatedSections / requiredAction` columns. For CS,
   `{{specFile}}` shows ALL destinations the issue touched
   (comma-separated `page_name`s), and `{{updatedSections}}` shows
   the aggregate row-count tuple across those destinations.

5. **Specification Files Updated (`{{githubFileRows}}`)** — one row
   per distinct touched destination. Inherited; renders only when
   `destinationsTouchedCount > 0`.

6. **Epic Release Status (`{{epicRows}}`)** — inherited per STEP 3-D
   / `release-filter-policy.md` §15. Conditional block — removed
   when `epicsScannedCount == 0`.

7. **Manual Actions Required (`{{manualActionRows}}`)** — inherited.
   Surfaces every BLOCKED entry with its verbatim policy log line:
   - Release-gate BLOCKED → verbatim §3 / §6 log line at the top.
   - §4-CS.4 ambiguous-multi-area BLOCKED → verbatim
     `Blocked - CS feature affects multiple product areas but Jira
     does not provide enough scope separation to safely update wiki
     pages.` per blocked Jira key.
   - §4-CS-D.5 destination BLOCKED → verbatim
     `Blocked - Could not identify a safe wiki destination for
     <KEY> scope "<scope_name>". Manual destination mapping required.`
     per blocked scope, with the top-3 candidate evidence inline so
     the operator can manually route.

### 10.2 Multi-destination overload of inherited placeholders

The CS routine relaxes two single-destination assumptions inherited
from the agile email contract:

- **`{{wikiPageName}}`** — comma-separated list of every touched
  `page_name` (e.g. `Leave, Attendance, Employee Profile`) when
  `destinationsTouchedCount > 1`. Single value when exactly one
  destination is touched.
- **`{{wikiPageUrl}}`** — comma-separated list of every touched page's
  BookStack URL, in the same order as `{{wikiPageName}}`. Single URL
  when exactly one destination is touched.

The agile placeholders that count things (`{{updatedCount}}`,
`{{noChangeCount}}`, `{{skippedCount}}`, `{{blockedCount}}`) continue
to count Jira ISSUES, not destinations. CS adds parallel counters
(`{{destinationsTouchedCount}}`, `{{pagesUpdatedCount}}`,
`{{pagesNoChangeCount}}`, `{{pagesFailedCount}}`) for the
destination-axis view.

### 10.3 What MUST be visible on every fire

These are non-negotiable visibility guarantees — the routine MUST
emit all of them on every fire that reaches STEP 10, even on
NO_CHANGE / SKIPPED / BLOCKED outcomes:

- For every CS issue processed: **every destination it touched**
  (no collapsing — multi-area features render multi-row).
- For every destination touched: **every CS issue that contributed**
  (cross-reference visible from both axes).
- For every blocked scope: **the top-3 candidate destinations and their
  score evidence** (so an operator can route manually without
  re-running discovery).
- For every blocked release-gate / ambiguous-multi-area / no-safe-
  destination: **the verbatim policy log line** under Manual Actions
  Required (no paraphrasing — operators rely on the exact wording for
  ticket templates and Jira automations).

A run that suppresses any of these counts as a STEP 10 failure —
record `email_send_status: FAILED reason='mandatory CS visibility
section missing: <name>'` and treat as a manual-action item for the
next fire.

---

## STEP 11 — Final banner

Print `VOILA! JOB DONE.` on `status=SUCCESS` or `status=NO_CHANGE`
only. Never on SKIPPED / BLOCKED / FAILED.

```
========================================
            VOILA! JOB DONE.
========================================
Routine : cs_features_daily_sync
Status  : <SUCCESS|NO_CHANGE>
Dest.   : <D> pages written
Email   : <SENT N_OK/N_TOTAL>
Log     : <log_html_url>
========================================
```

---

## Safety rails

- **Refuse any write whose pre-flight check fails.** Set `status=FAILED`.
- Every PUT must pre-flight with a GET and re-verify shelf 3 membership.
- **NEVER use wiki / BookStack / wiki catalogs to determine release
  status.** Release confirmation is Jira-only per
  `release-filter-policy.md`.
- **NEVER write to a page outside Specification shelf id=3.**
- **NEVER create a new BookStack page.** The CS routine has no
  STEP 5C create-flow — if no destination scores high enough, the
  scope is BLOCKED and an operator routes it manually.
- **NEVER mutate `wiki_destination.json`.** CS has no first-fire
  bootstrap. The routine reads its own slug entry but does not write
  to it.
- **NEVER mutate any other resource file.**
- **NEVER modify or load `SKILL.md`.** CS authority does not include
  it; behavior must remain isolated from the agile routines.
- **NEVER print** `WIKI_TOKEN_ID`, `WIKI_TOKEN_SECRET`, `GITHUB_TOKEN`,
  `RESEND_API_KEY`, or the AUTH header value.
- **HTTP retry policy** — identical to the agile routines (idempotent
  GETs + PUTs retryable up to 3 attempts with exponential backoff; 4xx
  responses non-retryable; POST `/api/pages` non-retryable but CS
  doesn't use it).

---

## Allowed writes

**BookStack** (only inside `SPECS_SHELF_ID = 3`):
- `PUT  /api/pages/<destination.page_id>` — STEP 7, ONE PUT per
  touched destination.

The CS routine is NOT allowed to:
- `POST /api/books`
- `PUT  /api/shelves/3`
- `POST /api/chapters`
- `POST /api/pages`
- Any write outside shelf id=3.

**GitHub** (STEP 9 only):
- `PUT /repos/devnith-git/ohrm-wiki-sync/contents/logs/cs_features_daily_sync/<ts>.md`

The CS routine is NOT allowed to `PUT` to `resources/wiki_destination.json`
or any other file in `resources/`.

**Resend HTTPS API** (STEP 10 only):
- N HTTPS POSTs to `https://api.resend.com/emails`, each with
  `Authorization: Bearer <RESEND_API_KEY>`.

Every other write MUST be refused before the request leaves the agent.

---

## Common mistakes (do NOT do)

- Treating the CS routine's `page_id: 0` / `book_id: 0` as a sentinel
  for FIRST-FIRE BOOTSTRAP (it is NOT — CS deliberately has no fixed
  destination; the zeros mean "discover per scope at fire time").
- Falling back to `GET /api/books` at the wiki root to enumerate
  destinations. ONLY `GET /api/shelves/3` (and the per-book reads it
  drives) are allowed.
- Inventing a `Customer Specific` / `CS Feature` heading on the
  destination page. CS content lives in the canonical 5 tables and
  the global UI gallery — exactly the same shape as agile content.
- Splitting one CS issue across multiple ATC rows on the SAME
  destination just because the scope split produced two scopes that
  resolved to the same page. Same-destination scopes from one issue
  collapse to ONE ATC row at that destination (semantic match).
- Splitting a CS issue across multiple destinations when the
  description doesn't justify it. Use the §4-CS.2 triggers strictly —
  when in doubt, single-scope is safer than multi-scope, and a
  multi-area-but-unsplittable issue must be BLOCKED with the §4-CS.4
  verbatim line rather than guessed.
- Accepting a destination whose top candidate scored < 80 without
  verifying the ≥ 25-point gap to the runner-up. Confidence is the
  guardrail against quietly writing CS spec content to the wrong
  product area.
- Authoring a `Release` / `Fix Version` / `Status` / `Owner` /
  `Notes` column on any canonical table. The 5 canonical shapes are
  STRICT (ATC 3, List 3, Search 5, Form 6, Audit Trail 3).
- Using the agile routines' fixed-destination assumption — every CS
  fire potentially fans out to N destinations, and every destination
  is computed fresh from the live shelf, never cached across runs.
- Writing to `wiki_destination.json` mid-fire. CS has no self-commit
  step.

---

## Authority recap

```
release-filter-policy.md                  ← TOP
specification-writing-guideline.md
CS_FEATURE_ROUTING_SKILL.md               ← this file (CS only)
WIKI_PAGE_RENDER.md
routines/cs_features_daily_sync.prompt.md
```

When in doubt, re-read top of stack.
