#!/usr/bin/env python3
"""
Send a routine's email-ready log file via the Resend API (HTTPS).

Why Resend, not SMTP, not Gmail
-------------------------------
The claude.ai routines runtime firewalls outbound SMTP at the network
layer — proven empirically on 2026-05-15 (TCP timeouts on port 587
with no RST). Outbound HTTPS is allowed.

We previously used the Gmail API. It worked, but required an OAuth2
refresh-token flow with two failure modes:
  1. The refresh token expires every 7 days if the Google Cloud app
     consent screen is `External + Testing`.
  2. Renewal requires a local browser flow (`oauth_setup.py`).

Resend is one HTTPS POST per recipient with a single static API key.
No OAuth, no token refresh, no expiry. Free tier is 3000 emails/month
and 100/day — comfortably above this repo's daily fire rate of ~5.

USAGE
-----
    python routines/send_notification.py <path/to/log_file.md>

ENV VARS
--------
Required (set in the claude.ai routines UI — never inlined in code):

    RESEND_API_KEY    API key from resend.com. Format: re_<random>.
                      Treat as a password.

Optional:

    EMAIL_FROM        From-address. Default: `onboarding@resend.dev`
                      (Resend's shared sandbox sender — works without
                      domain verification on the free tier). For a
                      custom address, verify your domain in the
                      Resend dashboard first, then set this to
                      `notifications@yourdomain.com`.
    EMAIL_FROM_NAME   Visible display name (default: "OHRM Wiki Sync")
    EMAIL_RECIPIENTS  Comma-separated recipient list. If unset, falls
                      back to resources/email_recipients.json.
    RESEND_TIMEOUT    HTTP timeout, secs (default: 30)

EXIT CODES
----------
  0   all recipients accepted (Resend returned 200 for each)
  4   bad argv count
  5   log file missing
  6   RESEND_API_KEY unset  (treated as SKIPPED — not a failure)
  7   log file missing EMAIL_BODY markers
  8   all recipients failed at the network/HTTPS level
  9   at least one recipient failed (partial)
"""
from __future__ import annotations

import json
import os
import re
import ssl
import sys
import urllib.error
import urllib.request
from pathlib import Path


RESEND_SEND_URL = "https://api.resend.com/emails"


def fail(msg: str, code: int = 1) -> None:
    print(f"send_notification: {msg}", file=sys.stderr)
    sys.exit(code)


def redact(text: str, *secrets: str) -> str:
    out = text
    for s in secrets:
        if s:
            out = out.replace(s, "<REDACTED>")
    return out


def extract_yaml_frontmatter(text: str) -> dict[str, str]:
    """Minimal YAML scalar parser — handles `key: value` between the
    first two `---` fences. Matches SKILL.md Section 5.1."""
    m = re.match(r"^---\s*\n(.*?)\n---\s*\n", text, re.S)
    if not m:
        return {}
    fields: dict[str, str] = {}
    for line in m.group(1).splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or ":" not in line:
            continue
        key, _, val = line.partition(":")
        key = key.strip()
        val = val.strip()
        if len(val) >= 2 and val[0] == val[-1] and val[0] in ('"', "'"):
            val = val[1:-1]
        fields[key] = val
    return fields


def extract_email_body(text: str) -> str | None:
    m = re.search(
        r"<!--\s*EMAIL_BODY_START\s*-->(.*?)<!--\s*EMAIL_BODY_END\s*-->",
        text,
        re.S,
    )
    return m.group(1).strip() if m else None


def load_recipients(repo_root: Path) -> list[str]:
    """Recipient resolution:
    1. EMAIL_RECIPIENTS env var (comma-separated)
    2. resources/email_recipients.json (primary[] + additional[])
    """
    out: list[str] = []
    seen: set[str] = set()

    env_val = os.environ.get("EMAIL_RECIPIENTS", "").strip()
    if env_val:
        raw = [p.strip().strip('"').strip("'") for p in env_val.split(",")]
    else:
        path = repo_root / "resources" / "email_recipients.json"
        if not path.exists():
            fail(
                f"no recipient source — set EMAIL_RECIPIENTS in the "
                f"routine env vars, or commit "
                f"resources/email_recipients.json with at least one "
                f"address.",
                code=2,
            )
        data = json.loads(path.read_text(encoding="utf-8"))
        raw = list(data.get("primary", [])) + list(data.get("additional", []))

    for addr in raw:
        if not isinstance(addr, str):
            continue
        addr = addr.strip()
        if "@" not in addr or len(addr) < 5:
            print(f"send_notification: WARN skipping malformed recipient {addr!r}")
            continue
        if addr in seen:
            continue
        seen.add(addr)
        out.append(addr)

    if not out:
        fail("no valid recipients found", code=3)
    return out


def build_plain_text_fallback(fields: dict[str, str]) -> str:
    """Build a minimal plain-text body from the YAML frontmatter for
    email clients that don't render HTML."""
    lines = [
        f"Routine: {fields.get('routine_slug', '(unknown)')}",
        f"Run:     {fields.get('run_utc', '(unknown)')}",
        f"Status:  {fields.get('status', '(unknown)')}",
        "",
        "Full report is in the HTML version of this email.",
        "",
        f"Log: {fields.get('log_html_url', '(no GitHub log)')}",
    ]
    return "\n".join(lines)


def send_via_resend(
    api_key: str,
    sender: str,
    sender_name: str,
    recipient: str,
    subject: str,
    html: str,
    plain: str,
    timeout: int,
) -> tuple[bool, str]:
    """POST one email through the Resend API. Returns (ok, detail)."""
    from_field = f"{sender_name} <{sender}>" if sender_name else sender
    payload = json.dumps({
        "from": from_field,
        "to": [recipient],
        "subject": subject,
        "html": html,
        "text": plain,
    }).encode("utf-8")
    req = urllib.request.Request(
        RESEND_SEND_URL,
        data=payload,
        method="POST",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "User-Agent": "ohrm-wiki-sync/1.0",
            "Accept": "application/json",
        },
    )
    try:
        ctx = ssl.create_default_context()
        with urllib.request.urlopen(req, timeout=timeout, context=ctx) as resp:
            body = resp.read().decode("utf-8", errors="replace")
            return True, body
    except urllib.error.HTTPError as exc:
        try:
            body = exc.read().decode("utf-8", errors="replace")
        except Exception:
            body = ""
        return False, f"HTTP {exc.code}: {body}"
    except (urllib.error.URLError, OSError, ssl.SSLError) as exc:
        return False, f"network: {exc}"


def main() -> int:
    if len(sys.argv) != 2:
        fail("usage: send_notification.py <path/to/log_file.md>", code=4)

    log_path = Path(sys.argv[1]).resolve()
    if not log_path.exists():
        fail(f"log file not found: {log_path}", code=5)

    repo_root = log_path.parent.parent.parent

    api_key = os.environ.get("RESEND_API_KEY", "").strip()
    sender = os.environ.get("EMAIL_FROM", "onboarding@resend.dev").strip()
    sender_name = os.environ.get("EMAIL_FROM_NAME", "OHRM Wiki Sync").strip()
    try:
        timeout = int(os.environ.get("RESEND_TIMEOUT", "30"))
    except ValueError:
        timeout = 30

    if not api_key:
        fail(
            "RESEND_API_KEY not set. Set it in the routine's Environment "
            "Variables (claude.ai UI). Get the key from "
            "https://resend.com/api-keys (free tier).",
            code=6,
        )

    log_text = log_path.read_text(encoding="utf-8")
    fields = extract_yaml_frontmatter(log_text)
    html_body = extract_email_body(log_text)
    if not html_body:
        fail(
            f"log file {log_path.name} is missing "
            "EMAIL_BODY_START/END markers — STEP 9 produced a "
            "malformed file",
            code=7,
        )

    subject = fields.get("email_subject") or "OHRM Wiki Sync notification"
    recipients = load_recipients(repo_root)
    plain_body = build_plain_text_fallback(fields)

    print(
        f"send_notification: provider=resend "
        f"sender={sender} from_name={sender_name!r} "
        f"recipients={len(recipients)} body_bytes={len(html_body)} "
        f"api_key_len={len(api_key)} subject={subject!r}"
    )

    sent = 0
    failures: list[tuple[str, str]] = []
    for rcpt in recipients:
        ok, detail = send_via_resend(
            api_key, sender, sender_name, rcpt,
            subject, html_body, plain_body, timeout,
        )
        if ok:
            sent += 1
            preview = detail[:160].replace("\n", " ")
            print(f"send_notification: SENT to {rcpt}  resp={preview}")
        else:
            masked = redact(detail, api_key)
            failures.append((rcpt, masked))
            print(f"send_notification: FAILED for {rcpt}: {masked}")

    print(
        f"send_notification: total_sent={sent}/{len(recipients)} "
        f"failures={len(failures)}"
    )
    if sent == 0 and failures:
        return 8
    return 9 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
