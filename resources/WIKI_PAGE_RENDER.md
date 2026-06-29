---
name: wiki-page-render
description: >
  HTML render mechanics for the release-filtered Jira-to-Wiki sync routines.
  Strictly follows specification-writing-guideline.md — 5 canonical tables
  (ATC + List + Search + Form + Audit Trail) and a single global User
  Interfaces (UIs) section at the END of the page (h6 screen names + linked
  images). No invented section types, no prose sub-section headings, no
  per-release h2 organizers.
---

# Wiki Page Render — HTML Output Mechanics

This file documents *how* the routine renders HTML into the BookStack
destination page. The *what* is governed by
`specification-writing-guideline.md` (canonical structural authority) and
`release-filter-policy.md` (release eligibility + UI merge algorithm).
When this file disagrees with either of those, **they win**.

---

## 1. Page anatomy (canonical, not invented)

Per `specification-writing-guideline.md`:

```
[Page Title] (managed by BookStack, never authored by the routine)

[Existing legacy content — preserved verbatim by additive merge]

<h3>Acceptance Test Cases</h3>     ← canonical heading
  <table>...</table>                ← canonical 3-col table (always emitted)

<h3>List</h3>                       ← canonical heading (only if any List rows exist)
  <table>...</table>                ← canonical 3-col table

<h3>Search</h3>                     ← canonical heading (only if any Search rows exist)
  <table>...</table>                ← canonical 5-col table

<h3>Form</h3>                       ← canonical heading (only if any Form rows exist)
  <table>...</table>                ← canonical 6-col table

<h3>Audit Trail</h3>                ← canonical heading (only if any Audit Trail rows exist)
  <table>...</table>                ← canonical 3-col table

<h2>User Interfaces (UIs)</h2>      ← always last on the page; h6 screen name + <a><img>
```

### 1.1 MANDATORY: section heading above each table

Every canonical table **MUST** be immediately preceded by its canonical
section heading. The heading is **NOT** a presentation hint — it is
how a spec reader (and the routine itself on the next run) finds the
table. A page with `<table>` cells but no preceding heading reads as
raw data with no context, and the routine's STEP 5-B locator scans
for the heading first; missing headings break the locator.

Canonical heading text + level (verbatim, this is the only correct shape):

| Table | Canonical heading HTML |
|---|---|
| **Acceptance Test Cases** (ATC) | `<h3>Acceptance Test Cases</h3>` |
| **List** | `<h3>List</h3>` |
| **Search** | `<h3>Search</h3>` |
| **Form** | `<h3>Form</h3>` |
| **Audit Trail** | `<h3>Audit Trail</h3>` |
| **User Interfaces** (the global UI gallery) | `<h2>User Interfaces (UIs)</h2>` |

Note the level difference: the 5 table sections are `<h3>`; the UI
gallery is `<h2>` because it is a top-level section of the page, not
a peer of the 5 spec tables. This matches every established spec
page in shelf 3 today (Salary p.360, Apply Leave p.266, Assign Leave
p.264, etc.).

A table whose section heading is missing, mistyped, or at the wrong
level fails STEP 6 check **#2-HDR** (per-table section-heading
verification — see `SKILL.md` STEP 6 / `CS_FEATURE_ROUTING_SKILL.md`
STEP 6 table-heading checks). The locator at STEP 5-B uses the heading
to anchor table discovery; the validator at STEP 6 enforces it before
PUT.

When the routine **initialises** a table from scratch (the create-flow
path of §4-CS-D.4c in the CS routine, and §5-B init on agile routines
when a page has only `<h1>` and no tables yet), the heading MUST be
emitted **immediately before** the `<table>` element in the same PUT
body. Never emit a table without its heading; never emit a heading
without the table that follows it.

### 1.2 The routine authors content INSIDE these canonical tables only

There are no `<h2>{fixVersion}</h2>` release headers, no per-story
`<h3>{Title} (KEY)</h3>` sections, and no `<h4>Overview</h4>` etc.
sub-sections. fixVersion appears ONLY as the value of the Release
column on the ATC table. The five `<h3>` headings listed in §1.1 plus
the single `<h2>User Interfaces (UIs)</h2>` are the **only headings
the routine ever authors** — anything else under `<h2>` / `<h3>` /
`<h4>` / `<h5>` belongs to legacy content and is preserved verbatim
by the additive merge.

---

## 2. The 5 canonical tables — exact column shapes

### 2.1 Acceptance Test Cases (3 columns — canonical)

```html
<table border="1">
  <colgroup>
    <col style="width:15%">
    <col style="width:42%">
    <col style="width:43%">
  </colgroup>
  <tbody>
    <tr>
      <td><strong>#</strong></td>
      <td><strong>Feature</strong></td>
      <td><strong>Scenario</strong></td>
    </tr>
    <tr>
      <td>1</td>
      <td>Pay Grade Soft Delete (CM-2)</td>
      <td>When a pay grade is deleted, retire it instead of hard-deleting; existing employees referencing the grade keep their reference with a "Past" suffix.</td>
    </tr>
    ...
  </tbody>
</table>
```

- `#` is a 1-based sequence across the entire table. Never reset.
- `Feature` ends with a **parenthetical Jira-key list**: `(<KEY>)` when
  one story owns the row, `(<KEY>, <KEY2>, ...)` when several stories
  contributed to the same feature (per the de-duplication contract in
  `release-filter-policy.md` §10.3 and `SKILL.md` §5-C.1). On
  subsequent runs, rows are re-matched first by Jira-key (any key in
  the list matches), then by semantic Feature/Topic name.
- `Scenario` is a **bulleted list** in present tense — one `<li>` per
  distinct test case / released behavior point, per
  `specification-writing-guideline.md` §2.2 (*"Use bullet points for
  multiple details inside table cells"*). The cell is always shaped as
  a `<ul>` containing one or more `<li>` items, even when the feature
  has a single test case. Plain text inside each bullet (`<strong>` /
  `<em>` allowed for emphasis on field, button, tooltip labels; UI
  strings kept in `"double quotes"` verbatim). No `<img>` and no
  `<table>` inside any bullet — UI screenshots belong in the global
  User Interfaces (UIs) section at end of page. When multiple stories
  contribute, bullets are merged per `SKILL.md` §5-C.2 — earlier-
  confirmed bullets are preserved, never silently dropped.

  Canonical Scenario HTML shape:
  ```html
  <td>
    <ul>
      <li>Pay grades currently assigned to employees cannot be deleted; the delete option is disabled with tooltip "Cannot delete a pay grade in use by current employees."</li>
      <li>Pay grades with no prior assignment are physically deleted; those previously but no longer assigned are soft-deleted, retaining their name with a "(Deleted)" suffix in Salary History and the Salary tab and not appearing in the Pay Grade dropdown.</li>
      <li>Creating a new pay grade with the same name as a deleted one displays the inline message "Name already used by a deleted pay grade."</li>
    </ul>
  </td>
  ```

**De-duplication (universal across all 5 canonical tables):** before
appending a new row, scan the table for any existing row whose match
cell already names the same feature / topic / field / action (per
`specification-writing-guideline.md` §2.5 and `SKILL.md` §5-C.1). If
found, update that row's free-text cell in place using the §5-C.2
merge rule and append the new Jira key to the cell's key list. See
`release-filter-policy.md` §10.3 for the policy-level statement.

**fixVersion is NOT on the wiki page** — not as a column, not as a
heading. Jira is the single source of truth for "which release did
this ship in"; the wiki is the current spec. The routine uses
fixVersion at runtime as a filter to decide which stories to process
(per `release-filter-policy.md` §1–§9), then writes only the canonical
3-column ATC row.

### 2.2 List (3 columns — canonical)

```html
<table border="1">
  <colgroup>
    <col style="width:23%">
    <col style="width:17%">
    <col style="width:60%">
  </colgroup>
  <tbody>
    <tr>
      <td><strong>Column Name</strong></td>
      <td><strong>Sort-able?</strong></td>
      <td><strong>Description</strong></td>
    </tr>
    ...
  </tbody>
</table>
```

Per `specification-writing-guideline.md` §6.4: include the default
sort line in the description when applicable:
*"By default, the list is sorted &lt;sorted type&gt; by this column"*.

Each row's Column Name cell ends with `(ATC #<n>)` to link back to the
ATC entry whose feature owns this list.

### 2.3 Search (5 columns — canonical)

```html
<table border="1">
  <colgroup>
    <col style="width:20%">
    <col style="width:20%">
    <col style="width:20%">
    <col style="width:20%">
    <col style="width:20%">
  </colgroup>
  <tbody>
    <tr>
      <td><strong>Field Name</strong></td>
      <td><strong>Type</strong></td>
      <td><strong>Available Options</strong></td>
      <td><strong>Default Value</strong></td>
      <td><strong>Field Behavior</strong></td>
    </tr>
    ...
  </tbody>
</table>
```

Field Name ends with `(ATC #<n>)`.

### 2.4 Form (6 columns — canonical)

```html
<table border="1">
  <colgroup>
    <col style="width:16%">
    <col style="width:14%">
    <col style="width:13%">
    <col style="width:16%">
    <col style="width:19%">
    <col style="width:22%">
  </colgroup>
  <tbody>
    <tr>
      <td><strong>Field Name</strong></td>
      <td><strong>Type</strong></td>
      <td><strong>Default Value</strong></td>
      <td><strong>Validation(s)</strong></td>
      <td><strong>Validation Message(s)</strong></td>
      <td><strong>Field Behavior</strong></td>
    </tr>
    ...
  </tbody>
</table>
```

- `Validation(s)` and `Validation Message(s)` cells use `-` prefixes
  for multiple items, NOT `<ul>` (per canonical §2.4 Form note).
- **No** `<img>` inside any cell (per canonical §2.4 Form note —
  highlighted red in the guideline).
- **No** `Save` / `Cancel` rows (per canonical §2.4 Form note).
- Field Name ends with `(ATC #<n>)` followed by the parenthetical
  Jira-key list (e.g. `Pay Grade (ATC #4) (CM-2)` per `SKILL.md`
  §5-C.3 step 3).

### 2.4-bis Form-table cell-alignment rule (strict 6-cell rows)

Every Form-table **data** row MUST author exactly **6 `<td>` cells** in
the canonical header order — Field Name, Type, Default Value,
Validation(s), Validation Message(s), Field Behavior — **even when one
or more of those cells has no content**. Empty cells render as `—`
(em-dash, U+2014), NOT as truly empty `<td></td>` and NOT as collapsed
cells.

**Why:** BookStack rendering of a `<tr>` with only 4 or 5 `<td>` cells
silently shifts every subsequent cell one column to the left. A row
that intended `Field Name | Type | Default | (empty) | (empty) | Behavior`
ends up rendering as `Field Name | Type | Default | Behavior | (blank) | (blank)`
— the `Behavior` content visually sits under the `Validation(s)`
header, looking misaligned. The `—` placeholder forces every column to
materialise.

**Canonical Form row rendering (correct shape):**

```html
<!-- correct: 6 cells, em-dash placeholders for empty Validation cells,
     <ul><li> bullet form in the Field Behavior cell — one li per
     distinct behaviour point per release-filter-policy.md §10.3 /
     SKILL.md §5-C.2 / specification-writing-guideline.md §2.2 -->
<tr>
  <td>Pay Grade (ATC #4) (CM-2)</td>
  <td>Dropdown</td>
  <td>--Select--</td>
  <td>—</td>
  <td>—</td>
  <td><ul><li>Displays available pay grades for selection.</li><li>Soft-deleted pay grades (marked "(Deleted)") do not appear in this dropdown.</li></ul></td>
</tr>
```

```html
<!-- correct: even a single-behaviour cell still uses <ul><li> for
     vertical-shape consistency with every other Form row -->
<tr>
  <td>Currency (ATC #6) (CM-2)</td>
  <td>Dropdown</td>
  <td>--Select--</td>
  <td>—</td>
  <td>—</td>
  <td><ul><li>Based on the selected currency in this field, the currency symbol appears in all amount fields within the Salary tab.</li></ul></td>
</tr>
```

```html
<!-- WRONG #1: omitting empty validation cells (4 cells instead of 6)
     — DO NOT do this. The Field Behavior content slides under the
     Validation(s) header on render. -->
<tr>
  <td>Pay Grade (ATC #4) (CM-2)</td>
  <td>Dropdown</td>
  <td>--Select--</td>
  <td>Displays available pay grades for selection; soft-deleted pay grades (marked "(Deleted)") do not appear in this dropdown.</td>
</tr>
```

```html
<!-- WRONG #2: plain-text Field Behavior (no <ul><li>) — DO NOT do this.
     Mixing plain-text and bulleted rows in the same column produces
     visually inconsistent vertical spacing and bullet visibility. -->
<tr>
  <td>Currency (ATC #6) (CM-2)</td>
  <td>Dropdown</td>
  <td>--Select--</td>
  <td>—</td>
  <td>—</td>
  <td>Based on the selected currency in this field, the currency symbol appears in all amount fields within the Salary tab.</td>
</tr>
```

**Multi-item validation cells** (the only Form-table exception to the
bullet rule) use `-` (hyphen + space) prefix lines separated by `<br>`,
per §2.4 Form note. Example:

```html
<td>- Required<br>- Maximum length: 50 characters<br>- Allowed characters: alphanumeric + space</td>
```

Enforced by `SKILL.md` STEP 6 check #8 (6-cell alignment) AND check #14
(bullet-form free-text cells, including Form Field Behavior). Both
checks FAIL the run if violated; the routine refuses to PUT the page.

### 2.5 Audit Trail (3 columns — canonical)

```html
<table border="1">
  <colgroup>
    <col style="width:5%">
    <col style="width:45%">
    <col style="width:50%">
  </colgroup>
  <tbody>
    <tr>
      <td class="align-center"><strong>#</strong></td>
      <td><strong>Action</strong></td>
      <td><strong>How it is tracked in Audit Trail</strong></td>
    </tr>
    <tr>
      <td class="align-center">1</td>
      <td>ADD Working Weekend (ATC #4)</td>
      <td>...</td>
    </tr>
  </tbody>
</table>
```

The Action cell ends with `(ATC #<n>)`. The "How it is tracked" cell
uses the canonical multi-paragraph format (Section / Performed Screen
/ Action Description / Sample Audit), per the example in
`specification-writing-guideline.md` §2.4 Audit Trail.

---

## 3. User Interfaces (UIs) — always last on page

Per canonical §4: *"User Interfaces should always be included at the
end of the specifications document. Each system screenshot must be
placed immediately after the corresponding screen name. The screen
name should be in a tiny header format."*

### 3.1 Structure

```html
<h2>User Interfaces (UIs)</h2>

<h6>Add Pay Grade Modal</h6>
<a href="https://enterprisewiki.orangehrm.com/uploads/images/.../add-pay-grade-modal.png">
  <img src="https://enterprisewiki.orangehrm.com/uploads/images/.../add-pay-grade-modal.png"
       alt="Add Pay Grade Modal">
</a>

<h6>Pay Grade List View</h6>
<a href="https://enterprisewiki.orangehrm.com/uploads/images/.../pay-grade-list.png">
  <img src="https://enterprisewiki.orangehrm.com/uploads/images/.../pay-grade-list.png"
       alt="Pay Grade List View">
</a>

<h6>Design References</h6>
<p>
  <strong>Figma:</strong> <a href="https://figma.com/file/...">Compensation UI v8.0</a><br>
  <strong>Sketch:</strong> <a href="https://sketch.cloud/s/...">Pay Grade detail flow</a><br>
</p>
```

### 3.2 Heading level

`<h6>` (tiny header) for screen names — and **only** `<h6>`. Never
`<h4>`, `<h5>`, `<h3>`, list-item `UI 1: ...` prefixes, or inline
`<strong>UI:</strong>` labels.

### 3.2-bis UI section purity — h6+image pairs ONLY

The UI section is a **gallery**, not a narrative. Authored content is
strictly limited to:

- One `<h2>User Interfaces (UIs)</h2>` heading at the start.
- Repeating `<h6>{Topic}</h6>` + `<a href><img></a>` pairs, one per
  screen. The image MUST immediately follow its `<h6>` with no
  intervening tags.
- An optional `<h6>Design References</h6>` sub-block at the end with
  external design-tool links wrapped in **one** `<p><strong>Figma:</strong>
  <a href>...</a></p>` element.

**Forbidden inside the UI section** (authored content):

- `<p>` paragraphs of any kind — except the single `<p>` inside the
  Design References sub-block.
- `<ul>` / `<ol>` / `<li>` lists.
- `<table>` of any kind.
- Heading levels other than `<h6>` (no `<h4>`, `<h5>`, `<h3>`).
- Inline `<strong>` / `<em>` labels around images (`<strong>UI:</strong>`,
  `<em>Figure 1:</em>`, etc.).
- Narrative connective text between an `<h6>` and its image, or
  between consecutive `<h6>+<img>` pairs.

The image documents itself; the `<h6>` labels it. If the spec author
needs to describe what a screen does, that explanation belongs in the
**Scenario** column of the ATC table (as a bullet), not in the UI
section. See `release-filter-policy.md` §11.1-bis for the policy-level
statement and §11.1-ter for the topic-name source priority (Jira
description heading → bold label → filename → story title → generic
fallback with warning).

### 3.3 Image embed

`<a href="{URL_FULL}">` wraps `<img src="{URL_THUMB_DISPLAY}">` —
clicking opens the full-size asset; the page renders the scaled-display
variant inline. `alt=` is the screen name. No inline `style=`. No
`width=` / `height=` (BookStack scales via the thumbs URL).

**URLs must be BookStack-hosted.** The routine downloads every Jira
image binary, re-uploads it to BookStack via `/api/image-gallery`, and
uses the returned `url` (full-size) and `thumbs.display` (1680-scaled)
in the page HTML. The Atlassian attachment URL
(`api.atlassian.com/.../rest/api/3/attachment/content/<id>`) MUST
NEVER appear in the rendered page — it requires a Jira-authenticated
browser session and returns 403 to wiki readers. See
`release-filter-policy.md §11.1` and `SKILL.md` STEP 5-D step 2 for
the upload contract.

Pattern that ships:
```html
<h6>Add Pay Grade Modal</h6>
<a href="https://enterprisewiki.orangehrm.com/uploads/images/gallery/2026-05/abcimage.png">
  <img src="https://enterprisewiki.orangehrm.com/uploads/images/gallery/2026-05/scaled-1680-/abcimage.png"
       alt="Add Pay Grade Modal">
</a>
```

Pattern that DOES NOT ship (broken for readers):
```html
<img src="https://api.atlassian.com/.../rest/api/3/attachment/content/40235">
```

### 3.4 Idempotency / merge

See `release-filter-policy.md` §11.1 for the exact extract → compare →
replace/add algorithm. Match by lowercase filename. Replace updates
the `<a href>` AND the `<img src>` to the new URL while preserving the
`<h6>` text (unless the screen name itself has changed in Jira, in
which case both are updated). Wiki entries with no Jira counterpart
are preserved verbatim (additive merge).

---

## 4. Heading hierarchy (allowed elements)

| Tag | Authored this run? | Used for |
|---|---|---|
| `<h1>` | no | page title (BookStack manages from `name`) |
| `<h2>` | yes (once) | `User Interfaces (UIs)` — that's it |
| `<h3>` | no | only on legacy / pre-canonical content; preserved verbatim |
| `<h4>` | no | only on legacy content; preserved verbatim. Forbidden in new authored content. |
| `<h5>` | no | only on legacy content; preserved verbatim |
| `<h6>` | yes | screen name inside the User Interfaces (UIs) section |

The routine authors exactly two heading levels: `<h2>User Interfaces (UIs)</h2>`
(once, at end of page) and `<h6>{Screen Name}</h6>` (one per UI asset
inside that section). Everything else lives inside the 5 canonical
tables.

---

## 5. HTML hygiene

### 5.1 Escaping
HTML-escape `<`, `>`, `&` inside text content. Convert Jira ADF
markup to safe HTML — strip any inline `style=` from rich-text spans
(other than the canonical colgroup `style="width:N%"` widths and the
canonical class `align-center` on Audit Trail # cells).

### 5.2 Permitted tags (authored content)
```
<table> <colgroup> <col> <tbody> <tr> <td>
<ul> <li>
<strong> <em>
<a href> <img>
<h2> <h6>
<p> <br>
```

`<ul>` / `<li>` are REQUIRED inside the free-text cells of the ATC,
List, Search, Form (Field Behavior only), and Audit Trail tables — one
`<li>` per distinct test case / behavior point, per
`specification-writing-guideline.md` §2.2. They remain **forbidden**
inside the Form table's `Validation(s)` and `Validation Message(s)`
columns (those use `-`-prefixed plain-text lines per the §2.4 Form
note — the canonical exception to the bullet rule).

Pre-existing legacy content on the page may contain other tags
(`<h3>`, `<h4>`, `<ul>`, `<ol>`, `<li>`, etc.). The routine preserves
all of it verbatim. The list above is what the routine itself emits.

### 5.3 No change markers
The routine **never** authors:
- `style="background-color: ..."` / `style="background: ..."` —
  no yellow tints, no diff highlights.
- `[New — KEY]` / `[Updated — KEY]` / `[Retired — KEY]` inline tags.
- `<span class="diff-...">` or any kind of diff annotation.

### 5.4 Forbidden in authored content
- Any new section heading outside `<h2>User Interfaces (UIs)</h2>` and
  `<h6>{Screen Name}</h6>`.
- Tables outside the canonical 5 (ATC / List / Search / Form / Audit
  Trail).
- Column counts other than 4 / 3 / 5 / 6 / 3 (ATC includes the
  appended Release column).
- `<img>` inside any `<td>` (canonical §2.4 Form note).
- `Save` / `Cancel` rows in Form tables (canonical §2.4 Form note).
- `<ul>` / `<ol>` inside the Form table's `Validation(s)` or
  `Validation Message(s)` columns specifically — those use `-`-prefixed
  plain-text lines per canonical §2.4 Form note. (Note: `<ul>` / `<li>`
  are REQUIRED for every other free-text cell across all canonical
  tables per §5.2 — the Form validation columns are the only exception.)
- `<h2>{fixVersion}</h2>` release-section organizers.
- `<h4>Overview</h4>` / `<h4>Business Requirement</h4>` /
  `<h4>Expected System Behavior</h4>` / `<h4>Rules / Validations</h4>` /
  `<h4>User Stories</h4>` / `<h4>Acceptance Criteria</h4>` /
  `<h4>Interfaces (UIs)</h4>` / `<h4>Notes / Dependencies / Limitations</h4>`.
  These are the invented prose schema the routine accidentally adopted
  on 2026-05-16 and must never re-appear.

---

## 6. Validation checklist (mirror of SKILL.md STEP 6)

Every authored output must satisfy:

- [ ] Authored tables match exactly one of the 5 canonical shapes
      (ATC 4-col / List 3-col / Search 5-col / Form 6-col / Audit 3-col).
- [ ] ATC header row is exactly `# | Feature | Scenario | Release`.
- [ ] Every non-ATC table row's leftmost cell carries an `(ATC #<n>)`
      suffix linking it to an ATC entry.
- [ ] Every authored row's Feature / Action / Field-Name cell that
      represents a Jira-sourced item ends with `(<JIRA-KEY>)` for
      idempotent re-matching.
- [ ] No two ATC rows share the same `(<JIRA-KEY>)` suffix.
- [ ] No `<h2>` / `<h3>` / `<h4>` / `<h5>` authored *outside* the
      single `<h2>User Interfaces (UIs)</h2>` heading.
- [ ] All `<h6>` we authored sit inside the UI section.
- [ ] UI section contains zero `<ul>` / `<ol>` (no list-item UI captions).
- [ ] No `<img>` inside any `<td>`.
- [ ] No `Save` / `Cancel` rows in Form tables.
- [ ] No `style="background-color: ..."` and no change-marker inline
      tags.
- [ ] Every `<h2>` / `<h3>` / `<h4>` text present in `PRIOR_HTML` is
      still present in `NEW_HTML` (additive merge — never delete
      legacy content).
- [ ] Re-running STEP 5 against `NEW_HTML` produces byte-identical
      output (idempotency).
- [ ] No two rows in the ATC table share the same normalized Feature
      name after stripping the parenthetical key list and applying
      synonym folding (per `SKILL.md` §5-C.1).
- [ ] No two rows in the List / Search / Form / Audit Trail tables
      share the same normalized leftmost-cell name (`Column Name`,
      `Field Name`, `Field Name`, `Action` respectively) after synonym
      folding.
- [ ] No Jira key appears in more than one ATC row's parenthetical key
      list (a missed dedup match would surface here).
- [ ] Every field, action, or topic mentioned in this run's eligible
      Jira issues appears in every applicable canonical table per
      `specification-writing-guideline.md` §2.6 (cross-table
      field-completeness).
- [ ] Every ATC `Scenario` cell, every List `Description` cell, every
      Search `Field Behavior` cell, every Form `Field Behavior` cell,
      and every Audit Trail `How it is tracked in Audit Trail` cell
      is a `<ul>` containing one or more `<li>` items — one bullet per
      distinct test case / behavior point — per `SKILL.md` STEP 6
      check #14 and `specification-writing-guideline.md` §2.2. No
      paragraph-form cells; no multi-test-case run-on bullets.
- [ ] Form `Validation(s)` and `Validation Message(s)` columns use
      `-`-prefixed plain-text lines (NOT `<ul>` / `<li>`) per the §2.4
      Form note — the only canonical exception to the bullet rule.

---

## 7. Common mistakes (do NOT do)

- Authoring `<h2>8.0</h2>` / `<h2>8.0.2</h2>` release organizers.
  fixVersion lives ONLY in the Release column on ATC.
- Authoring `<h3>{Story Title} ({KEY})</h3>` story sections. Stories
  appear as ATC table rows, not heading-anchored sections.
- Authoring `<h4>Overview</h4>` (or any of the prose sub-section
  headings). These are invented and forbidden — the routine made this
  mistake on 2026-05-16.
- Authoring per-story `<h4>Interfaces (UIs)</h4>`. All UIs go in the
  ONE global UI section at the end of the page.
- Captioning UIs as `UI 1: ...` list items. Use `<h6>{Screen Name}</h6>`
  + linked `<img>` per canonical §4.
- Embedding `<img>` inside a `<td>`.
- Adding `Save` / `Cancel` rows to a Form table.
- Highlighting changes with yellow `<tr style="background-color:#fff7d6;">`
  or inline `[New — KEY]` spans.
- Re-authoring or re-shaping pre-existing legacy content. Existing
  content stays verbatim; new content appends.
- Creating a new ATC row for `Audit Log` or `Audit History` when
  `Audit Trail` already exists — they are the same feature per
  `SKILL.md` §5-C.1. Update the existing row's Scenario and append
  the new Jira key to its key list instead.
- Splitting one feature across multiple ATC rows because two Jira
  stories used slightly different wordings (e.g. `Salary Screen` vs
  `Salary Structure`). Merge to one row; the Scenario cell carries
  the latest released wording per `SKILL.md` §5-C.2.
- Adding a Form / Search / Audit Trail / List row without first
  checking whether the field/action/column already has a row in that
  table. The semantic-match step in `SKILL.md` §5-C.3 exists to
  prevent this — match cell is `Field Name` for Form/Search,
  `Action` for Audit Trail, `Column Name` for List.
- Writing the Scenario / Description / Field Behavior / Audit-tracking
  cell as a paragraph instead of a `<ul>` of `<li>` items. The
  guideline §2.2 mandates bullets for multi-detail table cells. The
  CM run on 2026-05-17 made this mistake (rows `Pay Grade Soft Delete
  (CM-2)`, `Salary Structure (CM-3, CM-27)`, `Add Employee Wizard
  Salary (CM-19)` shipped as paragraphs); subsequent runs repair them
  per `SKILL.md` §5-C.2 step 1 (legacy paragraph-form repair).
- Cramming multiple distinct test cases into a single `<li>`. Each
  bullet is one assertion a QA engineer would verify in one test
  pass — split the run-on bullet into separate items.
