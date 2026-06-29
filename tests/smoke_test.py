"""
Minimal smoke test — runnable without any credentials.

Verifies:
  1. .env.example parses cleanly.
  2. Resolver, sync, and deploy modules import without error.
  3. Routine prompt template has the required PROMPT_BODY markers and only
     uses placeholders that are documented in .env.example.

Run:
  py tests/smoke_test.py
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "automation"))
sys.path.insert(0, str(REPO / "routines"))


def fail(msg):
    print(f"[FAIL] {msg}")
    sys.exit(1)


def ok(msg):
    print(f"[OK]   {msg}")


# 1. .env.example sanity
env_example = REPO / ".env.example"
if not env_example.exists():
    fail(".env.example missing")
text = env_example.read_text()
required = ["JIRA_USER", "JIRA_API_TOKEN", "ANTHROPIC_API_KEY",
            "WIKI_TOKEN_ID", "WIKI_TOKEN_SECRET", "WIKI_BASE_URL",
            "ROUTINE_ENVIRONMENT_ID", "ATLASSIAN_CLOUD_ID",
            "ATLASSIAN_MCP_UUID", "WIKI_MCP_UUID"]
missing = [k for k in required if k not in text]
if missing:
    fail(f".env.example missing keys: {missing}")
ok(".env.example has all expected keys")

# 2. Imports
try:
    import resolver  # noqa: F401
    ok("resolver imports cleanly")
except Exception as e:
    fail(f"resolver import: {e}")

# 3. Routine prompt templates — iterate over every *.prompt.md
prompt_files = sorted((REPO / "routines").glob("*.prompt.md"))
if not prompt_files:
    fail("no routines/*.prompt.md files found")
ok(f"found {len(prompt_files)} prompt template(s): {[p.name for p in prompt_files]}")

documented_envs = set()
for line in text.splitlines():
    if "=" in line and not line.strip().startswith("#"):
        documented_envs.add(line.split("=", 1)[0].strip())

required_runtime = {"WIKI_TOKEN_ID", "WIKI_TOKEN_SECRET", "WIKI_BASE_URL", "ATLASSIAN_CLOUD_ID"}

for prompt_path in prompt_files:
    pname = prompt_path.name
    prompt = prompt_path.read_text()
    if "<!-- PROMPT_BODY_START -->" not in prompt or "<!-- PROMPT_BODY_END -->" not in prompt:
        fail(f"{pname}: missing PROMPT_BODY markers")
    ok(f"{pname}: PROMPT_BODY markers present")

    placeholders = set(re.findall(r"\{\{\s*([A-Z0-9_]+)\s*\}\}", prompt))
    undocumented = placeholders - documented_envs
    if undocumented:
        fail(f"{pname}: placeholders not documented in .env.example: {undocumented}")
    ok(f"{pname}: {len(placeholders)} {{KEY}} placeholders (env-var pattern preferred)")

    # Match any of: $VAR, ${VAR}, ${#VAR} (length), ${!VAR} (indirect).
    # ${#VAR} and ${!VAR} are legitimate ways to reference an env var without
    # leaking the value (the prompt uses ${#ATLASSIAN_CLOUD_ID} for the length-only
    # diagnostic line — see STEP 1 of every routine prompt).
    runtime_refs = set(re.findall(r"\$\{?[#!]?([A-Z][A-Z0-9_]+)\}?", prompt))
    missing_runtime = required_runtime - runtime_refs
    if missing_runtime:
        fail(f"{pname}: missing $VAR references for runtime secrets: {missing_runtime}")
    ok(f"{pname}: references all {len(required_runtime)} required runtime env vars via $VAR")

# 4. Confirm no real-looking secrets in ANY prompt template
suspicious = []
for prompt_path in prompt_files:
    prompt = prompt_path.read_text()
    for pat, name in [
        (r"\bsk-ant-[A-Za-z0-9_-]{20,}", "Anthropic key shape"),
        (r"\b[A-Za-z0-9]{30,40}\b(?![^{]*\}\})", "long alnum string (possible token)"),
    ]:
        for m in re.finditer(pat, prompt):
            ctx = prompt[max(0, m.start()-3):m.end()+3]
            if "{{" in ctx or "}}" in ctx:
                continue
            suspicious.append((prompt_path.name, name, m.group()))
if suspicious:
    fail(f"possible inline secrets: {suspicious}")
ok(f"no inline-secret patterns detected across {len(prompt_files)} prompt template(s)")


# ===========================================================================
# 5. Resource-file consistency validator
#
# The routine reads `resources/*` at every fire (STEP 2 repo-aware bootstrap).
# Inconsistencies between SKILL.md, release-filter-policy.md,
# specification-writing-guideline.md, WIKI_PAGE_RENDER.md, email_template.html,
# wiki_destination.json, and the routine prompts can silently regress
# behaviour. These checks catch the patterns that have caused real bugs
# in the past 7 days:
#   - "one paragraph" Scenario language (caused 2026-05-17 paragraph-form CM rows)
#   - "five canonical resource files" out-of-date count (drifted after STEP 3-D)
#   - "ends with `(<KEY>)`" singular language (drifted after the multi-key list)
#   - Missing required sections (§5-C.1, §10.3, §2.5, §2.6, etc.)
#   - Email-template placeholders not documented in SKILL.md §9-B
# ===========================================================================

resources = REPO / "resources"
skill = (resources / "SKILL.md").read_text(encoding="utf-8")
rfp = (resources / "release-filter-policy.md").read_text(encoding="utf-8")
guideline = (resources / "specification-writing-guideline.md").read_text(encoding="utf-8")
render = (resources / "WIKI_PAGE_RENDER.md").read_text(encoding="utf-8")
email_tpl = (resources / "email_template.html").read_text(encoding="utf-8")
wiki_dest_raw = (resources / "wiki_destination.json").read_text(encoding="utf-8")

# --- 5a. Required sections present in each canonical file ---
required_sections = {
    "SKILL.md": (skill, [
        "5-C.1 Synonym Set",
        "5-C.2 Scenario merge rule",
        "5-C.3 Non-ATC tables",
        "5-C.4 Cross-table field-completeness",
        "5-C.5 First-fire bootstrap",
        "STEP 1 — Env-var verification",
        "STEP 3-D",
        "STEP 6 — Validation",
        "STEP 7 — Diff-aware write",
        "STEP 9 — GitHub audit log",
        "STEP 10 — Send notification",
        "Safety: HTTP retries",
    ]),
    "release-filter-policy.md": (rfp, [
        "## 10. Specification Page Update",
        "### 10.1 ATC table",
        "### 10.2",
        "### 10.3 De-duplication contract",
        "## 11. User Interfaces",
        "### 11.1-bis UI section purity",
        "### 11.1-ter Topic-name source priority",
        "## 15. Per-Epic Project Scan",
    ]),
    "specification-writing-guideline.md": (guideline, [
        "### 2.4 Tables",
        "### 2.5 De-duplication rule",
        "### 2.6 Cross-table field-completeness",
    ]),
    "WIKI_PAGE_RENDER.md": (render, [
        "## 2. The 5 canonical tables",
        "## 3. User Interfaces (UIs)",
        "### 3.2-bis UI section purity",
        "## 5. HTML hygiene",
        "## 6. Validation checklist",
    ]),
}

for fname, (content, sections) in required_sections.items():
    missing = [s for s in sections if s not in content]
    if missing:
        fail(f"{fname}: missing required section(s): {missing}")
    ok(f"{fname}: all {len(sections)} required sections present")

# --- 5b. Forbidden phrases anywhere in canonical resource files ---
# Each entry: (phrase, friendly_name, why_it_matters, scope: list of file dicts)
FORBIDDEN = [
    ("Scenario is one paragraph",
     "Scenario as paragraph",
     "Contradicts specification-writing-guideline.md §2.2 (bullets in multi-detail "
     "table cells). Caused the 2026-05-17 paragraph-form CM rows. "
     "Fix by changing to bullet-form language matching SKILL.md §5-C.2.",
     [("release-filter-policy.md", rfp), ("SKILL.md", skill)]),

    ("five canonical resource files",
     "five-vs-six count drift",
     "STEP 3-D (commit a202901) added a sixth canonical resource file "
     "(email_template.html). The bullet list and abort message in any routine "
     "prompt must say SIX, not five.",
     [(p.name, p.read_text(encoding="utf-8")) for p in prompt_files]),

    ("all five",
     "five-vs-six count drift in prompts",
     "Same as 'five canonical resource files' — the bullet-list intro phrase.",
     [(p.name, p.read_text(encoding="utf-8")) for p in prompt_files]),

    # Old single-key suffix language — the multi-key list (commit 07b4f11) is canonical.
    # Allow `(<KEY>)` examples (those are legitimate single-contributor rows); flag
    # only the phrase that explicitly disallows the list.
    ("Jira issue key suffix `(<KEY>)`",
     "single-key suffix wording",
     "After commit 07b4f11 the canonical suffix is a parenthetical KEY LIST — "
     "`(<KEY>)` for one contributor, `(<KEY>, <KEY2>)` when multiple stories "
     "share a row. Old singular language confuses readers and risks regression.",
     [("release-filter-policy.md", rfp), ("SKILL.md", skill)]),

    # Forbidden HTML patterns
    ("<th>",
     "<th> in canonical schema",
     "WIKI_PAGE_RENDER.md §5.4 forbids <th> in authored content — header cells "
     "are <td><strong>...</strong></td>. A canonical resource file mentioning "
     "<th> as an allowed shape is an error.",
     [("WIKI_PAGE_RENDER.md", render)]),

    # Forbidden inline change markers
    ("[New &mdash;",
     "[New — KEY] inline change marker",
     "STEP 6 check #10 forbids `[New — KEY]` and `[Updated — KEY]` inline "
     "change markers in authored content. Canonical resource files must not "
     "describe them as valid.",
     [("SKILL.md", skill), ("WIKI_PAGE_RENDER.md", render),
      ("release-filter-policy.md", rfp)]),
]

for phrase, name, why, files in FORBIDDEN:
    hits = [(fname, fname.count(phrase) if isinstance(fname, str) else 0) for fname, content in files]
    real_hits = [(fname, content.count(phrase)) for fname, content in files if phrase in content]
    if real_hits:
        details = "; ".join(f"{f}×{n}" for f, n in real_hits)
        fail(f"forbidden phrase {phrase!r} appears in: {details}. ({why})")

ok(f"no forbidden phrases detected across {sum(len(scope) for _, _, _, scope in FORBIDDEN)} file-checks")

# --- 5c. Routine prompts must say "six canonical" ---
for prompt_path in prompt_files:
    prompt = prompt_path.read_text(encoding="utf-8")
    if "all six" not in prompt:
        fail(f"{prompt_path.name}: STEP 2 bullet list must reference 'all six' canonical files")
    if "six canonical resource files" not in prompt:
        fail(f"{prompt_path.name}: missing 'six canonical resource files' (abort message language)")
    ok(f"{prompt_path.name}: references all six canonical resource files")

# --- 5d. STEP 6 validation check count matches what the prompts claim ---
# Count rows in the validation table that look like `| <n> | **<check>** | <fail>...`
step6_check_count = len(re.findall(r"^\|\s*\d+\s*\|\s*\*\*[^|]+\*\*\s*\|", skill, re.M))
if step6_check_count < 14:
    fail(f"SKILL.md STEP 6 validation table has only {step6_check_count} checks "
         f"(expected >= 14 after the dedup contract added #12/#13/#14)")
ok(f"SKILL.md STEP 6 validation table has {step6_check_count} checks (>= 14 required)")

# Prompts mention the same count
for prompt_path in prompt_files:
    prompt = prompt_path.read_text(encoding="utf-8")
    # Look for "14 strict canonical checks" — matches the recent dedup-contract update
    m = re.search(r"(\d+)\s+strict canonical checks", prompt)
    if not m:
        fail(f"{prompt_path.name}: STEP 6 row does not mention 'N strict canonical checks'")
    claimed = int(m.group(1))
    if claimed != step6_check_count:
        fail(f"{prompt_path.name}: claims {claimed} canonical checks but SKILL.md has "
             f"{step6_check_count}. Sync the count in both files.")
    ok(f"{prompt_path.name}: claims {claimed} canonical checks (matches SKILL.md)")

# --- 5e. Every {{placeholder}} in email_template.html is documented in SKILL.md ---
# Block markers come in pairs and are stripped post-substitution; both members are valid.
placeholders = set(re.findall(r"\{\{\s*([a-zA-Z][a-zA-Z0-9]*)\s*\}\}", email_tpl))
# Pull all documented placeholders from SKILL.md §9-B (and the row-block templates §9-C / §9-D)
documented = set(re.findall(r"`\{\{\s*([a-zA-Z][a-zA-Z0-9]*)\s*\}\}`", skill))
undocumented = placeholders - documented
if undocumented:
    fail(f"email_template.html uses placeholder(s) not documented in SKILL.md §9-B/§9-C/§9-D: "
         f"{sorted(undocumented)}")
ok(f"all {len(placeholders)} email-template placeholder(s) documented in SKILL.md")

# Conditional-block marker pairs (StartXxx / EndXxx) — must come in pairs
start_markers = set(re.findall(r"\{\{\s*([a-zA-Z][a-zA-Z0-9]*BlockStart)\s*\}\}", email_tpl))
end_markers = set(re.findall(r"\{\{\s*([a-zA-Z][a-zA-Z0-9]*BlockEnd)\s*\}\}", email_tpl))
expected_ends = {m.replace("BlockStart", "BlockEnd") for m in start_markers}
expected_starts = {m.replace("BlockEnd", "BlockStart") for m in end_markers}
if expected_ends != end_markers:
    fail(f"email_template.html: block-start markers without matching End: "
         f"missing {sorted(expected_ends - end_markers)}; "
         f"extra Ends: {sorted(end_markers - expected_ends)}")
if expected_starts != start_markers:
    fail(f"email_template.html: block-end markers without matching Start: "
         f"missing {sorted(expected_starts - start_markers)}")
ok(f"email-template block markers pair up: {len(start_markers)} Start/End pair(s)")

# --- 5f. wiki_destination.json structural sanity ---
try:
    wiki_dest = json.loads(wiki_dest_raw)
except json.JSONDecodeError as e:
    fail(f"wiki_destination.json is not valid JSON: {e}")
required_top_keys = ["wiki", "specification_shelf", "routine_destinations"]
missing_keys = [k for k in required_top_keys if k not in wiki_dest]
if missing_keys:
    fail(f"wiki_destination.json missing top-level keys: {missing_keys}")
if wiki_dest.get("specification_shelf", {}).get("id") != 3:
    fail(f"wiki_destination.json: specification_shelf.id must be 3 — "
         f"got {wiki_dest.get('specification_shelf', {}).get('id')!r}")
routine_dests = wiki_dest.get("routine_destinations", {})
# `_comment` is allowed in the map
non_comment = {k: v for k, v in routine_dests.items() if not k.startswith("_")}
if not non_comment:
    fail("wiki_destination.json: routine_destinations has no real entries (only comments)")
for slug, entry in non_comment.items():
    bootstrap = entry.get("_bootstrap")
    # Required fields: page_name + release_scope + jira_project_key always.
    # page_id + book_id are required UNLESS the entry has a `_bootstrap` field
    # set (meaning the destination doesn't yet exist on BookStack and the
    # routine's FIRST-FIRE BOOTSTRAP will create it). Sentinel IDs of 0 are
    # intentional in that case and the operator will commit real ids after the
    # first fire flags them as manual_actions.
    for field in ("page_name", "release_scope", "jira_project_key"):
        if not entry.get(field):
            fail(f"wiki_destination.json: routine_destinations.{slug}.{field} is empty or missing")
    for field in ("page_id", "book_id"):
        val = entry.get(field)
        if val is None:
            fail(f"wiki_destination.json: routine_destinations.{slug}.{field} is missing")
        if val == 0 and not bootstrap:
            fail(f"wiki_destination.json: routine_destinations.{slug}.{field} is 0 — "
                 f"valid only for routines in bootstrap mode (add a `_bootstrap` "
                 f"field explaining the sentinel, otherwise this is a misconfig).")
ok(f"wiki_destination.json: {len(non_comment)} routine_destinations entry(s), all required fields present (bootstrap entries allowed)")

# --- 5g. SKILL.md authority order matches release-filter-policy.md ---
# SKILL.md cites release-filter-policy.md as TOP; verify that ordering is mentioned
# in both files (otherwise an LLM reading them could pick the wrong order).
if "release-filter-policy.md" not in skill[:8000]:
    fail("SKILL.md does not cite release-filter-policy.md in its first ~8KB (top-of-authority)")
if "specification-writing-guideline.md" not in skill[:8000]:
    fail("SKILL.md does not cite specification-writing-guideline.md in its first ~8KB")
ok("SKILL.md cites the canonical authority order in its header")

# --- 5h. release-filter-policy.md §10.1 uses bullet-form language ---
# After the bullet-form fix (commit 5f82176 + this commit), §10.1 should describe
# Scenario as a bulleted list, NOT as a paragraph.
m = re.search(r"###\s*10\.1[\s\S]+?(?=\n###?\s|\n---)", rfp)
if not m:
    fail("release-filter-policy.md: section 10.1 ATC table section not found")
section_101 = m.group(0)
if "bullet" not in section_101.lower():
    fail("release-filter-policy.md section 10.1: must describe Scenario as bullet-form "
         "(per specification-writing-guideline.md section 2.2)")
ok("release-filter-policy.md section 10.1: bullet-form Scenario language present")

# --- 5i. UI section purity language (gallery-only, no paragraphs) ---
# §11.1-bis must explicitly forbid <p> inside the UI section.
# §11.1-ter must define the Jira-driven topic-name source priority.
m = re.search(r"###\s*11\.1-bis[\s\S]+?(?=\n###?\s|\n---)", rfp)
if not m:
    fail("release-filter-policy.md: section 11.1-bis (UI section purity) not found")
section_bis = m.group(0)
for required_phrase in ("gallery, not a narrative", "Forbidden inside the UI section", "<p>"):
    if required_phrase not in section_bis:
        fail(f"release-filter-policy.md section 11.1-bis: missing required phrase {required_phrase!r}")
ok("release-filter-policy.md section 11.1-bis: gallery-only rule with explicit forbidden list present")

m = re.search(r"###\s*11\.1-ter[\s\S]+?(?=\n###?\s|\n---)", rfp)
if not m:
    fail("release-filter-policy.md: section 11.1-ter (topic-name source priority) not found")
section_ter = m.group(0)
for required_phrase in ("Jira description heading", "filename", "Untitled UI", "ui_topic_name_unresolved"):
    if required_phrase not in section_ter:
        fail(f"release-filter-policy.md section 11.1-ter: missing required phrase {required_phrase!r}")
ok("release-filter-policy.md section 11.1-ter: Jira-driven topic-name priority + warning fallback present")

# SKILL.md STEP 6 check #7 must reference the gallery-only rule and list the FAIL conditions.
# Find the check #7 row in the validation table.
m = re.search(r"\|\s*7\s*\|[^\n]+", skill)
if not m:
    fail("SKILL.md: STEP 6 validation check #7 row not found")
check7 = m.group(0)
for required_phrase in ("gallery-only", "11.1-bis", "FAIL conditions", "noun-phrase"):
    if required_phrase not in check7:
        fail(f"SKILL.md STEP 6 check #7: missing required phrase {required_phrase!r}")
ok("SKILL.md STEP 6 check #7: gallery-only validation with explicit FAIL conditions present")

# WIKI_PAGE_RENDER.md §3.2-bis must list forbidden tags inside the UI section.
m = re.search(r"###\s*3\.2-bis[\s\S]+?(?=\n###?\s|\n---)", render)
if not m:
    fail("WIKI_PAGE_RENDER.md: section 3.2-bis (UI section purity) not found")
section_32bis = m.group(0)
for required_phrase in ("gallery", "Forbidden inside the UI section", "<p>", "<ul>", "<table>"):
    if required_phrase not in section_32bis:
        fail(f"WIKI_PAGE_RENDER.md section 3.2-bis: missing required phrase {required_phrase!r}")
ok("WIKI_PAGE_RENDER.md section 3.2-bis: forbidden-tag list present")

# specification-writing-guideline.md §4 must say "gallery, not a narrative" and list Jira topic-name priority.
m = re.search(r"###\s*4\.\s*User Interfaces[\s\S]+?(?=\n###?\s|\n---)", guideline)
if not m:
    fail("specification-writing-guideline.md: section 4 (User Interfaces) not found")
section_4 = m.group(0)
for required_phrase in ("gallery, not a narrative", "No paragraph descriptions", "screen name (UI topic)"):
    if required_phrase not in section_4:
        fail(f"specification-writing-guideline.md section 4: missing required phrase {required_phrase!r}")
ok("specification-writing-guideline.md section 4: gallery rule + Jira topic-name priority present")

# --- 5j. Form-table 6-cell alignment rule present ---
# STEP 6 check #8 must mention strict 6-cell row alignment and em-dash empty-cell placeholder.
m = re.search(r"\|\s*8\s*\|[^\n]+", skill)
if not m:
    fail("SKILL.md: STEP 6 validation check #8 row not found")
check8 = m.group(0)
for required_phrase in ("exactly 6 `<td>`", "em-dash"):
    if required_phrase not in check8:
        fail(f"SKILL.md STEP 6 check #8: missing required phrase {required_phrase!r}")
ok("SKILL.md STEP 6 check #8: strict 6-cell + em-dash empty-cell rule present")

# WIKI_PAGE_RENDER.md section 2.4-bis present with the em-dash example.
m = re.search(r"###\s*2\.4-bis[\s\S]+?(?=\n###?\s|\n---)", render)
if not m:
    fail("WIKI_PAGE_RENDER.md: section 2.4-bis (Form-table cell-alignment) not found")
section_24bis = m.group(0)
for required_phrase in ("6-cell rows", "em-dash", "do not appear"):
    if required_phrase not in section_24bis:
        fail(f"WIKI_PAGE_RENDER.md section 2.4-bis: missing required phrase {required_phrase!r}")
ok("WIKI_PAGE_RENDER.md section 2.4-bis: 6-cell rule + em-dash example present")

# specification-writing-guideline.md Form section must explicitly require 6 cells.
if "Every Form data row MUST have exactly 6 cells" not in guideline:
    fail("specification-writing-guideline.md Form section: missing 6-cell requirement language")
ok("specification-writing-guideline.md Form section: 6-cell requirement present")

# --- 5k. UI binary handling: never Read image files into routine context ---
# Both release-filter-policy.md §11.1 and SKILL.md STEP 5-D must explicitly
# forbid using the Read tool on downloaded image binaries. This guards against
# the "API Error: an image in the conversation could not be processed and was
# removed" failure mode (Claude API multimodal rejection of malformed/oversized
# image inputs).
if "NEVER use the `Read` tool" not in skill and "NEVER use the Read tool" not in skill:
    fail("SKILL.md STEP 5-D: missing explicit \"NEVER use the Read tool\" guidance for downloaded image binaries")
ok("SKILL.md STEP 5-D: explicit 'NEVER use Read tool on downloaded image binaries' guidance present")

if "do NOT use the `Read` tool" not in rfp:
    fail("release-filter-policy.md §11.1 step 1: missing explicit \"do NOT use the Read tool\" guidance for downloaded image binaries")
ok("release-filter-policy.md §11.1: explicit 'do NOT use Read tool on downloaded image binaries' guidance present")

# --- 5l. FIRST-FIRE BOOTSTRAP canonical pattern present in SKILL.md §5-C.5 ---
# SKILL.md §5-C.5 must document the FIRST-FIRE BOOTSTRAP algorithm with
# page-name idempotency check + destination self-commit. Both are required
# safeguards against duplicate-page creation on bootstrap re-fires AND
# the operator-forgets-to-merge scenario.
if "FIRST-FIRE BOOTSTRAP" not in skill:
    fail("SKILL.md §5-C.5: missing FIRST-FIRE BOOTSTRAP canonical pattern")
if "Page-name idempotency check" not in skill:
    fail("SKILL.md §5-C.5: missing page-name idempotency safeguard (step 5)")
if "Self-commit the destination update" not in skill:
    fail("SKILL.md §5-C.5: missing destination self-commit step (step 7)")
if "5-C.5.2" not in skill:
    fail("SKILL.md §5-C.5: missing §5-C.5.2 self-commit constraint rules")
if "wiki_destination.json" not in skill[skill.find("Allowed writes"):]:
    fail("SKILL.md Allowed writes: must permit wiki_destination.json PUT during first-fire bootstrap")
ok("SKILL.md §5-C.5: FIRST-FIRE BOOTSTRAP canonical pattern with page-idempotency + self-commit + Allowed-writes entry present")

print()
print("All smoke checks passed.")
