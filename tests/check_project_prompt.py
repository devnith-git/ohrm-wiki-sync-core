"""
Per-project prompt path/navigation gate for the split (core + per-project) layout.

Run this for a project repo BEFORE pointing its routine at the new repo. It
verifies every path/navigation reference the routine relies on actually
resolves under the split architecture — the class of bug that otherwise only
surfaces as a BLOCKED/FAILED fire.

USAGE
    python tests/check_project_prompt.py <core_dir> <project_dir> <slug> <project_repo_name>

EXAMPLE
    python tests/check_project_prompt.py ./_core ./_comp cm_daily_sync ohrm-wiki-sync-compensation

Exit 0 = PASS, non-zero = at least one FAIL.
"""
import sys, os, re, base64, json

def main():
    if len(sys.argv) != 5:
        print(__doc__); sys.exit(2)
    CORE, PROJ, SLUG, REPO = sys.argv[1:5]
    prompt_path = os.path.join(PROJ, "routines", f"{SLUG}.prompt.md")
    if not os.path.exists(prompt_path):
        print(f"[FAIL] prompt not found: {prompt_path}"); sys.exit(1)
    prompt = open(prompt_path, encoding="utf-8").read()
    # Only validate the deployed body (between markers) for path refs.
    m = re.search(r"<!-- PROMPT_BODY_START -->(.+?)<!-- PROMPT_BODY_END -->", prompt, re.S)
    body = m.group(1) if m else ""
    oks, fails = [], []
    ok = lambda s: oks.append(s)
    bad = lambda s: fails.append(s)

    if m: ok("PROMPT_BODY markers present")
    else: bad("PROMPT_BODY markers MISSING (shim/deploy would ship nothing)")

    # clone command must be the proxy-safe bare-token form
    if re.search(r'git clone .*"https://\$\{GITHUB_TOKEN\}@github\.com/devnith-git/ohrm-wiki-sync-core\.git"', body):
        ok("core clone uses bare-token URL (proxy-safe, works first-go)")
    elif "x-access-token:" in body and "ohrm-wiki-sync-core" in body:
        bad("clone uses x-access-token: form -- the cloud proxy REJECTS this")
    elif re.search(r'git clone\s+"?https://github\.com/devnith-git/ohrm-wiki-sync-core', body):
        bad("clone is ANONYMOUS -- the cloud proxy returns 403")
    else:
        bad("no recognizable core clone command in body")

    # every _core/<file> ref must exist in the core checkout
    for r in sorted(set(re.findall(r'_core/([A-Za-z0-9_./-]+\.[A-Za-z0-9]+)', body))):
        p = os.path.join(CORE, r)
        (ok if os.path.exists(p) else bad)(f"_core/{r} {'exists' if os.path.exists(p) else 'MISSING in core'}")

    # local resources refs (NOT _core-prefixed) must exist in the project repo
    for r in sorted(set(re.findall(r'(?:^|[^/])resources/([A-Za-z0-9_./-]+\.[A-Za-z0-9]+)', body))):
        if f"_core/resources/{r}" in body and r not in [x for x in re.findall(r'(?<!_core/)\bresources/'+re.escape(r), body)]:
            continue  # the only hit is the _core-prefixed one
        # treat as local only if a bare 'resources/<r>' occurs
        if re.search(r'(?<!_core/)\bresources/' + re.escape(r), body):
            p = os.path.join(PROJ, "resources", r)
            (ok if os.path.exists(p) else bad)(f"local resources/{r} {'exists' if os.path.exists(p) else 'MISSING in project repo'}")

    # STEP 10 notifier must come from core, not the (empty) local routines/
    if "_core/routines/send_notification.py" in body: ok("STEP 10 -> _core/routines/send_notification.py")
    elif re.search(r'(?<!_core/)\broutines/send_notification\.py', body): bad("STEP 10 -> LOCAL routines/send_notification.py (not present in project repo)")

    # STEP 9 log must target this project's repo
    if f"{REPO}/contents/logs/{SLUG}" in body: ok(f"STEP 9 log -> {REPO}")
    else: bad(f"STEP 9 log target not pointing at {REPO}")

    # destination navigation: slug entry resolves and rolls up cleanly (page_id present)
    dest_raw = open(os.path.join(CORE, "resources", "wiki_destination.json"), "rb").read()
    dest = json.loads(base64.b64decode(dest_raw))
    cm = dest.get("routine_destinations", {}).get(SLUG)
    if cm and cm.get("page_id"):
        ok(f"destination resolves: page_id={cm['page_id']} ({cm.get('page_name')}) book={cm.get('book_id')} chapter={cm.get('chapter_id')}")
    else:
        bad(f"destination for {SLUG} missing/invalid in core wiki_destination.json")

    print(f"=== PATH/NAV GATE: {SLUG} ({REPO}) ===")
    for s in oks: print("  [OK]  ", s)
    for s in fails: print("  [FAIL]", s)
    print(f"RESULT: {len(oks)} ok, {len(fails)} fail -> {'PASS' if not fails else 'FAIL'}")
    sys.exit(1 if fails else 0)

if __name__ == "__main__":
    main()
