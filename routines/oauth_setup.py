#!/usr/bin/env python3
"""
*** DEPRECATED 2026-05-24 ***
This script is no longer used. The repo migrated to Resend on
2026-05-24. The Gmail API path is preserved here only as a fallback
option. To re-enable Gmail email, see git history before the Resend
migration commit (chore(email): migrate to Resend) and revert the
routine prompts + send_notification.py + SKILL.md to that state.

----

Local helper to mint a Google OAuth2 refresh token for the Gmail API.
Run on YOUR machine (not the routine runtime).

WHEN TO RUN THIS
----------------
- **First time** — initial setup. Pass CLIENT_ID and CLIENT_SECRET as
  args; they're cached to `.oauth_local.json` (gitignored) for later
  re-runs.
- **Renewal** — when STEP 10 starts failing with `invalid_grant` (the
  documented 7-day expiry of refresh tokens issued by apps in
  "External + Testing" consent status). Just run with NO args; the
  cached client credentials are reused so all you do is click Allow
  in the browser and paste the new refresh token into the routines UI.
  Whole renewal takes ~30 seconds.

USAGE
-----
First-time setup:
    python routines/oauth_setup.py CLIENT_ID CLIENT_SECRET

Renewal (after first-time setup has cached the credentials):
    python routines/oauth_setup.py

You get CLIENT_ID and CLIENT_SECRET from the Google Cloud Console:

  1. https://console.cloud.google.com -> New Project (or pick an existing one)
  2. APIs & Services -> Library -> enable "Gmail API"
  3. APIs & Services -> OAuth consent screen
       - User Type:
           - **Internal** if you have Google Workspace and the sender
             will only be your Workspace's own users (RECOMMENDED — no
             token expiry issues, no Google verification needed).
           - **External** if personal Gmail. Caveat: refresh tokens
             expire after 7 days while the app's Publishing Status is
             "Testing". For long-lived production usage on personal
             Gmail you'd need Google to verify the app (1-2 weeks).
       - Add the gmail.send scope (sensitive scope).
       - Test users (External only): add the Gmail address you're
         sending from.
  4. APIs & Services -> Credentials -> Create Credentials -> OAuth client ID
       - Application type: **Desktop app**
       - Name: anything (e.g. "ohrm-wiki-sync-routine")
       - Download the JSON or copy the Client ID + Client Secret strings.

What this script does
---------------------
  1. Spins up a local HTTP server on http://localhost:8765
  2. Opens your default browser to Google's OAuth consent page with
     the redirect_uri pointing at that local server
  3. After you sign in and grant access, Google redirects with a
     one-time authorization code
  4. The script exchanges that code at Google's token endpoint for a
     refresh token (long-lived) + access token (short-lived)
  5. Prints the four env-var values you need to set on the routine.

NOTHING is saved to disk. The refresh token only appears in this
script's stdout — copy it directly into the claude.ai routines UI.

SAFETY
------
- Run on your own machine, not on shared infrastructure.
- The local HTTP listener only accepts ONE callback then exits.
- The redirect URL contains a `state` token; if it doesn't match, the
  exchange is rejected (CSRF defence).
- The refresh token printed to stdout grants long-lived send-as access
  to the Google account that authorised it. Treat as a password.
"""
from __future__ import annotations

import http.server
import json
import secrets
import socketserver
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import webbrowser


SCOPE = "https://www.googleapis.com/auth/gmail.send"
REDIRECT_PORT = 8765
REDIRECT_URI = f"http://localhost:{REDIRECT_PORT}"
AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"

# Local cache of CLIENT_ID + CLIENT_SECRET so subsequent renewal runs
# don't need them re-typed. Lives next to this script, gitignored.
# Refresh token is NEVER cached here (it only lives in the routines UI).
import os as _os
from pathlib import Path as _Path
_CACHE_PATH = _Path(__file__).resolve().parent / ".oauth_local.json"


def _load_cached_creds() -> tuple[str, str] | None:
    """Return (client_id, client_secret) cached from a previous run,
    or None if the cache file is missing / malformed."""
    if not _CACHE_PATH.exists():
        return None
    try:
        data = json.loads(_CACHE_PATH.read_text(encoding="utf-8"))
        cid = (data.get("client_id") or "").strip()
        cs = (data.get("client_secret") or "").strip()
        if cid and cs:
            return cid, cs
    except Exception:
        pass
    return None


def _save_cached_creds(client_id: str, client_secret: str) -> None:
    """Persist CLIENT_ID + CLIENT_SECRET to the gitignored cache file so
    the next renewal run can read them. Does NOT cache the refresh
    token — that only ever lives in the routines UI."""
    _CACHE_PATH.write_text(
        json.dumps(
            {"client_id": client_id, "client_secret": client_secret},
            indent=2,
        ),
        encoding="utf-8",
    )
    # Tighten file permissions on Unix-like systems (no-op on Windows).
    try:
        _os.chmod(_CACHE_PATH, 0o600)
    except Exception:
        pass


class _Server(socketserver.TCPServer):
    """Single-shot TCP server holding the auth code captured from the redirect."""
    allow_reuse_address = True
    auth_code: str | None = None
    auth_error: str | None = None
    expected_state: str = ""


class _Handler(http.server.BaseHTTPRequestHandler):
    server: _Server

    def do_GET(self) -> None:
        parsed = urllib.parse.urlparse(self.path)
        params = urllib.parse.parse_qs(parsed.query)

        # Ignore requests that aren't the OAuth callback (e.g. /favicon.ico,
        # stray refreshes of localhost:8765 from a previous attempt, browser
        # prefetches). A real OAuth callback always carries either `code`
        # (success) or `error` (Google declined). If neither is present,
        # this isn't the callback we're waiting for — quietly 404 and keep
        # waiting for the real one.
        if "code" not in params and "error" not in params:
            self.send_response(404)
            self.end_headers()
            return

        # CSRF defence: the `state` round-trip must match exactly. Only
        # check this on real callback requests (above guard ensures it).
        returned_state = params.get("state", [""])[0]
        if returned_state != self.server.expected_state:
            self.server.auth_error = (
                f"state mismatch (got {returned_state!r}, "
                f"expected {self.server.expected_state!r})"
            )
            self.send_response(400)
            self.end_headers()
            self.wfile.write(b"state mismatch; aborting")
            return

        if "code" in params:
            self.server.auth_code = params["code"][0]
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(
                b"<!doctype html><meta charset='utf-8'>"
                b"<style>body{font-family:Arial;text-align:center;padding:60px;}"
                b"h1{color:#27ae60;}p{color:#7f8c8d;}</style>"
                b"<h1>Authorization received</h1>"
                b"<p>You can close this tab. The script will print your "
                b"refresh token in the terminal.</p>"
            )
        elif "error" in params:
            self.server.auth_error = params["error"][0]
            self.send_response(400)
            self.end_headers()
            self.wfile.write(f"OAuth error: {params['error'][0]}".encode())
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, fmt: str, *args: object) -> None:
        # Suppress noisy default access log
        pass


def main() -> int:
    # Two invocation modes:
    #   2 args -> first-time setup. Use the provided CLIENT_ID +
    #             CLIENT_SECRET, cache them locally for future runs.
    #   0 args -> renewal. Read CLIENT_ID + CLIENT_SECRET from the
    #             local cache. The browser flow still runs so a fresh
    #             refresh token is minted.
    if len(sys.argv) == 1:
        cached = _load_cached_creds()
        if cached is None:
            print(__doc__.strip())
            print(
                "\nERROR: no cached credentials at "
                f"{_CACHE_PATH.name}.\n"
                "First-time setup needs both CLIENT_ID and CLIENT_SECRET:\n"
                "  python routines/oauth_setup.py CLIENT_ID CLIENT_SECRET\n"
                "After that, run with no args to renew the refresh token."
            )
            return 1
        client_id, client_secret = cached
        print(f"Renewal mode: using cached CLIENT_ID + CLIENT_SECRET "
              f"from {_CACHE_PATH.name}")
    elif len(sys.argv) == 3:
        client_id = sys.argv[1].strip()
        client_secret = sys.argv[2].strip()
        if not client_id or not client_secret:
            print("ERROR: empty CLIENT_ID or CLIENT_SECRET.")
            return 1
        _save_cached_creds(client_id, client_secret)
        print(f"First-time setup: cached CLIENT_ID + CLIENT_SECRET to "
              f"{_CACHE_PATH.name} for fast renewal next time.")
    else:
        print(__doc__.strip())
        print(
            "\nERROR: expected either 0 args (renewal, reads cached creds) "
            "or 2 args (first-time setup: CLIENT_ID and CLIENT_SECRET)."
        )
        return 1

    state = secrets.token_urlsafe(32)
    params = {
        "client_id": client_id,
        "redirect_uri": REDIRECT_URI,
        "response_type": "code",
        "scope": SCOPE,
        "access_type": "offline",   # required for refresh_token
        "prompt": "consent",        # force consent so refresh_token is returned every time
        "state": state,
    }
    auth_url = AUTH_URL + "?" + urllib.parse.urlencode(params)

    server = _Server(("localhost", REDIRECT_PORT), _Handler)
    server.expected_state = state
    server_thread = threading.Thread(target=server.serve_forever, daemon=True)
    server_thread.start()

    print()
    print("=" * 70)
    print("OAuth setup — Gmail API refresh token")
    print("=" * 70)
    print(f"\n1. Opening browser to Google's consent page...")
    print(f"   If your browser doesn't open, paste this URL manually:")
    print(f"\n   {auth_url}\n")

    try:
        webbrowser.open(auth_url)
    except Exception as exc:
        print(f"   (couldn't auto-open browser: {exc})")

    print("2. Waiting for the redirect on http://localhost:8765 ...")
    print("   (sign in, grant access, then return here)\n")

    # Wait for callback handler to record either auth_code or auth_error
    deadline = time.time() + 300  # 5-minute upper bound
    while server.auth_code is None and server.auth_error is None:
        if time.time() > deadline:
            print("ERROR: no callback received within 5 minutes. Re-run the script.")
            server.shutdown()
            return 1
        time.sleep(0.2)

    server.shutdown()

    if server.auth_error:
        print(f"ERROR from Google: {server.auth_error}")
        if server.auth_error == "access_denied":
            print("(You declined the consent screen. Re-run and click Allow.)")
        return 1

    code = server.auth_code
    print(f"3. Authorization code captured. Exchanging it for tokens...")

    # POST to the token endpoint with grant_type=authorization_code
    token_payload = urllib.parse.urlencode({
        "client_id": client_id,
        "client_secret": client_secret,
        "code": code,
        "redirect_uri": REDIRECT_URI,
        "grant_type": "authorization_code",
    }).encode("ascii")
    req = urllib.request.Request(
        TOKEN_URL,
        data=token_payload,
        method="POST",
        headers={
            "Content-Type": "application/x-www-form-urlencoded",
            "User-Agent": "ohrm-wiki-sync-oauth-setup/1.0",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            tokens = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        print(f"ERROR: token exchange failed (HTTP {exc.code}): {body}")
        return 1
    except urllib.error.URLError as exc:
        print(f"ERROR: network error: {exc}")
        return 1

    if "refresh_token" not in tokens:
        print("ERROR: response did NOT include a refresh_token.")
        print("This usually means the consent screen was for an account that")
        print("already authorised this client; Google only issues a new")
        print("refresh_token on first consent OR when prompt=consent is used.")
        print("\nFull response (sanitised):")
        for k, v in tokens.items():
            if k in ("access_token", "id_token"):
                print(f"  {k}: <{len(v)} chars>")
            else:
                print(f"  {k}: {v}")
        print("\nTo force a new refresh_token: revoke previous access at")
        print("https://myaccount.google.com/permissions then re-run this script.")
        return 1

    refresh_token = tokens["refresh_token"]

    print()
    print("=" * 70)
    print("SUCCESS")
    print("=" * 70)
    print("Set these env vars on each routine in the claude.ai UI")
    print("(Settings -> Environment variables):")
    print()
    print(f"  GOOGLE_CLIENT_ID      = {client_id}")
    print(f"  GOOGLE_CLIENT_SECRET  = {client_secret}")
    print(f"  GOOGLE_REFRESH_TOKEN  = {refresh_token}")
    print(f"  EMAIL_SENDER          = <the Gmail address you just signed in as>")
    print()
    print("Optional:")
    print(f"  EMAIL_FROM_NAME       = OHRM Wiki Sync   (default if unset)")
    print(f"  GMAIL_TIMEOUT         = 30               (default if unset)")
    print()
    print("Notes:")
    print("- Set the same four env vars on BOTH triggers (CM and PNP); they")
    print("  share the same environment so a single set covers both.")
    print("- The refresh token does NOT expire if your OAuth app is set to")
    print("  'Internal' (Workspace) or 'External + In production'. If the")
    print("  app is 'External + Testing', the token expires after 7 days.")
    print("- EMAIL_SENDER MUST match the Google account that just authorised")
    print("  this script (or be a verified send-as alias in that account).")
    print("=" * 70)
    return 0


if __name__ == "__main__":
    sys.exit(main())
