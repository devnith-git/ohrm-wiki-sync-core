# Specification Writing Guideline

### 1. Document Formatting

#### 1.1 Title &amp; Headings

- Section Headers: Medium Header
- Subsections: Small Header
- Body Text: Paragraph

#### 1.2 Text Styling

- Bold : Use for emphasis on important terms
- *Italics*: Use for highlighting references or notes

### 2. Tables

#### 2.1 Table Guidelines

- Text size: Paragraph
- Header row: Bold text
- Content Alignment: Left

#### 2.2 List Formatting within Tables

- Use bullet points (`•`) for multiple details inside table cells

##### Sample bulleting

- - Level 1 detail 
    - - Level 2 detail

##### Numbering

**Main Section:** Represented by whole numbers (e.g., 1, 2, 3)

**Subsections:** Indicated by an additional decimal place (e.g., 1.1, 1.2, 2.1)

**Sub-subsections:** Further divisions are represented by a third level of numbering (e.g., 1.1.1, 1.2.1)

### 2.4 Tables

#### Acceptance Test Cases 


<table border="1" id="bkmrk-%23-feature-scenario" style="width: 115.309%;"><tbody><tr><td style="width: 15.1413%;">**\#**  
</td><td style="width: 42.3957%;">**Feature**  
</td><td style="width: 42.3957%;">**Scenario**  
</td></tr><tr><td style="width: 15.1413%;">  
</td><td style="width: 42.3957%;">  
</td><td style="width: 42.3957%;">  
</td></tr></tbody></table>

- Acceptance test cases table typically include the feature name, a detailed scenario describing how the functionality should work, and the steps required to execute the test case.
- Any table added, apart from the "Acceptance Test Cases" table, must be linked to an entry within the "Acceptance Test Cases" table.
- Any other table added, should be related to an item in the "Acceptance Test Cases" table.

#### List 

<table border="1" id="bkmrk-column-name-sort-abl" style="border-collapse: collapse; width: 100%; height: 59.7334px;"><colgroup><col style="width: 22.8668%;"></col><col style="width: 16.3485%;"></col><col style="width: 60.7806%;"></col></colgroup><tbody><tr style="height: 29.8667px;"><td style="height: 29.8667px;">**Column Name**  
</td><td style="height: 29.8667px;">**Sort-able?**  
</td><td style="height: 29.8667px;">**Description**  
</td></tr><tr style="height: 29.8667px;"><td style="height: 29.8667px;">  
</td><td style="height: 29.8667px;">  
</td><td style="height: 29.8667px;">  
</td></tr></tbody></table>

- The List table includes the details of the lists which are shown in the system.

#### Search 

<table border="1" id="bkmrk-field-name-type-avai" style="border-collapse: collapse; width: 100%; height: 119px;"><colgroup><col style="width: 20%;"></col><col style="width: 20%;"></col><col style="width: 20%;"></col><col style="width: 20%;"></col><col style="width: 20%;"></col></colgroup><tbody><tr><td>**Field Name**  
</td><td>**Type**  
</td><td>**Available Options**  
</td><td>**Default Value**  
</td><td>**Field Behavior**  
</td></tr><tr><td>  
</td><td>  
</td><td>  
</td><td>  
</td><td>  
</td></tr></tbody></table>

- The Search table includes the details of the search/filter sections in the system.

#### Form 

<table border="1" id="bkmrk-field-name-type-defa" style="border-collapse: collapse; width: 100%; height: 76.1528px;"><colgroup><col style="width: 15.9417%;"></col><col style="width: 14.088%;"></col><col style="width: 12.8522%;"></col><col style="width: 16.3124%;"></col><col style="width: 19.1547%;"></col><col style="width: 21.7499%;"></col></colgroup><tbody><tr style="height: 46.4722px;"><td style="height: 46.4722px;">**Field Name**  
</td><td style="height: 46.4722px;">**Type**  
</td><td style="height: 46.4722px;">**Default Value**  
</td><td style="height: 46.4722px;">**Validation(s)**</td><td style="height: 46.4722px;">**Validation Message(s)**  
</td><td style="height: 46.4722px;">**Field Behavior**  
</td></tr><tr style="height: 29.6806px;"><td style="height: 29.6806px;">  
</td><td style="height: 29.6806px;">  
</td><td style="height: 29.6806px;">  
</td><td style="height: 29.6806px;">  
</td><td style="height: 29.6806px;">  
</td><td style="height: 29.6806px;">  
</td></tr></tbody></table>

- The form table includes the details of the forms in the system.
- Multiple details included in “Validations” and “validations messages” columns should be included using "-" characters instead of bullet points.
- <span style="color: rgb(186, 55, 42);">Content in the table should not contain images.</span>
- <span style="color: rgb(186, 55, 42);">Save and cancel buttons should not be included as form inputs.</span>
- **Every Form data row MUST have exactly 6 cells**, one per canonical column in this order: Field Name, Type, Default Value, Validation(s), Validation Message(s), Field Behavior. Even when a cell has no content (e.g. a Dropdown with no validation rules), the cell MUST exist and MUST display `—` (em-dash) as a placeholder. Skipping empty cells causes BookStack to shift every subsequent cell one column to the left, so the Field Behavior content visually sits under the Validation(s) header (this is the alignment symptom reported by spec authors on 2026-05-18).
- **The Field Behavior cell uses `<ul><li>` bullet form per §2.2**, with one `<li>` per distinct behaviour point — never plain text, never a single `<li>` containing multiple behaviours joined by `;` or `. `. A cell with a single behaviour still uses `<ul><li>...</li></ul>` for vertical-shape consistency with every other Form row in the same column. Mixing plain-text and bulleted Field Behavior cells in the same Form table produces visually inconsistent rows (different vertical spacing, different bullet visibility) and breaks the column-as-a-scannable-stack reading pattern. This rule applies identically to: ATC `Scenario`, List `Description`, Search `Field Behavior`, Form `Field Behavior`, Audit Trail `How it is tracked in Audit Trail`. The Form `Validation(s)` and `Validation Message(s)` columns are the only canonical exception — they use `-`-prefixed plain-text lines separated by `<br>`, per the §2.4 Form note above.

#### Audit Trail

<table border="1" id="bkmrk-screen-name-actions-" style="border-collapse: collapse; width: 100%; height: 329px;"><colgroup><col style="width: 4.82324%;"></col><col style="width: 45.1026%;"></col><col style="width: 50.0494%;"></col></colgroup><tbody><tr style="height: 29.6px;"><td class="align-center" style="height: 29.6px;">**\#**</td><td style="height: 29.6px;">**Action**</td><td style="height: 29.6px;">**How it is tracked in Audit Trail**</td></tr><tr style="height: 299.4px;"><td class="align-center" style="height: 299.4px;">1</td><td style="height: 299.4px;">ADD Working Weekend</td><td style="height: 299.4px;">**"Section:** Working Weekend  
**Performed Screen:** Working Weekend

**Action Description:**  
&lt;Working weekend name&gt; &lt;Date&gt; is created as a &lt;full day/half day&gt; Working Weekend with shift in time as &lt;Shift in Time&gt; and shift out time as &lt;Shift out time&gt;. This is applicable for the following location(s) in &lt;Country&gt; : &lt;Location&gt;"

**<span style="text-decoration: underline;">Sample Audit:</span>**

Chinese Working day (2025-04-19) is created as a full day Working Weekend with shift in time as 09:00 and shift out time as 17:00. This is applicable for the following location(s) in China : Chinese Center.

</td></tr></tbody></table>

### 2.5 De-duplication rule (universal — applies to every canonical table)

Before adding any new row to any canonical table (Acceptance Test Cases, List, Search, Form, Audit Trail), first check the existing table for the same feature / topic / field / action. **Do not create duplicate rows for the same item.**

The matching key is the leftmost named cell of each table:

| Table | Match cell |
|---|---|
| Acceptance Test Cases | **Feature** |
| List | **Column Name** |
| Search | **Field Name** |
| Form | **Field Name** |
| Audit Trail | **Action** |

#### Rule 1 — Existing feature/topic available

If the feature, field, or topic already exists in the canonical table:

- **Keep** the existing row (preserve the `#` and the existing parenthetical Jira-key list).
- **Update** the Scenario / Description / Field Behavior / How it is tracked column with the newly identified released behavior.
- **Merge** the new scenario with the existing one clearly. Preserve existing valid test coverage — never drop sentences from the prior content just because the latest Jira description omits them.
- **Append** the new contributing Jira key to the parenthetical key list (e.g. `Audit Trail (CM-100)` becomes `Audit Trail (CM-100, CM-200)`).
- Do NOT duplicate the row.

#### Rule 2 — New feature/topic not available

If the feature, field, or topic is not already in the table:

- **Add** a new row at the end.
- Map the new Feature / Topic / Field / Action correctly onto the canonical column shape.
- Add the matching Scenario / Description / Field Behavior.
- The leftmost cell ends with the Jira issue key in parentheses (e.g. `Pay Grade Soft Delete (CM-2)`).
- Follow the existing table structure exactly — do NOT add extra columns.

#### Rule 3 — Duplicate prevention by semantic name

Use the Feature / Topic / Field name as the main matching point. If the wording is slightly different but the meaning is the same, treat them as the same item.

Examples that MUST collapse to one row:

- "Audit Trail" / "Audit Log" / "Audit History" / "Activity Log" / "Change History"
- "Pay Grade" / "Salary Grade" / "Compensation Grade"
- "Search" / "Filter" / "Filters" / "Search & Filter"
- "List View" / "Grid View" / "Table View"

These should NOT become separate rows unless the specification clearly treats them as separate features (e.g. distinct scopes within the same project).

When in doubt, lean toward **merge** rather than split — merging is reversible if the next iteration discovers the items really were separate; splitting creates duplicates that someone has to consolidate manually.

#### Rule 4 — Scenario reflects the latest released behavior (bullet-form)

The Scenario / Description / Field Behavior column is always rendered as a **bulleted list** per §2.2 — one bullet per distinct test case / behavior point. It should always reflect the **latest released behavior** from Jira. If multiple Jira issues belong to the same existing feature / topic, **merge their bullets** within the same row instead of creating duplicate feature rows.

Bullet-level guidance:

- If a new bullet is byte-equivalent to one already in the cell → no change.
- If a new bullet describes the same test case with updated wording (e.g. `Salary Screen` → `Salary Structure`) → replace the matching bullet in place.
- If a new bullet describes a new test case for the same feature → append it as a new `<li>` at the end of the list.
- Existing bullets that the latest Jira description doesn't repeat are **kept verbatim** — they represent earlier-confirmed released behavior. Never silently drop a bullet to shrink the list.
- Two-level nesting (per §2.2 *Sample bulleting*) is allowed when a bullet needs sub-detail; otherwise keep bullets flat (Level 1 only).
- The Form table's `Validation(s)` and `Validation Message(s)` columns are the canonical exception to this rule — they use `-`-prefixed plain-text lines (per §2.4 Form note), not `<ul>` / `<li>`.

#### Rule 5 — Final validation before saving

Before publishing the updated page, review every canonical table on the page and confirm:

- No duplicate Feature / Topic / Field / Action rows were created.
- Existing rows were updated where applicable.
- New rows were added only for genuinely new features / topics / fields.
- The Scenario / Description / Field Behavior column reflects the correct, latest released behavior.

The routine implementation of this rule lives in `SKILL.md` §5-C.1 / §5-C.2 / §5-C.3 and is enforced by `SKILL.md` STEP 6 validation checks #12 / #13 / #14.

### 2.6 Cross-table field-completeness (universal)

When a Jira issue mentions a field, button, or action by name, that item MUST appear in **every applicable** canonical table:

- If the field is filtered or searched on → **Search** table.
- If the field appears in an add / edit form → **Form** table.
- If the field's create / update / delete is audited → **Audit Trail** table.
- If the field is a column on a list view → **List** table.

If the field is described by Jira but missing from an applicable table, the routine MUST add it (per §2.5 Rule 2) in the same run. Cross-table completeness keeps the spec page in a consistent state across runs.

The routine implementation lives in `SKILL.md` §5-C.4.

### 3. Icons &amp; Links Usage

#### 3.1 Icons

<table border="1" id="bkmrk-enable%2Fdisable-check" style="border-collapse: collapse; width: 58.7654%; height: 79.45px;"><colgroup><col style="width: 45.0349%;"></col><col style="width: 10.5182%;"></col><col style="width: 44.6179%;"></col></colgroup><tbody><tr style="height: 29.6px;"><td class="align-center" style="height: 29.6px;">Navigation</td><td class="align-center" style="height: 29.6px;">→</td><td style="height: 29.6px;">Arrow</td></tr></tbody></table>

#### 3.1 Links

- Links should be in bold text format.

[![image.png](https://enterprisewiki.orangehrm.com/uploads/images/gallery/2025-02/scaled-1680-/iOkimage.png)](https://enterprisewiki.orangehrm.com/uploads/images/gallery/2025-02/iOkimage.png)

### 4. User Interfaces (UIs) Section

- User Interfaces should always be included at the end of the specifications document.
- Each system screenshot must be placed immediately after the corresponding screen name.
- The screen name should be in a tiny header format for consistency.
- **The UI section is a gallery, not a narrative.** It contains only screen name + screenshot pairs (and an optional Design References sub-block at the end for Figma / Sketch / external design-tool links).
- **No paragraph descriptions, captions, or narrative text inside the UI section.** Do not write what a screen does between the screen name and the image, or between consecutive entries. If a behaviour explanation is needed, it belongs as a bullet in the **Scenario** column of the corresponding **Acceptance Test Cases** row (per §2.4), not in the UI section.
- The **screen name (UI topic)** is a short noun-phrase label that names the screen — e.g. `Salary History`, `Pay Grade Configuration`, `Add Employee Wizard — Salary`. **Never** a sentence or description. Source priority for the topic name (from Jira, in order):
    1. Heading text immediately preceding the image in the Jira description (preferred).
    2. Bold/strong label in the same description paragraph (`**Salary History:** ![]()`).
    3. Image filename in title case (`salary-history.png` → "Salary History").
    4. Jira story title, cleaned.
    5. Generic fallback (e.g. "Untitled UI 1") — the spec author should fix the Jira description to provide a real heading; routines log a warning when they have to use this level.
- Routine implementation lives in `resources/release-filter-policy.md` §11.1 / §11.1-bis / §11.1-ter and is enforced by `resources/SKILL.md` STEP 6 check #7.

### 5. Configurations

#### 5.1 Frontend Configurations

- Frontend configurations related to a screen should be included in the specification document itself.

#### 5.2 Backend Configurations

- Backend configurations for a screen's functionality should be linked to the corresponding specifications page that details those configurations.

### 6. General Guidelines

#### 6.1 Content Style

- The content of the specification document should be written in simple present tense.

#### 6.2 Exclusions

- Tooltips of the system should not be included.

#### 6.3 Navigation Paths

- Example for a navigation path is "**HR Administration → Manage User Roles".**
- Navigation Paths of the screen should be in bold format.
- If a navigation path to a different screen is included (other than the screen for which the spec is being written), it should be linked to the relevant spec. The link should open in a new window and the navigation path should not be in bold format.

#### 6.4 List Views

When including a list view in the system:

- The default sorting of the relevant column should be included in the following format: 
    - "By default, the list is sorted &lt;sorted type&gt; by this column"

#### 6.5 Formatting of UI Elements

- When including the content of a label, button, title, etc., the content should be enclosed within inverted commas (e.g. "Save", "Assign")

#### 6.5 Test Cases and UI Screenshots  


- Test cases should not be linked with UI screenshots. 
    - Components where the content cannot be included as a separate section in the specification document can be linked.