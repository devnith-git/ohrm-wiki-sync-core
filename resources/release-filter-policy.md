# Global Release Filtering Rule for All Jira-Based Specification Routines

> **AUTHORITY:** This file is the **top of the authority order** for every
> routine in this repo. When it disagrees with `specification-writing-guideline.md`,
> `SKILL.md`, `WIKI_PAGE_RENDER.md`, or any per-routine slim prompt, this file
> wins. Routines must read this file first at STEP 2 (repo-aware bootstrap)
> and abort `status=BLOCKED reason='resources/ unreachable'` if it is missing.

Apply this rule to every project routine, including CM, PNP, Roster,
Performance, Leave, Attendance, and any other Jira project.

The routine must use **Jira only** to determine whether a story is eligible
for specification update.

**Do not use:**
- Wiki
- BookStack
- Wiki catalog
- Wiki release dates
- Wiki MCP
- Any external release confirmation source

Do not execute any wiki-related validation or fallback logic for the purpose
of determining release status. (Reading existing wiki page bodies to compose
write payloads or to diff prior page state remains permitted — the
prohibition is specifically on using wiki/BookStack to decide *whether* a
story is released.)

---

## 1. Configured Fix-Version Scope

Each routine must have a configured Jira `fixVersion` scope.

Examples (current production values):
- CM routine     → configured `fixVersion`: **8.0**
- PNP routine    → configured `fixVersion`: **8.0.2**
- Roster routine → configured `fixVersion`: **8.1**

The routine must only check Jira stories linked to its configured
`fixVersion`. If a story is not linked to the configured `fixVersion`,
skip it.

**Log:**
```
Skipped - Story is outside the configured fixVersion scope.
```

The configured `fixVersion` lives in `resources/wiki_destination.json` under
the routine's `routine_destinations.<routine_name>.release_scope` field.

---

## 2. Jira Release Confirmation

A configured `fixVersion` should be treated as released only if Jira
confirms it using one of the following conditions:

- `fixVersion.released == true`

  **OR**

- `fixVersion.releaseDate` is today or in the past

Use the current date based on the **routine execution timezone**
(Asia/Colombo for OHRM routines today).

---

## 3. Not Confirmed Release

If the configured `fixVersion` has:
- `released: false`
- AND `releaseDate`: empty / null / missing

Then the routine must treat that `fixVersion` as **not confirmed for
release**. Do not process any stories under that `fixVersion`.

**Log (status=BLOCKED):**
```
Blocked - Configured fixVersion [VERSION] for project [PROJECT_KEY] is not
confirmed as released in Jira because released=false and releaseDate is
empty. Release Manager or Project Admin must either mark the version as
released or set a valid releaseDate in Jira.
```

---

## 4. Future Release Date

If the configured `fixVersion` has:
- `released: false`
- AND `releaseDate` is in the future

Then the routine must treat that `fixVersion` as **not released yet**.
Do not process any stories under that `fixVersion`.

**Log (status=SKIPPED):**
```
Skipped - Configured fixVersion [VERSION] for project [PROJECT_KEY] is not
released yet because Jira releaseDate is in the future.
```

---

## 5. Released Flag True

If the configured `fixVersion` has `released: true`, the routine can
process completed stories under that `fixVersion`.

**Log:**
```
Release confirmed - Jira fixVersion [VERSION] for project [PROJECT_KEY] is
marked as released.
```

---

## 6. Past Release Date

If the configured `fixVersion` has:
- `released: false`
- AND `releaseDate` is today or in the past

Then the routine can treat the version as released and process completed
stories under that `fixVersion`.

**Log:**
```
Release confirmed - Jira fixVersion [VERSION] for project [PROJECT_KEY] has
a releaseDate in the past or today.
```

---

## 7. Story Completion Check

Even if the `fixVersion` is confirmed as released, the routine must
process only **completed** stories.

A story is eligible only if it is in a completed status such as:
- Done
- Closed
- Completed
- Released

Or if the Jira `statusCategory.key == "done"`.

If the story is not completed, skip it.

**Log (per-story):**
```
Skipped - Story is linked to a released fixVersion, but the story itself
is not completed.
```

---

## 8. Issue-Type Filter

Spec coverage is **issue-type-scoped**. The routine processes only the
types that represent a deliverable specifiable unit:

| Issue type | Processed? | Counted in run log? |
|---|---|---|
| **Epic** | ❌ no — Epics are containers, not specifiable units. The routine walks the Epic for its child stories; the child stories' content goes into the ATC table. Never write a row for the Epic itself. | ✅ |
| **Story** | ✅ yes — feature spec content | ✅ |
| **Task** | ✅ yes — work-item content | ✅ |
| **Bug** | ❌ no — bugs document defects, not spec | ✅ |
| **Sub-task** | ❌ no — content folds into parent story | ✅ |
| **Improvement** | ❌ no — folds into the affected feature's section | ✅ |
| **Refactor / Spike / other** | ❌ no — engineering work, not specifiable | ✅ |

For every issue returned by the fixVersion query, the routine
classifies it into one of three buckets:

- **processed** — Epic / Story / Task. Sub-section content is added or
  updated on the wiki page per §10.
- **excluded by issue type** — Bug / Sub-task / Improvement / Refactor /
  Spike / etc. Counted in the run log and email status bar (so the
  Release Manager sees what was found) but NO wiki content is written
  for these.
- **excluded by scope filter** — fails completion (§7) or exclusion
  (§9) checks. Counted as skipped/blocked with the verbatim log line.

**Log (per issue excluded by issue type):**
```
Excluded - <KEY> is a <Type>; issue type not in spec coverage scope.
```

## 9. Exclusion Check (resolution / status / labels)

For any issue that passed §8 (Epic/Story/Task), still skip it if it is
marked as:
- Deferred
- Cancelled
- Rejected
- Removed from scope
- Duplicate
- Won't Do
- Moved to a future release
- Not applicable

Check `resolution.name`, `status.name`, and `labels[]` for any of the
above tokens (case-insensitive substring match against the canonical
list: `deferred`, `cancelled`, `rejected`, `removed-from-scope`, `dropped`,
`duplicate`, `wont-do`, `won't do`, `moved`, `not-applicable`, `na`).

If any of these apply, skip the story.

**Log (per-story):**
```
Skipped - Story is excluded from release scope.
```

---

## 9-bis. Expected Processing Logic

The routine should process an issue only when **all** of the following
are true:

1. The issue belongs to the configured Jira `fixVersion`.
2. Jira confirms the `fixVersion` as released using `released==true` or
   `releaseDate` today/in the past.
3. The issue type is in scope (per §8: Epic / Story / Task).
4. The issue is completed (`statusCategory.key == "done"` or a
   completed status name).
5. The issue is not excluded from scope by resolution / status / labels
   (per §9).
6. The issue has enough Jira information to update the specification
   (description is not empty AND not solely an external Drive/Figma link).

---

## 10. Specification Page Update (BookStack target)

**The page structure is strictly defined by `specification-writing-guideline.md`.**
This file does NOT prescribe a section schema — it delegates entirely to
the canonical guideline. The routine MUST NOT invent new section types,
new table types, new column counts, or new heading hierarchies. If the
canonical guideline doesn't have it, the routine doesn't author it.

If the story is eligible:

- Read the latest specification page from BookStack (the routine's
  destination page, picked from `routine_destinations.<routine>.page_id`
  in `wiki_destination.json`).
- Map Jira content onto the **5 canonical tables** described by
  `specification-writing-guideline.md` §2.4 — each table is rendered
  **exactly at its canonical column count**. The routine adds rows; it
  does NOT add columns:
  - **Acceptance Test Cases** — 3 canonical columns: `#`, `Feature`,
    `Scenario`. Every eligible story contributes at least one row.
    `Feature` ends with a parenthetical Jira-key list — `(<KEY>)` for
    a single contributor or `(<KEY>, <KEY2>, ...)` when several stories
    contributed to the same feature (per the §10.3 de-duplication
    contract). fixVersion is NOT represented on the page (no extra
    Release column, no `<h2>{fixVersion}</h2>` header) — Jira is the
    single source of truth for which fixVersion a story shipped in.
  - **List** — append rows when the Jira story describes a list view
    addition / change.
  - **Search** — append rows when the Jira story describes search /
    filter fields.
  - **Form** — append rows when the Jira story describes form fields
    or validations.
  - **Audit Trail** — append rows when the Jira story describes
    auditable actions.
- Use the Jira **issue key** (e.g. `CM-31`, `PNP-37`) as the primary
  identifier for idempotency. The Feature / Action / Field-Name cell
  carries a **parenthetical key list** — `(CM-2)` when one story owns
  the row, `(CM-100, CM-200)` when several stories contributed to the
  same feature. Match existing rows first by Jira key (any key in the
  list matches), then by semantic Feature/Topic name per §10.3.
- Preserve existing manually written content unless Jira clearly
  provides a newer released update — additive **by default**, but a run
  may UPDATE or REMOVE existing content when the eligible issue gives
  explicit evidence the prior behaviour is superseded or gone, per the
  **§10.4 CRUD reconciliation contract**. Rows written by prior runs are
  never removed on mere omission (absence ≠ removal); they are removed or
  replaced only on explicit Jira evidence, and the change is logged.
- **Forbidden:** new section types (`Overview`, `Business Requirement`,
  `Expected System Behavior`, `Rules / Validations`, `User Stories`,
  `Notes / Dependencies / Limitations`, etc.), new tables outside the
  canonical 5, ANY column-count deviation from the canonical shapes
  (no extra `Release` / `Status` / `Owner` / `Notes` columns),
  narrative paragraphs as section bodies, `<h2>{fixVersion}</h2>`
  release organizers, change markers (yellow tints, `[New — KEY]`
  spans).

### 10.1 ATC table — 3 columns, canonical

The ATC table is exactly the canonical shape:

| # | Feature | Scenario |
|---|---|---|

`#` is sequential across the whole table (1, 2, 3, …) — never reset.
`Feature` ends with a **parenthetical Jira-key list** — `(<KEY>)` for
a single contributor or `(<KEY>, <KEY2>, ...)` when several stories
contributed to the same feature (per the §10.3 de-duplication contract).
Example: `Pay Grade Soft Delete (CM-2)` or `Audit Trail (CM-100, CM-200)`.

`Scenario` is a **bulleted list** in present tense — one `<li>` per
distinct test case / released-behavior point, per
`specification-writing-guideline.md` §2.2. The cell is always shaped as
`<ul><li>...</li><li>...</li></ul>`, even when the feature has a single
test case. UI strings, button labels, and tooltips are kept in double
quotes verbatim inside each bullet. See `SKILL.md` §5-C.2 for the
bullet-level merge rule (preserves earlier-confirmed coverage on
re-runs; never silently shrinks the list).

**fixVersion is NOT on the wiki page** — not as a column, not as a
heading, not anywhere. Jira owns the question "which release did this
ship in"; the wiki page is the current spec. The routine still uses
fixVersion at runtime to filter which stories to process (per §1–§9),
but that's a routine-input filter, not page content.

### 10.2 Other tables — link to ATC by `#`

`List`, `Search`, `Form`, and `Audit Trail` tables stay at their
canonical column count (3 / 5 / 6 / 3 respectively). Each non-ATC row
references its ATC entry by including the ATC `#` in a parenthetical
suffix on the leftmost cell (e.g. a Form row's Field Name cell ending
in `(ATC #4)`).

This satisfies canonical §2.4: *"Any table added, apart from the
Acceptance Test Cases table, must be linked to an entry within the
Acceptance Test Cases table."*

### 10.3 De-duplication contract — match by Jira key OR by semantic Feature/Topic name

**Universal — applies to every canonical table on every routine.**

Each row in each canonical table represents ONE feature / topic / field /
action. The routine MUST NOT create duplicate rows for the same item.
This contract is the policy-level statement; the implementation lives in
`SKILL.md` §5-C.1 (synonym set) / §5-C.2 (scenario merge rule) /
§5-C.3 (non-ATC application) / §5-C.4 (cross-table completeness), and
is enforced by STEP 6 validation checks #12 / #13 / #14.

**Match order — the first match wins, and the issue's contribution
merges into the matched row:**

1. **Jira-key match (strict)** — the leftmost named cell's parenthetical
   key list contains the issue's Jira key. Per §10.1 / §10.2, a row may
   carry multiple keys (e.g. `Audit Trail (CM-100, CM-200)`) when
   multiple stories contributed to the same feature.

2. **Semantic Feature/Topic name match** — if (1) does not match,
   normalize the issue's intended Feature/Topic name (trim, lowercase,
   strip the parenthetical key list, collapse internal whitespace) and
   compare against every existing row's leftmost-cell name normalized
   the same way. Match if names are equal after normalization OR if
   both belong to the same synonym group per `SKILL.md` §5-C.1.

   Canonical examples of synonyms that MUST collapse to one row (not
   exhaustive — see `SKILL.md` §5-C.1):

   | Canonical name | Synonyms folded into the same row |
   |---|---|
   | Audit Trail | Audit Log, Audit History, Activity Log, Change History |
   | Pay Grade | Salary Grade, Compensation Grade |
   | Search | Filter, Filters, Search & Filter |
   | List View | Grid View, Table View |
   | User Interfaces (UIs) | UI, Screens, User Interface (singular) |

   Treat as separate rows ONLY when the specification clearly treats
   two names as separate features (e.g. distinct scopes within the
   same project). When in doubt, prefer merging — splitting is harder
   to reverse than merging.

**On match — UPDATE the row in place:**

- For free-text cells (`Scenario`, `Description`, `Field Behavior`,
  `How it is tracked in Audit Trail`, `Validation Message(s)`): merge
  per the `SKILL.md` §5-C.2 scenario-merge rule. The merged content
  reflects the **latest released behavior** while **preserving
  existing valid test coverage** — never drop sentences from the
  prior content just because the current Jira description omits them.
- For enumerated cells (`Type`, `Sort-able?`, `Default Value`,
  `Available Options`, `Validation(s)`): the latest Jira value wins.
  If it conflicts with the existing value, log
  `Updated - <table> row <name>: <field> changed: <old> → <new>` and
  apply the change.
- Append the new Jira key to the leftmost cell's parenthetical key
  list (so future runs match by Jira-key on rule 1).

**On no match — append a new row** per the canonical column shape
(`WIKI_PAGE_RENDER.md` §2). The leftmost cell ends with the issue's
Jira key in the parenthetical key list.

**Cross-table field completeness (universal):** when a Jira issue
mentions a field by name, that field MUST appear in every applicable
canonical table — Search if the issue describes filtering/search on
it, Form if it appears in an add/edit form, Audit Trail if its
create/update/delete is audited, List if it appears as a list-view
column. If the field is described by Jira but missing from an
applicable table, the routine adds the row in this same run. See
`SKILL.md` §5-C.4 for the implementation.

**Final-validation requirement (STEP 6):** before STEP 7 writes, the
routine MUST confirm — across every canonical table on the page —
that (a) no duplicate Feature / Topic / Field / Action rows exist
after dedup, (b) existing rows were updated where applicable, (c)
new rows were added only for genuinely new items, (d) every Scenario
/ Description / Field Behavior cell reflects the latest released
behavior. Failure of any check blocks the write per STEP 6.

### 10.4 CRUD reconciliation contract — confirm destination, then Create / Read / Update / Delete correctly

**Universal — applies to every canonical table on every routine (CM,
PNP, Roster, Orange Sign, CS-feature routing, and every current or
future Jira-to-wiki routine). This subsection is the authority for what
content a run may add, change, or remove.**

The merge is no longer "additive-only." A run reconciles the destination
page against the **latest released behaviour described by the eligible
Jira issue(s)** using four operations. Two of them — Update-replace and
Delete — change or remove existing content, so they are
**evidence-gated**: they fire only on explicit Jira evidence, never on
inference or on omission. The governing principle is:

> **Absence ≠ removal, but explicit supersession ⇒ removal/replacement.**
> A story that merely omits an existing behaviour removes nothing. A
> story that explicitly states a behaviour is gone, replaced, or renamed
> drives the corresponding removal/replacement — and the change is logged.

**0 — Read & confirm destination (precondition for any write).** Before
composing any change, read the destination page body (`PRIOR_HTML`) and
confirm — at the **content** level, not just by page name or routing
score — that the page is about the same feature/topic the Jira issue
concerns. Compare the issue's Feature/Topic name, screen references, and
field names against the page's existing ATC Feature cells, table
contents, and headings.
- **Confirmed** when at least one holds: a same-key or synonym-folded
  Feature/Topic row already exists (§10.3); OR the issue's screen/field
  references already appear in the page's canonical tables; OR the page's
  subject (book / chapter / page name + existing rows) is the
  unambiguous home for the feature. → proceed to operations 1–4.
- **Not confirmed** — the page's content is about a different feature
  than the issue describes (name matched but content diverges). Do NOT
  write. For discovered-destination routines (CS) this re-opens
  destination discovery / blocks the scope (§4-CS-D.5). For
  fixed-destination routines, log `Blocked - destination page <id>
  content does not match <KEY>; manual destination review required.` and
  surface it as a manual action.

**1 — Create.** The issue describes a feature/field/action with no
matching row (per the §10.3 match order). Append a new row to ATC and to
every applicable non-ATC table (§10.3 cross-table completeness). Log
`Created - <table> row '<name>' (<KEY>)`.

**2 — Read.** Satisfied by operation 0 — `PRIOR_HTML` is the basis for
every comparison below. No standalone write.

**3 — Update.** A matching row exists and the issue describes the
**same** feature with newer behaviour:
- **Free-text cells** (`Scenario`, `Description`, `Field Behavior`,
  `How it is tracked in Audit Trail`, `Validation Message(s)`): merge at
  bullet granularity per `SKILL.md` §5-C.2. A bullet is REPLACED when the
  issue restates the *same* test case/behaviour with newer wording or a
  changed rule (§5-C.2 step 2b); genuinely new behaviours are APPENDED
  (step 2c); bullets the issue does not mention are KEPT (step 3 — absence
  ≠ removal).
- **Enumerated cells** (`Type`, `Default Value`, `Available Options`,
  `Validation(s)`, `Sort-able?`): the latest Jira value wins. On a
  conflict, log `Updated - <table> row '<name>': <field> changed:
  <old> → <new>` and apply it.
- Append the issue's key to the leftmost-cell parenthetical key list.

**4 — Delete (evidence-gated — the only path that removes content).** A
run removes existing content ONLY when the eligible issue provides
**explicit** evidence the prior behaviour is gone — a removed field, a
withdrawn option, a deprecated validation, a renamed/replaced feature, or
a screen/feature the issue states is no longer present. Trigger phrasing
(non-exhaustive; the evidence must clearly map to the existing content):
*removed, no longer, deprecated, discontinued, replaced by, renamed to,
dropped, withdrawn, retired, superseded by*.
- **Bullet-level remove** — the issue states a specific behaviour no
  longer applies → remove the matching `<li>`. Log `Removed - <table>
  row '<name>' scenario bullet superseded by <KEY>: "<old bullet>"`.
- **Value replace / rename** — the issue states a value/option/validation
  is replaced → overwrite that enumerated value (logged as the §10.4-op-3
  `Updated - … <old> → <new>`). For a **renamed** feature, rename the
  leftmost cell **in place** and keep the row and its key history — do
  NOT delete-and-recreate (that orphans dependent rows and loses keys).
- **Row-level remove** — the issue explicitly removes the **entire
  feature/field/action** the row represents → remove the ATC row AND
  cascade: every non-ATC row whose leftmost cell carries that ATC's `#`
  is removed too, then remaining ATC `#`s and every `(ATC #n)`
  back-reference are renumbered so linkage stays consistent. Log
  `Removed - feature '<name>' (<KEY>) and N dependent rows; explicitly
  removed per <KEY>.`
- **Absence is NEVER deletion.** An issue that simply does not mention an
  existing field/behaviour removes nothing. Silence ⇒ keep.
- **Structural floor.** Evidence-gated removal operates at
  row / bullet / cell granularity only. A run NEVER deletes a whole
  canonical table, the UI section, or any heading — even when emptied of
  this run's content (an emptied table is left in place for future rows).
  The UI section follows its own replace/add rules in §11.1.

**No change markers.** C/U/D edits are applied as clean content — no
yellow tints, no `[New — KEY]` / `[Removed — KEY]` spans, no diff
classes. The audit trail lives in the run log (below), never on the page.

**Logging.** Every Create / Update / Delete operation emits its verb
(`Created` / `Updated` / `Removed`) into the run log, so the audit trail
shows exactly what each fire changed on each destination.

**Final-validation tie-in (STEP 6).** Validation confirms: (a) no
orphaned `(ATC #n)` reference survives a row-level removal; (b) every
removal/replacement carried explicit Jira evidence recorded in the log;
(c) the structural floor held (no table/heading/UI-section deleted).

### 10.5 Comment intelligence — scope changes & deprioritization

**Universal — every routine reads each eligible issue's comments and
classifies them. The classification feeds the §10.4 CRUD contract (what
to write / change / remove) and the §7–§9 eligibility gates (whether to
process the issue at all). Comments are a first-class evidence source,
not just the description.**

A requirement is rarely frozen at filing time. PO / QA / triage comments
routinely (a) change a previously-stated requirement (new default, new
validation, dropped option, renamed field), or (b) deprioritize / descope
the work after the fact. Reading the description alone misses both. This
section makes comment-reading mandatory and defines how each comment
drives a concrete action.

**Fetch.** For every eligible Story / Task **and** every requirement-defect
Bug (per `bug-requirement-filter-policy.md` — Bugs are in scope here too),
read the issue's comments via
`GET /rest/api/3/issue/<KEY>/comment?expand=renderedBody&maxResults=50&orderBy=-created`
(newest-first). **Reuse** the fetch when `bug-requirement-filter-policy.md`
§1.3 already pulled comments for the same issue this run — never double-fetch.
Ignore bot-authored comments (same guard as bug-requirement §1.3: display
name in `['Automation for Jira','Bitbucket','GitHub','Atlassian Assist']`
or `author.accountType == 'app'`).

**Classify** each non-bot comment into one or more of these buckets:

1. **Confirmed-final behavior** (pre-existing rule — `SKILL.md` §5-C.2 /
   STEP 5): the comment states final, decided behavior. Folds into the
   spec additively (Create/Update bullets). Uncertain or discussion
   comments are NOT used — log `Skipped comment <id> - not confirmed as
   final behavior`.

2. **Requirement / scope CHANGE**: the comment explicitly changes a
   previously-stated requirement — a changed default / validation /
   available option, a renamed field, an added or removed sub-behaviour,
   or a "scope reduced / expanded" decision. This is **§10.4 evidence**:
   - A changed value/behaviour → §10.4 op-3 Update: replace the affected
     bullet / enumerated cell. Log `Updated - <table> row '<name>': per
     comment <id> by <author> (<date>): <old> → <new>`.
   - An explicitly dropped sub-behaviour (comment uses supersession
     phrasing — *removed, dropped, no longer, replaced by, renamed to,
     descoped*) → §10.4 op-4 evidence-gated removal of the matching
     bullet / cell / row. Log the `Removed - …` line citing the comment.
   - Always record the comment id + author + ≤160-char excerpt with the
     CRUD log line so the change is auditable.

3. **Deprioritization / de-scope of the WHOLE issue**: the comment
   indicates the Story/Bug itself was deprioritized, dropped from the
   release, parked, or put out of scope (phrase set below). Effect:
   - Issue **not yet written** to the spec → **excluded this run** (it
     contributes no rows). Log `Excluded - <KEY> deprioritized per comment
     <id> by <author> (<date>): "<excerpt>"`.
   - Issue's content **was written by a prior run** AND the comment
     explicitly states the shipped feature/behaviour is *dropped/withdrawn*
     (not merely "lower priority") → §10.4 op-4 evidence to remove that
     content. A bare "deprioritized / moved to next sprint" with no
     statement that the shipped behaviour is withdrawn removes **nothing**
     (absence ≠ removal; **priority ≠ withdrawal**).
   - For a Bug, bucket 3 **overrides** the bug-requirement promotion: a
     deprioritized requirement-defect Bug stays excluded even if it
     otherwise matched a promotion signal.

4. **Noise** (questions, status pings, discussion): ignored.

**Recency guard (applies to buckets 2 & 3).** Honour a comment only when
it is the **latest disposition on that topic**. A newer comment that
re-prioritizes, re-confirms, or reverses an earlier change/deprioritization
overrides the older one (comments are newest-first; the first qualifying
comment on a topic wins). The same negative guard as bug-requirement §1.3
applies — a comment quoting or negating a phrase ("this is NOT being
descoped") does not match.

**Deprioritization phrase set (bucket 3 — case-insensitive regex on the
plain-text comment body after whitespace normalization):**
`deprioriti[sz]ed`, `de-?scoped`, `descoped`, `out of scope`,
`dropped from (this|the) release`, `moved to (the )?backlog`,
`pushed to (the )?next (sprint|release)`, `won'?t (do|fix)`,
`not (going|proceeding) (ahead|with) (this|it)`, `parked`, `shelved`,
`on hold indefinitely`, `removed from scope`.

**Ordering.** Bucket-3 deprioritization is evaluated **with the §7–§9
gates, before destination discovery** (so a deprioritized-and-unwritten
issue is dropped without wasted routing). Bucket-2 scope changes are
evaluated **during STEP 5 compose**, as §10.4 evidence.

**Counters & logging (every routine surfaces these).** `comments_scanned`,
`issues_excluded_by_comment`, `scope_changes_from_comments`, and — per
affected issue — the qualifying comment's id / author / ≤160-char excerpt
for any bucket-2 or bucket-3 action. These appear in the audit log and,
where the routine emails, in the change list / manual-actions section.

---

## 11. User Interfaces (UIs) — at the END of the page

**Canonical §4: User Interfaces are always at the END of the
specifications document. Each screenshot is placed immediately after
its corresponding screen name, with the screen name in tiny-header
format (`<h6>`).**

The routine maintains a single global UI section on the page:

```html
<h2>User Interfaces (UIs)</h2>
<h6>{Screen Name 1}</h6>
<a href="{URL_1}"><img src="{URL_1}" alt="{Screen Name 1}"></a>
<h6>{Screen Name 2}</h6>
<a href="{URL_2}"><img src="{URL_2}" alt="{Screen Name 2}"></a>
```

If the section doesn't exist yet, the routine creates it (positioned
last in the page body, after the canonical tables). If it already
exists, the routine merges into it per §11.1.

### 11.1 Extract → upload → compare → replace/add (UI merge algorithm)

**Extract from Jira** (per eligible story):
- Jira attachments whose `mimeType` starts with `image/` or whose
  filename ends in `.png`, `.jpg`, `.jpeg`, `.gif`, `.bmp`, `.svg`,
  `.webp`.
- Image URLs embedded inside the Jira description (ADF `mediaSingle` /
  `media` nodes, markdown `![]()` patterns).
- URLs in the description / comments matching Figma / InVision /
  Sketch / Miro / Whimsical / Excalidraw / Marvel / Adobe-XD / Zeplin
  domains (these are LINKS — `<a>` only, no `<img>`).

**Upload to BookStack (MANDATORY — never link Atlassian URLs directly).**

Jira attachment URLs of the form
`https://api.atlassian.com/ex/jira/<cloud>/rest/api/3/attachment/content/<id>`
require an authenticated Jira session and return HTTP 403 with
`{"errorMessages":["You do not have permission to view attachment with
id: <id>"]}` when loaded by an unauthenticated browser — which is how
wiki readers' browsers will load them. Therefore the routine MUST
re-host every Jira-attached image inside BookStack before writing the
page HTML:

1. **Download the binary directly to disk via curl.** Use a Bearer-auth
   `curl` against the attachment URL and write the response body to a
   temporary file. The Atlassian sites (`*.atlassian.net`,
   `attachment.atlassian.com`, `*.cloudfront.net`) are in the routine
   execution environment's outbound network allowlist as of 2026-05-18,
   so direct HTTP works.

   ```bash
   LOCAL_PATH="/tmp/${FILENAME}"
   HTTP_CODE=$(curl -sS -o "$LOCAL_PATH" -w "%{http_code}" \
                    -H "Authorization: Bearer $JIRA_API_TOKEN" \
                    -H "Accept: */*" \
                    "$ATTACHMENT_CONTENT_URL")
   if [ "$HTTP_CODE" != "200" ]; then
     # Log "UI download failed" and skip THIS asset; never write the
     # Atlassian URL into the wiki page. Continue with the next asset.
     ...
   fi
   ```

   **CRITICAL — do NOT use the `Read` tool on `$LOCAL_PATH`.** The
   `Read` tool loads images into the routine session's context as a
   visual modality (Claude API multimodal input). If the binary is a
   format the API can't process (corrupt, unusual encoding, partially
   downloaded, oversized), the API returns
   `"API Error: an image in the conversation could not be processed
   and was removed"` and silently drops the image from context — which
   can derail the rest of the run. The image bytes are **opaque** to
   the routine; the next step (upload) references them by file path
   only, never by content. Treat the file as a black box on disk.

2. **Upload to BookStack image-gallery via multipart curl referencing
   the file by path.** Pass `-F image=@$LOCAL_PATH` so curl streams the
   bytes directly from disk into the POST body — never read into the
   routine's context.

   ```bash
   RESPONSE=$(curl -sS -X POST "$WIKI_BASE_URL/api/image-gallery" \
                   -H "$AUTH" \
                   -F "type=gallery" \
                   -F "uploaded_to=$TARGET_PAGE_ID" \
                   -F "image=@$LOCAL_PATH;type=$MIME;filename=$FILENAME")
   ```
   The response is JSON: `{ "id":..., "name":..., "url":"https://enterprisewiki.orangehrm.com/uploads/images/gallery/...",
   "thumbs": { "gallery":"...scaled-thumb...", "display":"...scaled-1680-..." } }`.
   Parse `response.url` and `response.thumbs.display` from this JSON
   only — never inspect the image binary itself.

3. **Delete the temp file** after the upload completes (success OR
   failure): `rm -f "$LOCAL_PATH"`. Keeps the routine's temp space
   clean and avoids accidental Read-tool invocation by later
   diagnostic steps.

4. **Use the BookStack URLs** in the rendered HTML:
   - `<a href="{response.url}">` (full-size image)
   - `<img src="{response.thumbs.display}">` (1680-scaled display variant)
   This matches the existing in-wiki image pattern (see existing
   `/uploads/images/gallery/.../scaled-1680-/...` URLs on the canonical
   Salary page).

5. If the upload fails (any non-2xx response from BookStack), skip the
   UI asset for this run and log
   `UI upload failed - <filename> for <KEY>: <error>`. Do NOT fall back
   to writing the Atlassian URL — that produces broken images for
   readers.

6. Re-upload is one-shot per attachment. Once a Jira attachment is in
   BookStack, the filename-match merge algorithm (below) sees the
   BookStack URL on the next run and no-ops.

**Failure-mode summary table (in priority order):**

| Symptom | Cause | Action |
|---|---|---|
| `curl ... 403 Host not in allowlist` | Atlassian host not in env allowlist | Env admin adds `*.atlassian.net` + `attachment.atlassian.com` + `*.cloudfront.net` to outbound allowlist. (Should be done as of 2026-05-18 — verify before re-firing.) |
| `curl ... 401 / 403` (auth error) | Bearer token wrong / lacks attachment access | Routine Owner regenerates `JIRA_API_TOKEN` with the right user / scope. |
| `API Error: an image ... could not be processed` | Routine used `Read` tool on the downloaded binary. | Bug — STEP 5-D step 1 instructs `curl -o` only. Fix the routine prompt / re-fire. |
| Empty `/tmp/<filename>` after curl 200 | Partial download / response was actually an HTML error page despite 200 | Log `UI download failed - <filename> for <KEY>: empty response`, skip asset, no Atlassian URL fallback. |
| BookStack `POST /api/image-gallery` returns 4xx | Token lacks image upload scope, OR `uploaded_to` page doesn't exist | Routine Owner checks BookStack token + page. |
| BookStack `POST /api/image-gallery` returns 5xx | Transient — retry up to 3× per HTTP retry policy. | Automatic. |

Embedded `<img>` tags inside the Jira description (ADF `media` nodes)
follow the same rule: extract the underlying binary, upload to
BookStack, use the BookStack URL.

Design-tool URLs (Figma / InVision / Sketch / etc.) are NOT uploaded —
they remain external links rendered as `<a href>` only. Those don't
have an `<img>` to break.

Derive a **screen name** per UI asset (used as the `<h6>` text):
1. The heading text immediately preceding the image in the Jira
   description.
2. The Jira story title (cleaned — strip prefixes like `Bug -`,
   `Story:`).
3. The image filename converted to title case (e.g.
   `add-pay-grade-modal.png` → `Add Pay Grade Modal`).
4. Fall back to `Untitled UI <n>` (n = 1-indexed per story).

**Compare against the existing wiki UI section** (parse `<h6>` +
following `<a>`/`<img>` pairs):
- Build a map `{ lowercase_filename → (screen_name, url) }` from the
  wiki.

**Merge rules** (per Jira UI):

| Wiki state | Jira URL state | Action | Log line |
|---|---|---|---|
| filename absent from wiki | — | **ADD** new `<h6>{screen}</h6>` + `<a><img></a>` at end of UI section | `UI added - <filename> for <KEY>` |
| filename present, URL identical | identical | **NO-OP** | `No change - UI <filename> already present` |
| filename present, URL different | newer / different | **REPLACE** the wiki entry's URL (keep its `<h6>` screen name, unless screen name changed too) | `UI replaced - <filename> URL updated (was <old> → now <new>) for <KEY>` |
| wiki has UI not referenced by any Jira story | — | **KEEP** (additive — never delete legacy UIs) | (no log line) |

The replace rule is what implements *"replace the new UIs if available
in Jira"*. The add rule is *"if images are not existing in wiki add
them if available in Jira"*. No-op + keep are the additive-merge
guarantees.

Deduplicate within a single Jira story: if the same filename appears
twice (e.g. once in the description and once as an attachment), emit
one entry.

**Design-tool URLs** (Figma / Sketch / etc.) — these are external
links, not images. Render them as a final sub-block inside the UI
section:

```html
<h6>Design References</h6>
<p>
  <strong>Figma:</strong> <a href="{URL}">{label}</a><br>
  <strong>Sketch:</strong> <a href="{URL}">{label}</a><br>
</p>
```

Same compare-and-merge rules as for images, matched on URL host + path.

### 11.1-bis UI section purity — h6+image pairs ONLY

**The User Interfaces (UIs) section is a gallery, not a narrative.** It
contains **strictly** the following two patterns, repeated per UI:

```html
<h6>{Topic Name}</h6>
<a href="{BS_FULL_URL}"><img src="{BS_THUMB_URL}" alt="{Topic Name}"></a>
```

Plus an optional Design References sub-block at the very end:

```html
<h6>Design References</h6>
<p><strong>Figma:</strong> <a href="{URL}">{label}</a><br>
   <strong>Sketch:</strong> <a href="{URL}">{label}</a></p>
```

**Forbidden inside the UI section** (the routine MUST NOT author any of
these — STEP 6 check #7 enforces it):

- `<p>` paragraphs (captions, descriptions, lead text, transitions) —
  **except** the single `<p>` inside the Design References sub-block.
- `<ul>` / `<ol>` / `<li>` lists of any kind.
- `<table>` of any kind.
- Heading-level captions other than `<h6>` (no `<h4>`, `<h5>`, no
  `UI 1: ...` numbered prefixes, no inline `<strong>UI:</strong>`).
- Narrative connective text between an `<h6>` and its image, or between
  consecutive UI entries.

The image is its own documentation; the `<h6>` labels it. No surrounding
prose. If the spec author needs to explain what a screen does, that
explanation lives in the **Scenario** column of the ATC table (as a
bullet), not in the UI section.

### 11.1-ter Topic-name source priority (Jira-driven)

The `<h6>` topic name MUST be a short noun-phrase label naming the
screen — e.g. `Salary History`, `Pay Grade Configuration`,
`Add Employee Wizard — Salary`. **NEVER** a sentence, description, or
narrative caption.

Resolution priority (the routine takes the first that yields a usable
label, ≤ 6 words, no sentence punctuation):

1. **Jira description heading immediately preceding the image** — when
   the Jira description has an ADF heading right before the embedded
   image (`### Salary History\n![]()`), use the heading text verbatim.
   This is the preferred path because the topic name reflects what the
   spec author actually called the screen.

2. **A bold/strong label in the same description paragraph as the image**
   — e.g. `**Salary History:** ![]()`. Strip the trailing colon.

3. **The Jira attachment's filename normalised to title case** — e.g.
   `salary-history.png` → `Salary History`. Strip extension, replace
   hyphens/underscores with spaces, title-case each word, strip leading
   `Screenshot` / `Image` / numeric prefixes.

4. **The Jira story title (cleaned)** — strip `Bug -`, `Story:`,
   `Task:`, `(<KEY>)` suffixes. Use only if no per-image hint exists.

5. **Generic fallback** — `Untitled UI <n>` where `<n>` is 1-indexed
   per story. The routine MUST log a warning when falling back to
   this level: `validation_warning: ui_topic_name_unresolved for <fn> in <KEY>`.
   The warning surfaces in the email under Manual Actions so the PL
   can add a proper heading to the Jira description and re-fire.

Topic-name validation (applied per topic, also enforced by STEP 6):
- Length ≤ 6 words.
- No period inside the topic (period+space = sentence-form, not a label).
- No leading `The `, `This `, `When `, `A ` (descriptive verbiage).
- Title case preferred but not required.
- Quotation marks for UI strings (`"Save"`) are allowed only if they
  are PART of the topic (e.g. `"Save" Confirmation Modal`).

---

### 11.2 No per-story UI sub-section

The routine **never** emits a per-story `<h4>Interfaces (UIs)</h4>` or
any other per-story UI heading. All UIs live in the single global
`<h2>User Interfaces (UIs)</h2>` section at the END of the page, per
canonical §4. (The routine made this mistake on 2026-05-16 by emitting
per-story UI sub-sections under an invented prose schema; that
schema is forbidden and is now validated against in SKILL.md STEP 6.)

---

## 12. Run Log

At the end of each routine run, generate a clear log with:

**Release context**
- Routine name
- Project key
- Configured `fixVersion`
- Jira `fixVersion.released` flag
- Jira `fixVersion.releaseDate`
- Release gate outcome (CONFIRMED / NOT_YET / BLOCKED) with the
  verbatim policy log line

**Discovery counts** (every issue returned by the fixVersion query,
classified by §8 issue-type filter — these populate the email's
top-band status bar):
- `total_issues_found` — every issue at the configured fixVersion
- `epics_found` / `epics_processed`
- `stories_found` / `stories_processed`
- `tasks_found` / `tasks_processed`
- `bugs_found` — reported, not processed
- `subtasks_found` — reported, not processed
- `other_found` — Improvements, Refactors, Spikes, etc. — reported, not
  processed

**Outcome counts** (per-processed-issue):
- `stories_updated`
- `stories_no_change`
- `stories_skipped` (per-issue skips with reason from §7 or §9)
- `stories_blocked` (per-issue blocks with reason from §3 or §6
  source-material gate)

**Outputs**
- BookStack page IDs written
- GitHub audit-log file URL
- Email send status

**Manual actions required** — list of Jira keys flagged for PL /
Release Manager attention (Blocked items + missing release date /
release flag + any unclassifiable issue types).

Use these statuses:

| Status | Meaning |
|---|---|
| **Updated** | Story was successfully added or updated in the specification page. |
| **No Change** | Story already exists in the specification and no update was needed. |
| **Skipped** | Story was not processed because it is outside scope, not completed, not released yet, or excluded. |
| **Blocked** | Story or `fixVersion` could not be safely processed because required Jira release confirmation or story information is missing. |

---

## 13. Example Blocked Log

```
Blocked - Configured fixVersion 8.0 for project CM is not confirmed as
released in Jira because released=false and releaseDate is empty.
Release Manager or Project Admin must either mark the version as
released or set a valid releaseDate in Jira.
```

---

## 14. Final Rule

Never update specification pages for a Jira story unless Jira confirms
that the configured `fixVersion` is released **and** the story itself is
completed.

**Jira is the only source of release confirmation for this routine.**

The routine's final output (AUDIT SUMMARY and email body) must not
mention wiki/BookStack release checks unless explicitly reporting that
they were intentionally disabled.

---

## 15. Per-Epic Project Scan (Informational)

In addition to the fixVersion-scoped story query that drives wiki
updates, every routine **must** also perform a project-wide Epic scan
at runtime. This pass is purely informational — it does NOT change
which stories are written to the wiki. Its sole purpose is operator
visibility: the management-facing email surfaces every Epic in the
project together with its release status, so Release Manager / PL can
see at a glance which Epics still need wiki action.

This scan applies to **every routine globally** (CM, PNP, Roster,
Performance, Leave, Attendance, etc.) — no project may opt out.

### 15.1 Query

```jql
project = <JIRA_PROJECT_KEY> AND issuetype = Epic
```

Fetch with `fields = ["summary","status","resolution","fixVersions"]`.
Paginate to completion. (Cap at the first 200 Epics returned; if the
project has more, log `Note - epic scan capped at 200 results.` and
proceed.)

### 15.2 Per-Epic release classification

For each Epic returned, derive its release status from its
`fixVersions[]` using the same Jira-only rules as §2 / §4 / §6:

| Epic state | Status | Symbol |
|---|---|---|
| At least one fixVersion with `released==true` OR `releaseDate <= today` | **Released** | ✓ |
| All fixVersions have `released==false` AND (no `releaseDate` OR `releaseDate > today`) | **Pending** | ⚠ |
| Epic has no `fixVersions` attached | **Unassigned** | — |
| Epic `status.name` / `resolution.name` / `labels[]` match the §9 exclusion tokens | **Excluded** | ✗ |

The exclusion check wins over the released / pending check (an Epic
marked Cancelled is **Excluded** even if it has a released
fixVersion).

### 15.3 Counters

Add to the run log (per §12):

- `epics_scanned` — total Epics returned by §15.1
- `epics_released` — count classified Released
- `epics_pending` — count classified Pending
- `epics_unassigned` — count classified Unassigned
- `epics_excluded` — count classified Excluded

### 15.4 Per-Epic record (drives email)

For every Epic, record one entry with these fields:

- `key` — Jira key (e.g. `CM-1`)
- `name` — Jira `summary` verbatim
- `fix_versions` — comma-separated `name` values (e.g. `8.0, 8.0.2`);
  `—` (em-dash) if the array is empty
- `status` — one of `Released` / `Pending` / `Unassigned` / `Excluded`
- `symbol` — one of `✓` / `⚠` / `—` / `✗`

These records populate `{{epicRows}}` in the email template per
SKILL.md §9-C. The Epic Release Status section appears in the email
only when `epics_scanned > 0`; on a project with zero Epics the entire
block is removed via the `{{epicScanBlockStart}}` / `{{epicScanBlockEnd}}`
conditional pair.

### 15.5 Strict separation from the update flow

The per-Epic scan **never** causes a wiki write. Even if an Epic is
classified **Released** here, its child stories are still subject to
§1–§9 (fixVersion scope, completion, exclusion) before any wiki page
is touched. The wiki page update flow remains driven exclusively by
the configured `fixVersion` story query from §1.

Conversely, an Epic classified **Pending** or **Unassigned** does not
block the routine — the routine still proceeds to update wiki content
for any story at the configured fixVersion that passes §1–§9. The
Pending / Unassigned status is reported to the operator only.

---

## 16. Live Specification Nav-Tree Sync (mandatory, every routine, every fire)

> **STRICT RULE — applies to every routine globally** (CM, PNP, Roster,
> Orange Sign, CS Features, and every future Jira-to-wiki routine in
> this repo). No routine may opt out. A routine that skips this sync is
> treated as a defect; STEP 6 validates that the sync ran.

Before any routine reads a destination page or scores destination
candidates, it MUST refresh `specification_nav_tree` in
`resources/wiki_destination.json` so the JSON always reflects the live
shape of Specification shelf id=3. This makes the destinations file
the canonical, version-controlled map of every book / chapter / page
under specifications — every routine (and every operator reading the
repo) can rely on the tree to answer the question *"is this feature
already covered by an existing page somewhere in the shelf?"* without
re-walking the BookStack API.

### 16.1 When to sync

Immediately after `LIVE_SPEC_BOOKS` is captured at STEP 2 (the call
`GET /api/shelves/3`), and **before** any destination scoring or
canonical-table write.

- **CS routine** (`cs_features_daily_sync`) → STEP 2 step 7
- **Agile routines** (`cm_daily_sync`, `pnp_daily_sync`,
  `roster_daily_sync`, `orange_sign_daily_sync`) → STEP 2 step 6

If the sync fails (any non-2xx response from a follow-up `GET
/api/books/<id>`), abort `status=BLOCKED reason='specification_nav_tree
sync failed — cannot proceed without a current view of shelf 3'`.

### 16.2 Walk

For every `book_id` in `LIVE_SPEC_BOOKS`:

1. `GET /api/books/<book_id>` → capture the book's `name`, `slug`, and
   `contents[]` array. The book's position in `LIVE_SPEC_BOOKS.books[]`
   is its `sort_order` (1-indexed).
2. For each chapter in `contents[]` (any entry with `type == "chapter"`),
   record `id`, `name`, `slug`, position within `contents[]` as
   `sort_order`. List its child pages from the chapter's own
   `pages[]` (or fetch via `GET /api/chapters/<id>` if absent).
3. For each page that sits directly under the book (any `contents[]`
   entry with `type == "page"`), record it as an `orphan_page` with
   `id`, `name`, `slug`, `sort_order` (position within `contents[]`),
   and `url` (`/books/<book_slug>/page/<page_slug>`).

### 16.3 Diff against the stored tree

Compare the live walk to `specification_nav_tree.books[]` already in
`wiki_destination.json`. Match nodes by `id` (never by name — pages get
renamed, ids are stable).

| State | Action |
|---|---|
| `id` exists in stored tree AND in live walk, name unchanged | No-op |
| `id` exists in stored tree AND in live walk, but `name` or `slug` differs | UPDATE `.name` / `.slug` / `.url` in place. Log `Renamed - <type> id=<n> "<old>" -> "<new>"`. |
| `id` exists in stored tree AND in live walk, but `sort_order` differs | UPDATE `.sort_order` in place. Log `Reordered - <type> id=<n> sort_order <old> -> <new>`. |
| `id` exists in live walk but NOT in stored tree | APPEND a new node at the correct `sort_order`. Set `deprecated_at: null`. Log `Discovered - <type> id=<n> "<name>"`. |
| `id` exists in stored tree but NOT in live walk | KEEP the node in JSON. Set `deprecated_at: <run UTC>`. Log `Deprecated - <type> id=<n> "<name>" — no longer present in shelf 3`. Do NOT delete. |

Deprecated nodes remain visible in the JSON forever (operators rely on
the history to investigate "where did page X go?"). A node that was
previously deprecated and re-appears in a later walk has its
`deprecated_at` reset to `null` and is logged as
`Restored - <type> id=<n> "<name>"`.

### 16.4 Counters

Update `specification_nav_tree.node_count`:

- `books` — count of `books[]` entries where `deprecated_at == null`
- `chapters` — count of `chapters[]` across all live books where
  `deprecated_at == null`
- `pages` — count of `pages[]` + `orphan_pages[]` across all live
  books / chapters where `deprecated_at == null`
- `deprecated` — count of nodes (any type) where `deprecated_at != null`

Set:

- `last_synced_at` — UTC ISO 8601 of the walk
- `last_synced_run` — the firing routine's trigger id (or `manual` for
  ad-hoc fires)
- `last_synced_commit_sha` — the SHA of the self-commit that persists
  this refresh (filled AFTER the GitHub PUT in §16.5)

### 16.5 Self-commit contract

If the diff produced any change (new / updated / deprecated / restored
nodes, or any sort_order shuffle), the routine MUST self-commit the
refreshed `specification_nav_tree` block back to the current branch
via the GitHub Contents API. The commit message format:

```
chore(nav_tree): <routine_slug> STEP 2 nav-tree sync — +<a> discovered, -<b> deprecated, <c> renamed, <d> reordered
```

Target branch:
- For routines running against `main`, commit to `main`.
- For routines running against a test branch (`test/cs-dryrun-*`,
  `claude/*`), commit to that same branch.

If `GITHUB_TOKEN` is unset, skip the self-commit silently but STILL
log every diff line under `## STEP 2.x — Nav-Tree Sync` in the audit
log. The next fire with a token will pick up the unwritten delta and
commit it.

If the diff is empty (zero changes), no commit is made; the routine
logs `specification_nav_tree: no change (<books> books, <chapters>
chapters, <pages> pages)` in the audit log and proceeds.

### 16.6 Validation (STEP 6 — applies to every routine)

STEP 6 adds two checks driven by this section:

| Check | Pass condition |
|---|---|
| **NAV-1** Sync ran | The audit log contains the `## STEP 2.x — Nav-Tree Sync` section AND `last_synced_at` was updated to a timestamp ≥ run start. |
| **NAV-2** Tree is consistent | Every `routine_destinations.<slug>.page_id` (where non-zero and non-null) corresponds to an `id` present in `specification_nav_tree` with `deprecated_at == null`, OR the routine logs a manual_action explaining the deviation (e.g. fixed page_id was deleted in BookStack — operator should refresh `routine_destinations`). |

NAV-1 failure → run is recorded `status=FAILED` (sync was skipped or
the audit log is missing the section).

NAV-2 failure → routine still completes but emits a manual_action so
the operator knows the configured destination is stale.

### 16.7 Why this is mandatory

CS features in particular routinely affect multiple product areas; the
CS routing skill must be able to answer "does an existing page already
cover this scope?" before falling back to its §4-CS-D.4c create-flow.
Without a current map of the whole shelf, the create-flow risks
duplicating work that already exists under a sibling book. Agile
routines also benefit: their fixed `page_id` configurations decay
silently when a wiki admin renames or moves a page — NAV-2 catches
that decay on the very next fire.

---

## 17. Per-run changelog (mandatory, every routine, every fire — canonical on `main`)

Every routine MUST record its wiki changes in the shared changelog on every
fire, **at STEP 9**. The changelog is the stakeholder-facing roll-up: a
department head opens it and sees, per day, every project's wiki CRUD at a
glance.

### 17.0 Two files, and they live on `main` (NON-NEGOTIABLE)

- **Canonical store = `logs/changelog/changelog.csv`** — an append-only CSV
  ledger (plain text). This is the source of truth. Text means it never
  corrupts and merges cleanly across routines and branches.
- **Rendered view = `logs/changelog/wiki_sync_changelog.xlsx`** — the
  colour-coded Excel, **regenerated from the full CSV on every run** (never
  read-modify-written — that previously base64-corrupted the binary through
  the agents' commit flow).

**Both files are canonical on the `main` branch.** A routine's `.md` audit log
may commit to the routine's own run branch (scheduled remote agents commit to
per-run `claude/*` branches), **but the changelog CSV + xlsx MUST be committed
to `main`** so every project's history converges in one place. NEVER leave the
changelog only on a run branch — that is exactly the failure that hid the
2026-06-07 CM run. Use the GitHub Contents API targeting `branch=main`:
GET the current file `sha` on `main` → PUT the new content with that `sha` →
on `409`/`412` (a concurrent routine updated it first) re-GET, re-apply this
run's rows via the helper (idempotent — it de-dups by row signature), and
re-PUT. Retry per the standard HTTP retry policy.

### 17.1 Structure
- **One sheet per run-date**, named `DD/MM/YYYY` (e.g. `07/06/2026`); the
  helper stores it as `07.06.2026` (Excel forbids `/`), logical name is the
  slashed date.
- **One sheet per day; every routine that fires that day appends to it** — the
  xlsx is rebuilt from the CSV, which holds all rows for all routines/dates, so
  the day's sheet naturally contains every routine's rows. No second sheet per
  date.
- Rows are **colour-banded per project** (Project cell) with CRUD-Op and Status
  cells colour-coded.

### 17.2 Columns (CSV header = xlsx columns, helper-enforced)
`Run Time (UTC) | Routine | Project | Status | Jira Key | Topic / Feature |
Affected Area | Wiki Book | Wiki Page | Page ID | CRUD Op | Previous Wiki
Content | New / Changed Content | Outcome | Confidence | Fix Version |
Evidence / Notes`
- **Previous / New** capture the before/after of the §10.4 CRUD op (`—` where
  not applicable). **CRUD Op** ∈ `Created | Updated | Replaced | Deleted |
  Migrated | No-change`. **Evidence** carries the driving Jira phrase or
  comment id/author (§10.4 / §10.5).

### 17.3 How (STEP 9 sub-step)
1. **Pull the current `main` `changelog.csv`** into the working tree (so the
   ledger is up to date before appending).
2. Build a payload JSON from this fire's per-issue / per-destination CRUD
   (schema at the top of `routines/update_changelog.py`).
3. Run `python routines/update_changelog.py <payload.json>`. It appends to the
   CSV (idempotent — de-dups by signature) and re-renders the xlsx from the
   full ledger. Import-safe; on failure prints `CHANGELOG-SKIP ...` and exits 0.
   Record the `CHANGELOG-OK` / `CHANGELOG-SKIP` line under a
   `## STEP 9 — Changelog` section of the audit log.
4. **Commit BOTH `logs/changelog/changelog.csv` AND
   `logs/changelog/wiki_sync_changelog.xlsx` to `main`** (Contents API,
   `branch=main`, sha + retry per §17.0). This is independent of where the
   `.md` audit log is committed.
5. A run with no content changes (NO_CHANGE / SKIPPED / BLOCKED) still writes
   ONE summary row so the day's sheet records that the routine fired.

### 17.4 Validation (STEP 6)
`CHANGELOG-1` — the audit log contains a `## STEP 9 — Changelog` section with a
`CHANGELOG-OK` / `CHANGELOG-SKIP` line, and on a real run the CSV + xlsx were
committed **to `main`** (not only the run branch). `CHANGELOG-SKIP` is a soft
pass but surfaces as a `manual_action` so the operator knows the ledger lagged.

### 17.5 Safety net — the nightly Consolidator
Scheduled remote routines commit their `.md` logs to per-run `claude/*`
branches, so a routine that fails to push its changelog rows to `main` (e.g. an
older trigger prompt) would otherwise be invisible. The **Consolidator**
(`routines/consolidate_changelog.py`, scheduled nightly at `0 22 * * *` UTC —
after the `30 21` batch) is the backstop: it sweeps run logs from **every
branch**, de-dups by `(run_utc, routine)` against `changelog.csv`, and writes
any missing runs into the canonical CSV + xlsx on `main`. This guarantees every
run lands on `main` even if a routine's own STEP 9 didn't. The in-routine STEP 9
(§17.3) still gives the richest per-issue before/after rows; the Consolidator
adds a summary row for any run the in-routine step missed.
