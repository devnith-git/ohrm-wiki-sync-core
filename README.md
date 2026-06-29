# ohrm-wiki-sync-core

**Shared engine + canonical rules** for the OHRM Jira → Enterprise-Wiki
sync fleet. This repo holds everything common to *every* project; each
project has its own repo that **pulls this core at fire time**.

## What lives here (shared, single source of truth)

```
automation/    standalone Python CLI (sync.py, resolver.py, …)
routines/      helper scripts: deploy.py, scaffold.py, send_notification.py,
               update_changelog.py, consolidate_changelog.py, oauth_setup.py,
               mcp_connectors.json   (NO per-project *.prompt.md here)
resources/     canonical authorities — read by every project at fire time:
                 release-filter-policy.md         (top of authority)
                 bug-requirement-filter-policy.md (DEFAULT defect carve-out;
                                                   projects may override locally)
                 specification-writing-guideline.md
                 SKILL.md
                 WIKI_PAGE_RENDER.md
                 CS_FEATURE_ROUTING_SKILL.md
                 wiki_destination.json            (shelf/book catalog +
                                                   per-routine destinations)
                 email_template.html, email_recipients.json
docs/          architecture, deploy, security, rollout
tests/         smoke_test.py
logs/changelog/  aggregate ledger (historical)
```

## Who consumes it

Per-project repos, one per routine:

| Project | Repo |
|---|---|
| Compensation Management | `ohrm-wiki-sync-compensation` |
| CS Features (HT)        | `ohrm-wiki-sync-ht-cs-features` |
| Performance Core        | `ohrm-wiki-sync-performance-core` |
| Roster                  | `ohrm-wiki-sync-roster` |
| Orange Sign             | `ohrm-wiki-sync-orange-sign` |

Each project repo holds only: its routine prompt, its run logs, and its
**own** `resources/bug-requirement-filter-policy.md` (defect rules it can
change without affecting other projects). At fire time the routine clones
THIS repo into `_core/` and reads the shared canon from `_core/resources/`.

## Updating the engine

Change shared rules / engine here. Every project picks the change up on
its next fire automatically — no per-project copy needed. This is the
single point of truth that branches/duplicate-repos would otherwise drift.
