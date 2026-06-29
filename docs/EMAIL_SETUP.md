# Email notification setup (STEP 10)

The routine sends end-of-run logs via the Gmail API over HTTPS, authenticated
by OAuth2 refresh-token flow. Two paths, depending on what Google account
owns the OAuth client.

| | **Plan A — External + Testing** | **Plan B — Workspace + Internal** ⭐ |
|---|---|---|
| Google account that owns the GCP project | Personal Gmail (`xxx@gmail.com`) | Workspace shared service mailbox (e.g. `wiki-sync@orangehrm.com`) |
| Consent screen User Type | External | Internal |
| Refresh token expiry | **7 days** | Never |
| Google verification required | No (testing only) | No |
| Production-stable | No | Yes |
| Setup effort | ~15 min | ~30 min (incl. asking Workspace admin for a service mailbox) |
| Recommended for | First-time validation, throwaway testing | Anything you depend on |

---

## Plan A — External + Testing (current default for validation)

You did this. Refresh token expires every 7 days. When it expires,
`STEP 10` fails with `invalid_grant` and `send_notification.py` prints
the exact recovery command.

### Initial setup (already done)
1. Google Cloud Console → New project owned by a personal Gmail
2. APIs & Services → Library → enable Gmail API
3. APIs & Services → OAuth consent screen → External, Testing, add `gmail.send`
   scope, add yourself as Test user
4. APIs & Services → Credentials → Create OAuth client ID, type **Desktop app**
5. Locally: `python routines/oauth_setup.py CLIENT_ID CLIENT_SECRET`
6. Paste the four env-var values printed by the helper into both triggers'
   Environment variables in the claude.ai routines UI:
   `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, `GOOGLE_REFRESH_TOKEN`,
   `EMAIL_SENDER` (the Gmail address you authorised with)

### Renewal (every ~7 days)

When STEP 10 fails with `invalid_grant`:

```powershell
# From the repo root (any machine that has the cached creds):
python routines/oauth_setup.py
```

No arguments. The helper reads `CLIENT_ID` + `CLIENT_SECRET` from
`routines/.oauth_local.json` (cached at first-time setup, gitignored),
opens the browser, you click **Allow**, the new `GOOGLE_REFRESH_TOKEN`
is printed. Paste it into the routines UI for both CM and PNP triggers
(they share an environment, so one update covers both). ~30 seconds end
to end.

You can also pre-empt the expiry by running the renewal command on day 6
of every cycle — same flow, just before it breaks.

---

## Plan B — Workspace + Internal (the move when you stop wanting to babysit)

When ready, migrate to a Workspace-owned project. Refresh tokens issued
under Workspace Internal apps **never expire**.

### Prerequisites you'll need

- A Google Workspace **shared service mailbox** — i.e. a real user account
  in the Workspace, NOT a personal alias. Examples: `wiki-sync@orangehrm.com`,
  `noreply@orangehrm.com`, `automation@orangehrm.com`. Ask your Workspace
  admin to create one if it doesn't exist; the mailbox needs Send permission.
- Login credentials for that mailbox stored in your team's password manager
  so multiple people can administer.

### Setup

1. Sign in to <https://console.cloud.google.com> **as the service mailbox**
   (so the project is owned by the shared identity, not any individual)
2. New project: `ohrm-wiki-sync-routines` (or similar)
3. APIs & Services → Library → enable Gmail API
4. APIs & Services → OAuth consent screen
   - User Type: **Internal** ← this is the whole point
   - Add the `https://www.googleapis.com/auth/gmail.send` scope
   - Save. (No test users needed — Internal apps work for all Workspace users.)
5. APIs & Services → Credentials → Create OAuth client ID, type **Desktop app**
6. **IAM & Admin → IAM → Grant access** to 2–3 colleagues on the project so
   any of them can rotate the client secret if needed.
7. Locally (still signed in as the service mailbox in your browser):
   ```powershell
   python routines/oauth_setup.py NEW_CLIENT_ID NEW_CLIENT_SECRET
   ```
8. When the browser opens, sign in as the **service mailbox** (not your
   personal Workspace address). Click Allow.
9. Paste the four env-var values into both triggers in the routines UI,
   overwriting the Plan A values. `EMAIL_SENDER` becomes the service
   mailbox address (e.g. `wiki-sync@orangehrm.com`).

### Why this works long-term

- Tokens don't expire → no weekly babysitting.
- Sender is a shared mailbox → no individual identity tied to operations.
- Multiple admins on the GCP project → no single point of failure.
- When a team member leaves OHRM, nothing breaks.

---

## When to migrate from A to B

Migrate as soon as you've validated the routine works end-to-end on Plan A.
Concretely:

- One full SUCCESS run on Plan A (`email_send_status: SENT` in the YAML
  frontmatter, email visible in the recipient inbox).
- Then start the Plan B setup. The two can co-exist briefly — just don't
  swap the env vars in the routines UI until the new refresh token is in
  hand, then it's a single env-var update to flip over.

If you can't get the Workspace service mailbox right away (e.g. admin is
slow), the Plan A renewal command is fast enough that running it weekly
is annoying but survivable. Set yourself a reminder.

---

## Common failure modes and fixes

| Symptom | Cause | Fix |
|---|---|---|
| `email_send_status: SKIPPED` in run log | One of the four required env vars is unset in the routines UI | Add the missing var on the trigger |
| `email_send_error: ... invalid_grant ...` | 7-day expiry hit (Plan A) | `python routines/oauth_setup.py` (no args), paste new refresh token |
| `email_send_error: ... invalid_client ...` | `GOOGLE_CLIENT_ID` or `GOOGLE_CLIENT_SECRET` wrong / mistyped in the routines UI | Re-paste from `routines/.oauth_local.json` |
| `email_send_error: HTTP 403 ... precondition_failed ...` | `EMAIL_SENDER` doesn't match the account that authorised the refresh token | Either change `EMAIL_SENDER` to match, or re-run oauth_setup signed in as the desired sender |
| `Error 403: access_denied` during `oauth_setup.py` browser flow | Plan A only — the Gmail account isn't on the consent screen's Test users list | Add the Gmail to Test users in GCP Console → OAuth consent screen |
| `state mismatch (got '', ...)` from `oauth_setup.py` | Stray browser request (favicon, stale tab) hit the loopback listener first | Already fixed in current `oauth_setup.py`. Close any stale `localhost:8765` tabs and retry. |
