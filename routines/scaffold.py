"""
Scaffold a new routine in one shot.

WHAT IT DOES
------------
Given a routine slug, Jira project key, and a configured BookStack
page id, this script:

  1. Validates the slug + project shape (no surprise characters, slug
     ends in `_daily_sync` to match the existing convention).
  2. (Optional) Validates that the BookStack page exists and is inside
     the Specification shelf (id=3).
  3. (Optional) Validates that the Jira project + fixVersion exist.
  4. Generates `routines/<slug>.prompt.md` from the canonical
     `routines/cm_daily_sync.prompt.md` template with the new
     project's bindings substituted in.
  5. Adds an entry to `resources/wiki_destination.json` under
     `routine_destinations.<slug>`.
  6. Prints the next steps the operator needs to run: `deploy.py
     --create`, env vars to set in the claude.ai UI, etc.

This replaces a ~5-step manual onboarding flow with a single command.

USAGE
-----
  py routines/scaffold.py \\
      --slug roster_daily_sync \\
      --project-key ROS \\
      --project-name "Roster" \\
      --page-id 600 \\
      --page-name "Roster Spec" \\
      --book-id 12 \\
      --release-scope 8.1 \\
      --cron "30 2 * * *"

  # Skip the live BookStack + Jira validations (faster, no creds needed):
  py routines/scaffold.py --skip-validation [...]

  # Preview the diff without writing anything:
  py routines/scaffold.py --dry-run [...]

ENV VARS (optional — only needed if validation is NOT skipped)
--------------------------------------------------------------
  WIKI_BASE_URL / WIKI_TOKEN_ID / WIKI_TOKEN_SECRET   (BookStack)
  JIRA_USER / JIRA_API_TOKEN                          (Jira)

EXIT CODES
----------
  0  scaffolded successfully (or dry-run completed)
  1  bad usage / missing required arg
  2  slug already exists in wiki_destination.json (use a different slug
     or delete the existing entry first)
  3  validation failed (BookStack page not in shelf 3, Jira project not
     found, fixVersion not in Jira)
  4  IO error writing one of the artefacts
"""
from __future__ import annotations

import argparse
import json
import os
import re
import ssl
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
ROUTINES_DIR = REPO_ROOT / "routines"
RESOURCES_DIR = REPO_ROOT / "resources"
CM_PROMPT = ROUTINES_DIR / "cm_daily_sync.prompt.md"
WIKI_DEST = RESOURCES_DIR / "wiki_destination.json"

SLUG_RE = re.compile(r"^[a-z][a-z0-9_]*_(daily|weekly|hourly)_sync$")
JIRA_KEY_RE = re.compile(r"^[A-Z][A-Z0-9]+$")
CRON_RE = re.compile(r"^[\d\*/,\-\s]+$")  # very loose; claude.ai validates strictly

try:
    from dotenv import load_dotenv
    load_dotenv(REPO_ROOT / ".env")
except ImportError:
    pass


def fail(msg: str, code: int = 1) -> None:
    print(f"scaffold: {msg}", file=sys.stderr)
    sys.exit(code)


def warn(msg: str) -> None:
    print(f"scaffold: WARN {msg}", file=sys.stderr)


def info(msg: str) -> None:
    print(f"scaffold: {msg}")


# ---------------------------------------------------------------------------
# Validators
# ---------------------------------------------------------------------------

def validate_slug(slug: str) -> None:
    if not SLUG_RE.match(slug):
        fail(f"slug {slug!r} must match {SLUG_RE.pattern} "
             f"(lowercase snake_case ending in _daily_sync / _weekly_sync / "
             f"_hourly_sync — e.g. roster_daily_sync)", code=1)


def validate_project_key(key: str) -> None:
    if not JIRA_KEY_RE.match(key):
        fail(f"project-key {key!r} must match {JIRA_KEY_RE.pattern} "
             f"(uppercase letters/digits, must start with a letter — "
             f"e.g. CM, PNP, ROS)", code=1)


def validate_cron(expr: str) -> None:
    if not CRON_RE.match(expr):
        fail(f"cron {expr!r} contains unexpected characters "
             f"(only digits, *, /, ,, -, and whitespace allowed)", code=1)
    parts = expr.split()
    if len(parts) != 5:
        fail(f"cron {expr!r} must have exactly 5 fields "
             f"(minute hour day-of-month month day-of-week — got {len(parts)})",
             code=1)


def slug_already_taken(slug: str, dest: dict) -> bool:
    return slug in dest.get("routine_destinations", {})


def validate_page_in_shelf3(base: str, auth: str, page_id: int) -> tuple[bool, str]:
    """Return (ok, detail). Best-effort — caller decides whether to abort."""
    try:
        req = urllib.request.Request(
            base.rstrip("/") + f"/api/pages/{page_id}",
            method="GET",
            headers={"Authorization": auth, "Accept": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=30, context=ssl.create_default_context()) as resp:
            body = json.loads(resp.read().decode("utf-8", errors="replace"))
    except urllib.error.HTTPError as exc:
        return False, f"HTTP {exc.code} fetching page {page_id} (token may lack access, or page does not exist)"
    except (urllib.error.URLError, OSError, ssl.SSLError) as exc:
        return False, f"network error fetching page {page_id}: {exc}"

    book_id = body.get("book_id")
    if not book_id:
        return False, f"page {page_id} has no book_id in API response (malformed)"

    # Walk: page -> book -> shelf
    try:
        req2 = urllib.request.Request(
            base.rstrip("/") + f"/api/books/{book_id}",
            method="GET",
            headers={"Authorization": auth, "Accept": "application/json"},
        )
        with urllib.request.urlopen(req2, timeout=30, context=ssl.create_default_context()) as resp2:
            book = json.loads(resp2.read().decode("utf-8", errors="replace"))
    except Exception as exc:
        return False, f"could not walk book {book_id} to check shelf: {exc}"

    # BookStack book API returns shelves only when the book belongs to one — check shelf 3
    try:
        req3 = urllib.request.Request(
            base.rstrip("/") + "/api/shelves/3",
            method="GET",
            headers={"Authorization": auth, "Accept": "application/json"},
        )
        with urllib.request.urlopen(req3, timeout=30, context=ssl.create_default_context()) as resp3:
            shelf = json.loads(resp3.read().decode("utf-8", errors="replace"))
    except Exception as exc:
        return False, f"could not fetch shelf 3 to verify membership: {exc}"

    shelf_book_ids = {b["id"] for b in (shelf.get("books") or []) if b.get("id")}
    if book_id in shelf_book_ids:
        return True, f"page {page_id} -> book {book_id} ({book.get('name', '?')!r}) -> shelf 3 (OK)"
    return False, (f"page {page_id} -> book {book_id} ({book.get('name', '?')!r}) "
                   f"is NOT in the Specification shelf (id=3). "
                   f"Move the page first or pick a different page_id.")


def validate_jira_project_and_version(project_key: str, fix_version: str,
                                       jira_user: str, jira_token: str) -> tuple[bool, str]:
    """Best-effort Jira validation. The routine connects via the Atlassian
    MCP at fire time; this validator uses the REST API directly with HTTP
    Basic auth (base64-encoded `user:token`)."""
    import base64
    base = "https://orangehrmenterprise.atlassian.net"
    creds_b64 = base64.b64encode(f"{jira_user}:{jira_token}".encode("utf-8")).decode("ascii")
    auth_header = f"Basic {creds_b64}"

    # --- project lookup ---
    try:
        req = urllib.request.Request(
            f"{base}/rest/api/3/project/{project_key}",
            method="GET",
            headers={"Accept": "application/json", "Authorization": auth_header},
        )
        with urllib.request.urlopen(req, timeout=30, context=ssl.create_default_context()) as resp:
            body = json.loads(resp.read().decode("utf-8", errors="replace"))
    except urllib.error.HTTPError as exc:
        return False, (f"Jira project {project_key!r}: HTTP {exc.code} "
                       f"(token may lack access, or project does not exist)")
    except Exception as exc:
        return False, f"Jira project {project_key!r}: {exc}"

    project_name = body.get("name") or "(unknown)"

    # --- fixVersion lookup ---
    try:
        req2 = urllib.request.Request(
            f"{base}/rest/api/3/project/{project_key}/versions",
            method="GET",
            headers={"Accept": "application/json", "Authorization": auth_header},
        )
        with urllib.request.urlopen(req2, timeout=30, context=ssl.create_default_context()) as resp2:
            versions = json.loads(resp2.read().decode("utf-8", errors="replace"))
    except Exception as exc:
        return False, f"project versions lookup failed: {exc}"

    match = next((v for v in versions if v.get("name") == fix_version), None)
    if not match:
        names = ", ".join(v.get("name", "?") for v in versions[:8])
        return False, (f"fixVersion {fix_version!r} not found in project {project_key} "
                       f"(known: {names}{'...' if len(versions) > 8 else ''}). "
                       f"Create it in Jira or pick a different release_scope.")
    return True, (f"Jira project {project_key} ({project_name!r}) — "
                  f"fixVersion {fix_version} {'released' if match.get('released') else 'pending'}")


# ---------------------------------------------------------------------------
# Generators
# ---------------------------------------------------------------------------

def generate_prompt(args, template: str) -> str:
    """Substitute CM-specific tokens in cm_daily_sync.prompt.md to make
    a prompt for the new routine. Replacements are scoped to obviously
    project-specific lines — leaving STEP 1..11 wording, safety rails,
    etc. untouched."""
    out = template
    replacements = [
        # human title
        ("OHRM CM Daily Wiki Sync", f"OHRM {args.project_name} Daily Wiki Sync"),
        # JQL examples
        ("project = CM AND issuetype = Epic", f"project = {args.project_key} AND issuetype = Epic"),
        ("project = CM AND fixVersion", f"project = {args.project_key} AND fixVersion"),
        # routine slug + parameters
        ("cm_daily_sync", args.slug),
        # project key in standalone references
        ("`JIRA_PROJECT` | `CM`", f"`JIRA_PROJECT` | `{args.project_key}`"),
        ("`PROJECT_NAME` | Compensation Management",
         f"`PROJECT_NAME` | {args.project_name}"),
        # CM-specific release-scope line — generalised
        ("(current value: `8.0`)", f"(current value: `{args.release_scope}`)"),
        # target-page-id line
        ("(current value: `360` — `Salary` page in chapter `Employee Profile`, book `Employee Management`)",
         f"(current value: `{args.page_id}` — `{args.page_name}` page)"),
        # fire-time line — let operator hand-tune
        ("07:00 Asia/Colombo (cron `30 1 * * *` UTC)",
         f"(cron `{args.cron}` UTC)"),
        # routine_id — placeholder; deploy.py fills this in
        ("`ROUTINE_ID` | `trig_01QhSWfCdQjX66YgGoi1YpQ3`",
         "`ROUTINE_ID` | (set by `deploy.py --create`)"),
        # log path prefix
        ("`LOG_PATH_PREFIX` | `logs/cm_daily_sync/`",
         f"`LOG_PATH_PREFIX` | `logs/{args.slug}/`"),
    ]
    for old, new in replacements:
        out = out.replace(old, new)
    return out


def update_wiki_destination(dest: dict, args) -> dict:
    """Insert the new routine_destinations entry. Preserves order of
    existing keys and appends the new one at the end."""
    routine_destinations = dest.setdefault("routine_destinations", {})
    routine_destinations[args.slug] = {
        "page_id": args.page_id,
        "page_name": args.page_name,
        "book_id": args.book_id,
        "book_name": args.book_name or "(set by scaffold)",
        "chapter_id": args.chapter_id,
        "chapter_name": args.chapter_name,
        "release_scope": args.release_scope,
        "jira_project_key": args.project_key,
        "last_verified": "(set by scaffold — re-run with --skip-validation=false to verify live)",
    }
    return dest


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------

def main() -> int:
    ap = argparse.ArgumentParser(
        description="Scaffold a new OHRM Wiki Sync routine in one shot.")
    ap.add_argument("--slug", required=True,
                    help="routine slug, e.g. roster_daily_sync")
    ap.add_argument("--project-key", required=True,
                    help="Jira project key, e.g. ROS")
    ap.add_argument("--project-name", required=True,
                    help="Human project name, e.g. \"Roster Management\"")
    ap.add_argument("--page-id", type=int, required=True,
                    help="BookStack target page id")
    ap.add_argument("--page-name", required=True,
                    help="BookStack target page name (must match BookStack)")
    ap.add_argument("--book-id", type=int, required=True,
                    help="BookStack book id that contains the target page")
    ap.add_argument("--book-name", default="",
                    help="BookStack book name (optional — for the destination map)")
    ap.add_argument("--chapter-id", type=int, default=None,
                    help="BookStack chapter id (optional; null if page lives directly in the book)")
    ap.add_argument("--chapter-name", default=None,
                    help="BookStack chapter name (optional)")
    ap.add_argument("--release-scope", required=True,
                    help="Jira fixVersion to filter by, e.g. 8.1")
    ap.add_argument("--cron", default="30 1 * * *",
                    help="Cron expression in UTC (5-field). Default: 30 1 * * * (07:00 Asia/Colombo daily)")
    ap.add_argument("--skip-validation", action="store_true",
                    help="Skip the live BookStack + Jira validation steps "
                    "(useful when no creds are loaded or for quick scaffolding)")
    ap.add_argument("--dry-run", action="store_true",
                    help="Print the planned changes without writing anything")
    args = ap.parse_args()

    # ---- shape validation (always runs) ----
    validate_slug(args.slug)
    validate_project_key(args.project_key)
    validate_cron(args.cron)
    info(f"shape OK: slug={args.slug} project={args.project_key} "
         f"page_id={args.page_id} release_scope={args.release_scope}")

    # ---- pre-check: slug already exists? ----
    if not WIKI_DEST.exists():
        fail(f"missing {WIKI_DEST} — cannot scaffold without the canonical "
             f"destination map. Restore from git.", code=4)
    dest = json.loads(WIKI_DEST.read_text(encoding="utf-8"))
    if slug_already_taken(args.slug, dest):
        fail(f"routine slug {args.slug!r} already exists in "
             f"routine_destinations. Pick a different slug or remove the "
             f"existing entry first.", code=2)

    # ---- live validation (BookStack + Jira) ----
    if not args.skip_validation:
        base = os.environ.get("WIKI_BASE_URL", "").strip()
        tid = os.environ.get("WIKI_TOKEN_ID", "").strip()
        tsec = os.environ.get("WIKI_TOKEN_SECRET", "").strip()
        if base and tid and tsec:
            auth = f"Token {tid}:{tsec}"
            ok, detail = validate_page_in_shelf3(base, auth, args.page_id)
            if ok:
                info(detail)
            else:
                fail(f"BookStack validation failed: {detail}", code=3)
        else:
            warn("BookStack env vars not set — skipping BookStack validation. "
                 "Re-run with WIKI_BASE_URL / WIKI_TOKEN_ID / WIKI_TOKEN_SECRET "
                 "in .env to validate the page lives inside shelf 3.")

        jira_user = os.environ.get("JIRA_USER", "").strip()
        jira_token = os.environ.get("JIRA_API_TOKEN", "").strip()
        if jira_user and jira_token:
            ok, detail = validate_jira_project_and_version(
                args.project_key, args.release_scope, jira_user, jira_token)
            if not ok:
                fail(f"Jira validation failed: {detail}", code=3)
            info(detail)
        else:
            warn("Jira env vars not set — skipping Jira validation. "
                 "Re-run with JIRA_USER / JIRA_API_TOKEN in .env to validate "
                 "the project + fixVersion exist.")
    else:
        info("--skip-validation: skipped BookStack + Jira live checks")

    # ---- generate prompt ----
    if not CM_PROMPT.exists():
        fail(f"missing template {CM_PROMPT}", code=4)
    template = CM_PROMPT.read_text(encoding="utf-8")
    new_prompt = generate_prompt(args, template)
    new_prompt_path = ROUTINES_DIR / f"{args.slug}.prompt.md"

    # ---- prepare destination diff ----
    new_dest = update_wiki_destination(json.loads(json.dumps(dest)), args)

    if args.dry_run:
        info(f"--dry-run — would write {new_prompt_path} ({len(new_prompt)} chars)")
        info(f"--dry-run — would add this entry to routine_destinations:")
        print(json.dumps(new_dest["routine_destinations"][args.slug], indent=2))
        info("--dry-run — nothing was changed on disk")
        return 0

    if new_prompt_path.exists():
        fail(f"refusing to overwrite existing prompt file {new_prompt_path} "
             f"(delete it first if this is a re-scaffold)", code=4)

    new_prompt_path.write_text(new_prompt, encoding="utf-8")
    info(f"wrote {new_prompt_path} ({new_prompt_path.stat().st_size} bytes)")

    WIKI_DEST.write_text(json.dumps(new_dest, indent=2) + "\n", encoding="utf-8")
    info(f"updated {WIKI_DEST}")

    # ---- print next steps ----
    print("")
    print("=" * 70)
    print("SCAFFOLD COMPLETE — next steps:")
    print("=" * 70)
    print(f"  1. Review the generated prompt file:")
    print(f"       {new_prompt_path}")
    print(f"     Hand-tune anything the substituter couldn't infer (e.g. project-")
    print(f"     specific safety notes, custom STEP 5 hints).")
    print("")
    print(f"  2. Verify routine_destinations.{args.slug} in:")
    print(f"       {WIKI_DEST}")
    print("")
    print(f"  3. Deploy the routine:")
    print(f"       py routines/deploy.py --create {args.slug} \\")
    print(f"           --cron \"{args.cron}\"")
    print("")
    print(f"  4. After deploy.py prints the trigger_id, open the routine in")
    print(f"     claude.ai and set the Environment Variables:")
    print(f"       ATLASSIAN_CLOUD_ID, WIKI_BASE_URL, WIKI_TOKEN_ID,")
    print(f"       WIKI_TOKEN_SECRET, GITHUB_TOKEN, RESEND_API_KEY,")
    print(f"       EMAIL_RECIPIENTS")
    print("")
    print(f"  5. Fire a dry-run once to validate end-to-end:")
    print(f"       Set DRY_RUN=true in the routine's Environment Variables,")
    print(f"       click \"Run now\". Check the email + GitHub log. Then set")
    print(f"       DRY_RUN back to false (or remove it) for production.")
    print("")
    print(f"  6. Commit the changes:")
    print(f"       git add routines/{args.slug}.prompt.md resources/wiki_destination.json")
    print(f"       git commit -m \"scaffold: new routine {args.slug}\"")
    print("")
    return 0


if __name__ == "__main__":
    sys.exit(main())
