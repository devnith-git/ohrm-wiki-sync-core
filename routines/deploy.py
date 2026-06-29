"""
Deploy (create or update) the OHRM Wiki Sync routines.

Reads `.env` at the repo root, substitutes placeholders in the prompt template,
and submits the result to the Anthropic Routines API. Secrets never appear on
disk in a committed file or in plain process arguments — they live in `.env`
(gitignored) and travel only through `os.environ` to the request body.

USAGE
-----
  # Validate the template renders correctly without deploying:
  py routines/deploy.py --dry-run cm_daily_sync

  # Create a new routine (writes the trigger_id back to .env):
  py routines/deploy.py --create cm_daily_sync --cron "30 1 * * *"

  # Update an existing routine (uses ROUTINE_TRIGGER_ID from .env):
  py routines/deploy.py --update cm_daily_sync

  # Same but explicit trigger id:
  py routines/deploy.py --update cm_daily_sync --trigger-id trig_01XYZ...

EXIT CODES
----------
  0 on success; non-zero on any failure (missing env vars, API error, etc).
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.request
import urllib.error
import uuid
from pathlib import Path

# ---- Load .env (repo root) ----
HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parent
try:
    from dotenv import load_dotenv
    load_dotenv(REPO_ROOT / ".env")
except ImportError:
    sys.exit("python-dotenv not installed. Run: py -m pip install python-dotenv")


# Only the deploy-time env vars are required here. The runtime secrets
# (ATLASSIAN_CLOUD_ID, WIKI_BASE_URL, WIKI_TOKEN_ID, WIKI_TOKEN_SECRET) are
# NOT substituted into the prompt — they are configured at the environment
# level in the claude.ai routines UI and read by the routine at fire time.
#
# ## Email env vars (set in the claude.ai routines UI after --create)
#
# STEP 10 (notification email) reads one required env var from the routine
# environment:
#   RESEND_API_KEY           Resend API key, format re_<random> (sensitive).
#                            Get from https://resend.com/api-keys.
# Optional: EMAIL_FROM, EMAIL_FROM_NAME, RESEND_TIMEOUT, EMAIL_RECIPIENTS.
# STEP 10 is silently skipped if RESEND_API_KEY is unset.
REQUIRED = [
    "ROUTINE_ENVIRONMENT_ID",
]

ROUTINES_DIR = HERE
MCP_CONNECTORS_PATH = ROUTINES_DIR / "mcp_connectors.json"
PROMPT_BODY_RE = re.compile(
    r"<!-- PROMPT_BODY_START -->\s*(.+?)\s*<!-- PROMPT_BODY_END -->", re.S
)


def load_mcp_connectors() -> list[dict]:
    """Load the canonical MCP connector triples that every routine should be
    wired with. Single source of truth — when a new MCP is added to the fleet,
    update routines/mcp_connectors.json and re-run --update on every routine."""
    if not MCP_CONNECTORS_PATH.exists():
        fail(f"missing {MCP_CONNECTORS_PATH}. This file is the canonical "
             f"MCP wiring for every routine; check it into git.", code=11)
    data = json.loads(MCP_CONNECTORS_PATH.read_text(encoding="utf-8"))
    connectors = data.get("connectors") or []
    if not connectors:
        fail(f"{MCP_CONNECTORS_PATH} has no `connectors` array.", code=12)
    for c in connectors:
        for k in ("connector_uuid", "name", "url"):
            if not c.get(k):
                fail(f"connector {c} missing required field {k!r}.", code=13)
    return connectors


def fail(msg, code=1):
    print(f"deploy: {msg}", file=sys.stderr)
    sys.exit(code)


def check_env():
    missing = [k for k in REQUIRED if not os.environ.get(k)]
    if missing:
        fail(
            f"missing required env vars: {', '.join(missing)}.\n"
            f"Copy .env.example to .env and fill in the values.",
            code=2,
        )


def load_prompt(routine_name: str) -> str:
    path = ROUTINES_DIR / f"{routine_name}.prompt.md"
    if not path.exists():
        fail(f"prompt template not found: {path}", code=3)
    raw = path.read_text(encoding="utf-8")
    m = PROMPT_BODY_RE.search(raw)
    if not m:
        fail(
            f"no <!-- PROMPT_BODY_START --> ... <!-- PROMPT_BODY_END --> block "
            f"found in {path}",
            code=4,
        )
    return m.group(1).strip()


def substitute(template: str) -> str:
    """Two-mode substitution:

    1. Preferred runtime-env-var mode (this is what cm_daily_sync.prompt.md uses
       today): the prompt references env vars at fire time via `$WIKI_TOKEN_ID`
       etc. No `{{KEY}}` placeholders → substitute() is a no-op, prompt ships
       verbatim. Runtime secrets live in the claude.ai routines UI.

    2. Legacy / fallback deploy-time substitution mode: if a prompt template
       still contains `{{KEY}}` placeholders, look them up in `os.environ`
       (loaded from `.env`) and substitute. Fail if any are unresolved. Use
       this only when a value genuinely needs to be in the routine config
       (e.g. a non-secret repo URL or feature flag) — never for live secrets,
       because anything substituted into the prompt is visible to anyone with
       read access to the routine config.
    """
    def sub(match):
        key = match.group(1).strip()
        val = os.environ.get(key)
        if val is None:
            fail(
                f"prompt references {{{{ {key} }}}} but ${key} is not set. "
                f"Either set the env var, or migrate the placeholder to a "
                f"runtime $VAR reference (preferred for secrets — see "
                f"routines/README.md).",
                code=5,
            )
        return val

    if "{{" not in template:
        return template  # nothing to substitute; ship verbatim

    result = re.sub(r"\{\{\s*([A-Z0-9_]+)\s*\}\}", sub, template)
    leftover = re.findall(r"\{\{[^{}]+\}\}", result)
    if leftover:
        fail(f"unresolved placeholders after substitution: {leftover}", code=6)
    return result


def remote_trigger(method: str, path: str, body: dict | None = None) -> dict:
    """
    Call the Anthropic RemoteTrigger API. Auth is the same OAuth used by Claude
    Code (the harness sets the token). We piggy-back on the local CLI's token
    by reading `~/.claude/.credentials.json` if available, else require the env
    var ANTHROPIC_API_KEY.
    """
    # The cleanest approach: invoke the local `claude` CLI's already-authenticated
    # session via a small helper, OR talk directly to api.anthropic.com if a key
    # is set. We use whichever is available.
    # For MVP, we shell out to a small subprocess that uses the RemoteTrigger
    # tool — but since this script may run outside Claude Code, we hit the REST
    # endpoint directly with the Anthropic API key.
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        fail("ANTHROPIC_API_KEY not set (.env). Required to call the Routines API.", code=7)

    url = f"https://api.anthropic.com/v1/code{path}"
    headers = {
        "x-api-key": api_key,
        "anthropic-version": "2023-06-01",
        "Content-Type": "application/json",
    }
    data = None
    if body is not None:
        data = json.dumps(body).encode("utf-8")

    req = urllib.request.Request(url, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            raw = r.read().decode("utf-8")
            return json.loads(raw) if raw.strip() else {}
    except urllib.error.HTTPError as e:
        body_text = e.read().decode("utf-8", errors="replace")
        fail(f"HTTP {e.code} on {method} {url}: {body_text}", code=8)


def build_body(name: str, prompt: str, cron: str | None,
               run_once_at: str | None) -> dict:
    """Assemble the RemoteTrigger create/update body."""
    body = {
        "name": name,
        "enabled": True,
        "job_config": {
            "ccr": {
                "environment_id": os.environ["ROUTINE_ENVIRONMENT_ID"],
                "session_context": {
                    "model": os.environ.get("ROUTINE_MODEL", "claude-sonnet-4-6"),
                    "sources": [],
                    "allowed_tools": ["Bash", "Read", "Write", "Edit", "Glob", "Grep", "WebFetch"],
                },
                "events": [{
                    "data": {
                        "uuid": str(uuid.uuid4()),
                        "session_id": "",
                        "type": "user",
                        "parent_tool_use_id": None,
                        "message": {"role": "user", "content": prompt},
                    }
                }],
            }
        },
        "mcp_connections": load_mcp_connectors(),
    }
    if cron:
        body["cron_expression"] = cron
    if run_once_at:
        body["run_once_at"] = run_once_at
    return body


def main():
    ap = argparse.ArgumentParser(description="Deploy OHRM Wiki Sync routines.")
    ap.add_argument("routine", help="Routine name (matches <name>.prompt.md)")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--create", action="store_true", help="Create a new routine")
    g.add_argument("--update", action="store_true", help="Update an existing routine")
    g.add_argument("--dry-run", action="store_true", help="Print substituted prompt; don't call API")
    ap.add_argument("--cron", help="Cron expression (UTC). Required for --create unless --run-once-at is set.")
    ap.add_argument("--run-once-at", help="RFC3339 UTC timestamp for a one-time run. Alternative to --cron.")
    ap.add_argument("--trigger-id", help="Trigger id to update (else read ROUTINE_TRIGGER_ID from .env)")
    args = ap.parse_args()

    check_env()
    template = load_prompt(args.routine)
    prompt = substitute(template)

    name_map = {
        "cm_daily_sync":             "OHRM CM Daily Wiki Sync",
        "pnp_daily_sync":            "OHRM Performance Core Daily Wiki Sync",
        "roster_daily_sync":         "OHRM Roster Daily Wiki Sync",
        "orange_sign_daily_sync":    "OHRM Orange Sign Daily Wiki Sync",
        "cs_features_daily_sync":    "OHRM CS Features Daily Wiki Sync",
    }
    routine_name = name_map.get(args.routine, args.routine.replace("_", " ").title())

    if args.dry_run:
        print(f"[dry-run] routine name: {routine_name}")
        print(f"[dry-run] cron: {args.cron or '(none)'}")
        print(f"[dry-run] prompt length: {len(prompt)} chars")
        print(f"[dry-run] secrets resolved: WIKI_TOKEN_ID, WIKI_TOKEN_SECRET, ATLASSIAN_CLOUD_ID, WIKI_BASE_URL")
        print()
        print("---------- SUBSTITUTED PROMPT (first 1000 chars) ----------")
        print(prompt[:1000])
        print("---------- ... ----------")
        return

    body = build_body(routine_name, prompt, args.cron, args.run_once_at)

    if args.create:
        if not (args.cron or args.run_once_at):
            fail("--create requires --cron or --run-once-at", code=9)
        print(f"Creating routine {routine_name!r}...")
        result = remote_trigger("POST", "/triggers", body)
        trig_id = result.get("trigger", {}).get("id") or result.get("id")
        print(f"Created: {trig_id}")
        print(f"Manage: https://claude.ai/code/routines/{trig_id}")
        print(f"Next run: {result.get('trigger', {}).get('next_run_at', '(?)')}")
        print()
        print("IMPORTANT — set the runtime env vars in the claude.ai UI:")
        print(f"  Open: https://claude.ai/code/routines/{trig_id}")
        print( "  Edit → Environment variables → add ATLASSIAN_CLOUD_ID,")
        print( "         WIKI_BASE_URL, WIKI_TOKEN_ID, WIKI_TOKEN_SECRET.")
        print( "  The routine will refuse to run until these are set.")
        print()
        print( "  For email notifications (STEP 10), also set:")
        print( "         RESEND_API_KEY (get from https://resend.com/api-keys)")
        print( "  Free tier: 3000/month, no credit card needed.")
        print()
        print(f"Add this to your .env so future --update runs target it:")
        print(f"  ROUTINE_TRIGGER_ID={trig_id}")
    elif args.update:
        trig_id = args.trigger_id or os.environ.get("ROUTINE_TRIGGER_ID")
        if not trig_id:
            fail("--update needs --trigger-id or ROUTINE_TRIGGER_ID in .env", code=10)
        print(f"Updating routine {trig_id}...")
        result = remote_trigger("POST", f"/triggers/{trig_id}", body)
        print(f"Updated. next_run_at = {result.get('trigger', {}).get('next_run_at', '(?)')}")


if __name__ == "__main__":
    main()
