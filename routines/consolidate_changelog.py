#!/usr/bin/env python3
"""consolidate_changelog.py — sweep EVERY branch's run logs into main's changelog.

The scheduled routines commit their `.md` audit logs to per-run `claude/*`
branches (and their STEP-9 prompts don't update the changelog). This janitor
guarantees nothing is missed: it reads run logs from all branches, builds
changelog rows, and writes the canonical CSV ledger + rendered xlsx back to
`main`. Idempotent — a run already present (by run_utc + routine) is skipped.

Run by a scheduled trigger AFTER the daily batch (and safe to run anytime).

Reading uses local git refs (the agent must `git fetch` all branches first).
Writing uses the GitHub Contents API (branch=main) so it never pushes to the
clone. Dry-run with --dry to skip the PUTs (prints what it would do).

Usage:
    python routines/consolidate_changelog.py [--dry]

Env: GITHUB_TOKEN (required for the real PUT; --dry needs none),
     GITHUB_REPO (default devnith-git/ohrm-wiki-sync).
"""
import base64
import json
import os
import re
import subprocess
import sys
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from update_changelog import (CSV_FIELDS, _ensure_openpyxl, _load_csv,  # noqa: E402
                              _render_xlsx, _sig, _write_csv)

REPO = os.environ.get("GITHUB_REPO", "devnith-git/ohrm-wiki-sync")
CL_DIR = "logs/changelog"
CSV_PATH = os.path.join(CL_DIR, "changelog.csv")
XLSX_PATH = os.path.join(CL_DIR, "wiki_sync_changelog.xlsx")

PROJECT_OF = {
    "cm_daily_sync": "Compensation Management",
    "pnp_daily_sync": "PNP",
    "roster_daily_sync": "Roster",
    "orange_sign_daily_sync": "Orange Sign",
    "performance_core_daily_sync": "Performance Core",
    "performance_daily_sync": "Performance Core",
    "cs_features_daily_sync": "CS Features (HT)",
}
LOG_RE = re.compile(r"^logs/(?P<routine>[a-z_]+)/(?:TESTCREATE-)?(?P<ts>\d{4}-\d{2}-\d{2}T\d{6}Z)\.md$")


def _git(*args):
    return subprocess.run(["git", *args], capture_output=True, text=True, encoding="utf-8").stdout


def _all_log_paths():
    """Return {(branch, path)} for every run-log .md across all remote refs."""
    refs = [r for r in _git("for-each-ref", "--format=%(refname)", "refs/remotes/origin/").splitlines() if r]
    found = {}
    for ref in refs:
        for path in _git("ls-tree", "-r", "--name-only", ref, "logs/").splitlines():
            m = LOG_RE.match(path)
            if m and "/changelog/" not in path:
                # newest ref wins per path; first seen is fine (paths are unique by ts)
                found.setdefault(path, (ref, m.group("routine"), m.group("ts")))
    return found


def _frontmatter(text):
    if not text.startswith("---"):
        return {}
    end = text.find("\n---", 3)
    block = text[3:end] if end > 0 else ""
    fm = {}
    for line in block.splitlines():
        m = re.match(r"^([a-zA-Z0-9_]+):\s*(.*)$", line)
        if m:
            v = m.group(2).strip().strip('"')
            fm[m.group(1)] = v
    return fm


def _iso(ts):
    # 2026-06-07T090525Z -> 2026-06-07T09:05:25Z
    return f"{ts[:13]}:{ts[13:15]}:{ts[15:17]}Z" if re.match(r"\d{8}T\d{6}Z", ts.replace("-", "", 2)) else ts


def _ddmmyyyy(ts):
    return f"{ts[8:10]}/{ts[5:7]}/{ts[0:4]}"  # from YYYY-MM-DDThhmmssZ


def main():
    dry = "--dry" in sys.argv
    if not _ensure_openpyxl():
        return 0

    rows = _load_csv(CSV_PATH)
    seen_runs = {(r.get("run_utc", ""), r.get("routine", "")) for r in rows}
    seen_sig = {_sig(r) for r in rows}

    added = 0
    for path, (ref, routine, ts) in sorted(_all_log_paths().items(), key=lambda kv: kv[1][2]):
        run_utc = _iso(ts)
        if (run_utc, routine) in seen_runs:
            continue
        text = _git("show", f"{ref}:{path}")
        if not text:
            continue
        fm = _frontmatter(text)
        run_utc = fm.get("run_utc") or run_utc
        if (run_utc, routine) in seen_runs:
            continue
        project = PROJECT_OF.get(routine, routine)
        status = fm.get("status", "")
        run_date = _ddmmyyyy(run_utc)
        page = fm.get("target_page_name") or fm.get("page_name") or ""
        page_id = fm.get("target_page_id") or fm.get("page_id") or ""
        upd = fm.get("stories_updated") or fm.get("pages_updated") or "0"
        nochg = fm.get("stories_no_change") or fm.get("pages_no_change") or ""
        op = "Updated" if str(upd) not in ("0", "", "None") else "No-change"
        summary = (f"updated={upd} no-change={nochg} | "
                   f"stories={fm.get('stories_processed', fm.get('stories_found',''))} "
                   f"bugs={fm.get('bugs_found','')}").strip()
        row = {
            "run_utc": run_utc, "run_date": run_date, "routine": routine,
            "project": project, "status": status, "jira_key": "",
            "topic": f"{routine} run ({status})", "affected_area": "",
            "wiki_book": "", "wiki_page": page, "wiki_page_id": page_id,
            "crud_op": op, "previous_content": "—", "new_content": summary,
            "outcome": status, "confidence": "", "fix_version": fm.get("fix_version", ""),
            "evidence": f"from {ref.split('/')[-1]}:{path}",
        }
        if _sig(row) in seen_sig:
            continue
        rows.append(row)
        seen_sig.add(_sig(row))
        seen_runs.add((run_utc, routine))
        added += 1
        print(f"  + {routine} {run_utc} {status} ({page}) from {ref.split('/')[-1]}")

    if added == 0:
        print("CONSOLIDATE-OK - no new runs; changelog already current")
        return 0

    os.makedirs(CL_DIR, exist_ok=True)
    _write_csv(CSV_PATH, rows)
    _render_xlsx(rows, XLSX_PATH)
    print(f"CONSOLIDATE-OK - {added} run(s) added; ledger now {len(rows)} rows")

    if dry:
        print("CONSOLIDATE-DRY - skipping PUT to main")
        return 0
    token = os.environ.get("GITHUB_TOKEN")
    if not token:
        print("CONSOLIDATE-SKIP - GITHUB_TOKEN unset; CSV+xlsx written locally only")
        return 0
    for local_path in (CSV_PATH, XLSX_PATH):
        _put_main(local_path, token)
    return 0


def _api(url, token, method="GET", data=None):
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Authorization", f"Bearer {token}")
    req.add_header("Accept", "application/vnd.github+json")
    try:
        with urllib.request.urlopen(req) as resp:
            return resp.status, json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read().decode() or "{}")


def _put_main(local_path, token):
    url = f"https://api.github.com/repos/{REPO}/contents/{local_path}"
    for attempt in range(4):
        st, body = _api(f"{url}?ref=main", token)
        sha = body.get("sha") if st == 200 else None
        with open(local_path, "rb") as fh:
            content = base64.b64encode(fh.read()).decode()
        payload = {"message": f"chore(changelog): consolidate runs into main [{os.path.basename(local_path)}]",
                   "content": content, "branch": "main"}
        if sha:
            payload["sha"] = sha
        st, body = _api(url, token, method="PUT", data=json.dumps(payload).encode())
        if st in (200, 201):
            print(f"CONSOLIDATE-PUT - {local_path} -> main OK")
            return
        if st in (409, 422):
            continue  # concurrent update; re-GET sha and retry
        print(f"CONSOLIDATE-SKIP - PUT {local_path} failed HTTP {st}: {body.get('message','')}")
        return
    print(f"CONSOLIDATE-SKIP - PUT {local_path} gave up after retries")


if __name__ == "__main__":
    sys.exit(main())
