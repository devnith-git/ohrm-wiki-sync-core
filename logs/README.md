# Routine run logs

Each scheduled routine appends a markdown file here at the end of every run.
The commit history of this directory is the persistent audit trail for the
Jira → Wiki sync system.

## Layout

```
logs/
  cm_daily_sync/
    2026-05-12T013023Z.md
    2026-05-13T013021Z.md
    ...
  pnp_daily_sync/
    2026-05-13T003019Z.md
    ...
```

One file per routine fire, named with the UTC iso timestamp of the run.

## File format

Each log file has YAML frontmatter (machine-readable summary) followed by
the verbatim AUDIT SUMMARY block, a list of Jira items reviewed, a diff
summary, and any errors. See either prompt template under `routines/` for
the exact schema (STEP 7 in `cm_daily_sync.prompt.md`, STEP 9 in
`pnp_daily_sync.prompt.md`).

## Who writes here

The routines themselves, via the GitHub Contents API, using a fine-grained
PAT stored as `GITHUB_TOKEN` in the routine's environment variables (set in
the claude.ai routines UI). The PAT must have `contents:write` scoped to
this single repo. If unset, the log-commit step is silently skipped — the
wiki sync still runs.

## How to find a specific run

```bash
# By status
git log --grep='SUCCESS' -- logs/cm_daily_sync/
git log --grep='BLOCKED' -- logs/

# By date
git log --since=2026-05-01 --until=2026-05-15 -- logs/

# Most recent
ls -1t logs/cm_daily_sync/ | head -5
```

The commit message for each entry is
`chore(logs): <routine>_daily_sync run <ts> - <STATUS>` so `git log
--oneline` is also a fast index.

## Retention

No automatic purge — commits are cheap. If the directory grows unwieldy
(>1000 files per routine), add a quarterly archival job that moves old
files into a tag-archived branch.
