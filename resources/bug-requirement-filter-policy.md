# Requirement-Defect Bug Filtering Rule (Bug Carve-Out)

> **AUTHORITY:** This file sits at **authority level 1.5** — directly
> below `release-filter-policy.md` and above `SKILL.md`,
> `WIKI_PAGE_RENDER.md`, and every per-routine slim prompt. It is
> **subordinate to `release-filter-policy.md`**: where that file's
> general rules (§1–§9 release / completion / exclusion gates, §10
> canonical-table contract, §11 UI gallery, §12 run log) apply, they
> still apply to bugs too. This file's sole job is to define the **one
> carve-out** to `release-filter-policy.md` §8's "Bugs are excluded by
> type" rule. When this file disagrees with `SKILL.md` or
> `WIKI_PAGE_RENDER.md`, **this file wins**; when it disagrees with
> `release-filter-policy.md`, **that file wins**.
>
> Routines must read this file at STEP 2 (repo-aware bootstrap) and
> abort `status=BLOCKED reason='resources/ unreachable'` if it is
> missing.

Applies to **every project routine** (CM, PNP, Roster, Orange Sign,
Performance, Leave, Attendance, the dynamic CS routine, and any other
Jira project), exactly like `release-filter-policy.md`.

---

## 0. Why this carve-out exists

`release-filter-policy.md` §8 excludes Bugs from specification coverage
because *"bugs document defects, not spec."* That is correct for the
overwhelming majority of bugs (functional regressions, environment
issues, UI glitches). But a narrow class of bugs **does** change the
documented requirement — a defect logged because the *specified
behavior itself* was wrong, and the fix is a **requirement
correction**. Those bugs MUST flow into the specification page, because
after the fix the released behavior no longer matches what the spec
says.

This file defines exactly which bugs qualify and how they are handled.
**No other bug type is ever processed** — the default exclusion from
`release-filter-policy.md` §8 remains in force for everything else.

---

## 1. The qualifying condition (the gate)

A Bug is promoted from *excluded-by-type* to a **processing candidate**
if **both** of the following hold:

1. **It is flagged as a requirement defect** — by ANY of the three
   signals below (this is an OR — whichever is present first qualifies;
   record which signal matched):
   - **(a) Type Of Defect = Requirement.** The Jira field
     **"Type Of Defect"** (single-select) has the option value
     **`Requirement`** (match case-insensitive, trimmed); **OR**
   - **(b) `[Requirement]` summary prefix.** The Jira `summary`, after
     trimming, begins with a bracketed tag whose inner text equals
     `requirement` (case-insensitive) — e.g. `[Requirement] ...`,
     `[REQUIREMENT] ...`, `[ Requirement ] ...`; **OR**
   - **(c) Requirement-confirming comment.** A Jira comment on the
     bug — read via `GET /rest/api/3/issue/<KEY>/comment` — contains
     language explicitly classifying the change as a requirement
     update. The exact phrase set is in §1.3 below; matches are
     **case-insensitive** and must occur on a comment posted by a
     non-bot author after the most recent **non-Open** status
     transition (i.e. a comment that confirms the disposition, not an
     early-triage suggestion that was later overturned). The comment
     must NOT be in a section quoted from another comment (no nested
     `> quote` blocks).

   The three signals are equal in authority. This hybrid exists because
   teams tag requirement defects three different ways: some set the
   `Type Of Defect` field, the Hightower (HT) team marks them with the
   **`[Requirement]` summary prefix**, and other teams (or late-stage
   triage decisions) only call out the requirement nature in a comment
   on the bug — usually the final QA-acceptance or PO-acceptance
   comment. A field-only or prefix-only gate would miss the comment-tag
   path entirely (see §1.2). Recording **which** signal matched, and
   when (c) matches the comment id + author + matched phrase, is
   required for the per-issue log (see §5.1).
2. The Bug satisfies **every gate a Story must satisfy** in
   `release-filter-policy.md`:
   - §1 — linked to the routine's configured `fixVersion`.
   - §2 / §4 / §6 — that `fixVersion` is confirmed released (Jira-only).
   - §7 — the Bug itself is completed (`statusCategory.key == "done"`
     or a completed status name).
   - §9 — not excluded by resolution / status / labels.
   - source-material gate (`SKILL.md` §4-C) — has extractable behavior
     text in its description.

If **none** of the three signals in (1) is present, the Bug **stays
excluded** — the default `release-filter-policy.md` §8 behavior is
unchanged. If (1) is satisfied but any gate in (2) fails, the Bug is
**skipped/blocked** with the same verbatim log line a Story would get
(it does not become a silent exclusion).

**Module of impact is NOT part of this gate.** See §3.

### 1.1 Verified Jira field + endpoint mapping (OrangeHRM Enterprise instance)

Resolve fields by **display name** at runtime (via the `names`
expansion on the issue payload), not by hard-coded id — ids can differ
per Jira instance. The verified mapping for the OHRM Enterprise cloud
(`orangehrmenterprise.atlassian.net`, cloudId
`8cb10ab9-f92f-44b6-8fe2-d076ed2e5175`) as of 2026-06-01 is:

| Purpose | Jira display name | Custom field id / endpoint | Type | Notes |
|---|---|---|---|---|
| **Gate signal (a)** | `Type Of Defect` | `customfield_10051` | single-select | Option `Requirement` confirmed valid in JQL. Other observed options: `Functional`, `UX`, `UI`, `Localization`, `Performance`. |
| **Gate signal (b)** | `summary` | (built-in) | string | Qualifies when the trimmed summary begins with a bracketed `[Requirement]` tag (case-insensitive). This is the signal the HT team actually uses today. |
| **Gate signal (c)** | `comment[].body` | `GET /rest/api/3/issue/{key}/comment?expand=renderedBody&maxResults=50&orderBy=-created` | array of ADF/HTML | Returns the bug's comments newest-first. Iterate up to the first 50; for each, capture `author.accountId`, `author.displayName`, `created`, `updated`, `body` (rendered HTML). Match per §1.3. Excludes bot-authored comments (display name in `['Automation for Jira', 'Bitbucket', 'GitHub', 'Atlassian Assist']` or `author.accountType == 'app'`). |
| Advisory module | `Module` | `customfield_10090` | single-select | e.g. `HR Administration` on CM-17, `Leave` on most HT blackout bugs. See §3. |
| Advisory module (alt) | `Module / Feature` | `customfield_10100` | select | Frequently empty. See §3. |

`STEP 3-C` already fetches `customfield_*` and `summary`, so signals
(a) and (b) arrive without an extra query. Signal (c) requires **one
additional `GET /comment`** per Bug that fails (a) and (b) — at most
one extra Jira call per non-prefix non-field Bug per fire. This is
acceptable cost; the routine MUST NOT fetch comments for Bugs already
qualifying via (a) or (b) (waste), nor for non-Bug issue types (waste).

If the **"Type Of Defect"** field cannot be resolved by name in the
issue payload (field absent from the project's bug screen), do NOT
exclude on that alone — fall through to (b) and (c) before deciding. A
Bug is excluded only when **all three** signals are absent. Never guess
the requirement flag from any other field (e.g. Module, labels,
priority).

### 1.2 Forward-looking note

As of 2026-05-27, signal (a) was **dormant**: zero bugs across the
whole Jira instance had `Type Of Defect = Requirement` (0 in CM, 0
globally; observed values were Functional / UX / UI / Localization /
Performance). Signal (b) was the **active** one — the HT team flags
requirement defects with the `[Requirement]` summary prefix. A dry-run
over the HT "Leave Blackout Periods" cluster (HT-965/966/970/971/972)
found 30 linked bugs, of which **15 carried the `[Requirement]`
prefix** while 0 set the field. Without signal (b) the carve-out would
have processed nothing there.

Signal (c) closes the last gap: teams (CM, PNP, Roster, Orange Sign)
that don't yet use the field and don't tag in the summary frequently
state the requirement decision in a closing comment — typically the
PO / QA / triage comment that accepts the bug as a spec change. A
sample sweep on 2026-06-01 across CM / PNP closed bugs found 8 cases
where the final comment explicitly stated *"updating the requirement
to reflect this behavior"* or equivalent, on bugs whose summary made
no mention of "requirement" — i.e. invisible to (a) and (b), visible
only to (c).

All three signals stay in the gate so the rule keeps working as teams
migrate between tagging conventions.

### 1.3 Comment phrase set for signal (c)

The comment-text matcher uses a **curated phrase set** (case-insensitive,
applied to comment body after normalising whitespace, after stripping
HTML tags, and after dropping any `> quote` blocks). A match on ANY one
phrase qualifies the bug:

| # | Pattern (case-insensitive regex on plain-text comment body) | Intent |
|---|---|---|
| c1 | `\b(?:accept(?:ed)?|sign(?:ed)? off|approved)\s+as\s+(?:a\s+)?(?:new\s+)?requirement\b` | Explicit acceptance ("accepted as a requirement", "signed off as a new requirement", "approved as requirement"). |
| c2 | `\b(?:this\s+is\s+(?:now\s+)?(?:a\s+)?(?:new\s+)?requirement|now\s+(?:a\s+)?(?:new\s+)?requirement)\b` | Re-classification ("this is now a requirement", "now a new requirement"). |
| c3 | `\brequirement(?:s)?\s+(?:change|update|correction|addition|revision|amend(?:ment)?|clarif(?:y|ication))\b` | Operative change ("requirement update", "requirement correction"). |
| c4 | `\bspec(?:ification)?\s+(?:change|update|correction|revision|amend(?:ment)?)\b` | Spec-level change ("spec change", "specification update"). |
| c5 | `\bupdat(?:e|ing|ed)\s+the\s+(?:spec(?:ification)?|requirement)(?:s)?\b` | "Update the spec / requirement" verb form. |
| c6 | `\b(?:behaviou?r|spec(?:ification)?)\s+(?:has\s+been\s+)?chang(?:ed|ing)\s+(?:to|in|and)\b` | "Behavior has been changed to ..." disposition. |
| c7 | `\[\s*requirement\s*\]` | The literal `[Requirement]` tag added inside a comment (rather than as a summary prefix). Common when triage decision is taken AFTER the bug was filed. |
| c8 | `\b(?:cpo|po|product\s+owner|qa(?:-lead)?)\s+accept(?:ed|ance)\s*[:\s]+.*\brequirement\b` | Authority-acceptance lines (CPO/PO/QA acceptance) that explicitly invoke requirement. |

**Negative guard** — a comment is NOT a match if its body, after
normalisation, contains any of:
- `not a requirement` (literally) — explicit rejection.
- `requirement was previously` followed by `not changed` / `unchanged`.
- A `> ` quote-block prefix on the matching line (the matcher operates
  on de-quoted body only; this is implementation-level).

**Match priority within signal (c)** — when multiple comments match
on the same bug, record the **earliest one chronologically** as the
qualifying signal (the spec change was decided then; later comments
just confirm). The audit log records the qualifying comment's id,
author display name, created timestamp, and a ≤ 160-char excerpt
containing the matched phrase.

**Implementation note (per routine STEP 4-A.0-bis):** the matcher runs
ONLY after signals (a) and (b) have both returned negative. Skip the
`GET /comment` call entirely for Bugs that already qualified — those
fields are already in the issue payload.

---

## 2. JQL is not narrowed — filter in STEP 4

Do **not** add `AND "Type Of Defect" = Requirement` to the STEP 3-C
discovery JQL. The discovery query stays
`project = <KEY> AND fixVersion = "<SCOPE>"` so the run log still
reports **every** bug found (`bugs_found`), qualifying or not. The
qualifying test runs per-issue at `SKILL.md` STEP 4-A.0-bis, including
the comment-fetch for signal (c). This keeps operator visibility
intact: the email's bug card still counts all bugs, and the run log
still records why each non-qualifying bug was excluded.

---

## 3. Module of impact — advisory only (NOT a gate)

"Module of impact" (the `Module` / `Module / Feature` fields above) is
**recorded for traceability but is NEVER a reason to exclude a bug** in
the 1:1 routines (CM, PNP, Roster, Orange Sign, …), where each routine
already writes to a single fixed destination page from
`wiki_destination.json`. The destination is fully determined by routine
config, so the module value cannot change where a qualifying bug is
written.

Rationale: making Module a hard gate would create **false negatives** —
a genuine requirement-correcting bug would be silently dropped just
because someone forgot to set the field. We refuse to drop the exact
bugs this rule is meant to capture.

**Handling:**
- If a qualifying bug has a Module value, record it in the per-issue
  log Notes (`Module: <value>`) and in the STEP 9 frontmatter
  (`bug_modules:` list) for traceability.
- If a qualifying bug has **no** Module value, **still process it** —
  log `Note - <KEY> qualifies as requirement-defect; Module of impact is empty (advisory only, not blocking).`

**Reserved future use — dynamic CS routing only.** Module of impact MAY
be used as a destination **router** exclusively in the dynamic CS case
(`cs_features_daily_sync`, `destination_mode: dynamic_by_affected_area`,
governed by `CS_FEATURE_ROUTING_SKILL.md`), where one Jira issue can
affect multiple product areas and there is no single fixed page. No
agile 1:1 routine may use Module for routing.

---

## 4. How a qualifying bug is processed (content mapping)

Once a Bug passes §1, it joins `ELIGIBLE_STORIES` and is processed by
`SKILL.md` STEP 5 **exactly like a Story**, with one nuance:

- A requirement correction usually **updates an existing documented
  behavior** rather than introducing a brand-new feature. Apply the
  §10.3 de-duplication contract (`SKILL.md` §5-C.1/§5-C.2): match the
  bug's feature first by Jira key, then by semantic Feature/Topic name,
  and **merge into the matched row's Scenario/behavior** so it reflects
  the corrected requirement. Append the bug's Jira key to the row's
  parenthetical key list. Only append a **new** row when the corrected
  requirement is genuinely not represented yet.
- The Feature-cell title is de-prefixed exactly as for stories — strip
  a leading `Bug -` / `Bug:` (per `SKILL.md` §5-C step 2) **and any
  leading bracketed triage tag** such as `[Requirement]`, `[Client
  Specific]`, `[UX]` (case-insensitive). These tags are triage metadata,
  not part of the feature name, and must never appear in authored page
  content. fixVersion is still NOT written to the page.

A qualifying bug that results in no canonical-table change (all bullets
already byte-equivalent) logs `No change - <KEY> already up to date.`
like any other no-op issue.

---

## 5. Logging & counters

### 5.1 Per-issue log lines (verbatim)

| Situation | Log line |
|---|---|
| Bug qualifies via `Type Of Defect` (signal a) | `Updated - <KEY> (requirement-defect Bug, matched Type Of Defect=Requirement): <change summary>.` |
| Bug qualifies via `[Requirement]` prefix (signal b) | `Updated - <KEY> (requirement-defect Bug, matched [Requirement] summary prefix): <change summary>.` |
| Bug qualifies via comment match (signal c) | `Updated - <KEY> (requirement-defect Bug, matched comment by <author display name> on <YYYY-MM-DD>: "<≤160-char excerpt with matched phrase>"): <change summary>.` |
| Bug qualifies, no change needed | `No change - <KEY> already up to date.` |
| Bug excluded — not a requirement defect | `Excluded - <KEY> is a Bug; not a requirement defect (Type Of Defect='<value or unset>', summary has no [Requirement] prefix, no qualifying comment in last 50 comments).` |
| Bug qualifies but fails a Story gate | the same verbatim §7 / §9 / source-material line a Story would get |
| Qualifying bug, empty Module | `Note - <KEY> qualifies as requirement-defect; Module of impact is empty (advisory only, not blocking).` |

The per-issue line names **which** signal matched (field vs prefix vs
comment) so the run log shows why each bug was promoted. Bugs that
match none of the three signals get the specific "not a requirement
defect" line above — naming the field value seen, the absence of the
prefix, and the absence of a qualifying comment — rather than the
generic `issue type not in spec coverage scope` line, so the log
explains the exclusion.

### 5.2 Counters (added to `release-filter-policy.md` §12 / `SKILL.md` STEP 9 frontmatter)

- `bugs_found` — unchanged: **every** bug at the fixVersion (qualifying
  or not). Still drives the email "Bugs Reported" card.
- `bugs_requirement_found` — subset of `bugs_found` flagged as a
  requirement defect by ANY of the three signals.
- `bugs_requirement_found_by_signal` — breakdown:
  `{ "a_type_of_defect": <n>, "b_summary_prefix": <n>, "c_comment_match": <n> }`.
- `bugs_requirement_processed` — subset of `bugs_requirement_found` that
  passed every Story gate and reached STEP 5 (these render as rows in
  the email's per-issue results table with an `Updated` / `No Change`
  status, exactly like a story).
- Outcome counts (`stories_updated` / `stories_no_change` /
  `stories_skipped` / `stories_blocked`) **include** processed
  requirement-bugs — they are eligible issues like any other.

---

## 6. Final rule

The only bug ever written to a specification page is one flagged as a
requirement defect — **`Type Of Defect = Requirement` OR `[Requirement]`
summary prefix OR a qualifying comment per §1.3** — AND that passes
every release / completion / exclusion / source-material gate a Story
must pass. Every other bug remains excluded by
`release-filter-policy.md` §8. Module of impact is advisory in 1:1
routines and a router only in the dynamic CS case.
