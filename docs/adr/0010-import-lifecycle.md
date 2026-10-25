# ADR-0010: Import lifecycle: a history the client manages

- **Status:** Accepted (2026-10-25)
- **Date:** 2026-10-25
- **CLAUDE.md reference:** Hard constraints (no invented data, euros traceable, read-only by default, done means a client can do it, every number explained), Architecture (ingestion, data model), Conventions

## Context

Today an import is a one-off replace. `run_import` maps the uploaded files into standard CSVs, then `replace_plant_data` deletes and rewrites every record type the upload brings. Rows do not say which import they came from, an upload cannot be changed or taken back, and the engine calculates from the latest import's `standard/` files, not from the database. Edits on the Setup and Calendar pages change the database but do not recalculate the answer, so a page can show an answer that no longer matches the data.

Daily use needs more: a plant sends a new week of events, not twelve weeks again. A wrong file must be replaced, a wrong row fixed, a wrong upload taken back. Both built-in mappings generate `event_id` as `<file>-<line>` (`generate: row_id`), so the same id means different events in two uploads of `events.csv`.

The user decided on 2026-10-25: PostgreSQL + TimescaleDB stays the only database; the engine runs locally and reads the big data sets from the database; the event log adds and lists replace; rows can be fixed in the app; refresh is automatic with a banner.

## Decision

**1. Files are the source.** An uploaded file is never changed. Each import keeps its source files (`import_data` volume) until the client deletes the import. Everything in the plant's tables can be rebuilt from the kept imports plus corrections.

**2. Every row knows where it came from.** Each stored row carries `import_id` (and file name) or `source = 'app'` for rows entered on the Setup or Calendar page. App rows are never touched by an import or a rebuild.

**3. The event log adds; lists replace.**

| Kind | Files | On a new import |
|---|---|---|
| Event log | events (touchpoints) | Added. An event already stored is counted once. |
| Lists | steps, shift sheet (calendar), teams and team plan, orders (jobs), products, routings, breaks, holidays | The list in the newer import replaces the older one. Lists the import does not bring stay as they were. |

Overlapping periods are allowed. The import report shows the period the import added and the plant's whole period.

**4. Recognising the same event across uploads.**

- When the mapping reads the plant's own event id from the file, that id identifies the event.
- Otherwise (`generate: row_id`) the event is identified by its content: step, job, event type and time (to the second), plus quantity/reason only to tell apart two real events at the same moment. The stored id is a hash of that content, so it does not depend on file name or line.
- The same event in a later upload is counted once. With a real id and a changed value (other quantity or reason), the later upload's value wins and the report counts it as changed. Without a real id a changed value is a new event; the report says how many events were already there.

**5. Rebuild from the kept imports.** One rebuild function produces the plant's data: kept imports in upload order (events added, lists replaced), then corrections, then app rows. It runs inside one tenant transaction under the plant lock. Run, replace, delete and corrections all use it. A failed rebuild leaves the previous data in use and says so in plain words. Rebuilding everything gives the same data as importing one by one.

**6. The engine reads the database.** Facts, detection and loss read the plant from the rebuilt rows in PostgreSQL through a loader in `constraint_engine`, not from an import's files. The engine still runs locally (worker and the offline `diagnose` on files). Reading a plant from the database gives the same answers as reading its files.

**7. A fixed row is a correction next to the original.** Fixing a rejected or wrong row in the app stores a correction: the original value, the new value, the reason, the role and account, and the time. The original stays. Every number that uses a corrected row says so in its provenance. Personal columns are dropped on read and can never be shown, fixed or restored.

**8. Changing files.** An import's files can be replaced, added or removed before or after it runs. The page shows what will change (rows added, replaced, removed, and the period) before the client confirms in the page. Before the run, files can simply be added, replaced or removed and the file check runs again. After the run, a change makes a new version of that import; the old version is marked replaced and kept in the history until the client deletes it. Every change is audit-logged (who, when, which file; never contents).

**9. Deleting is for real.** The client can delete one upload, one import, or all of a plant's data. Delete removes the files from disk and the rows from the database, then rebuilds from the rest. What remains is an audit line: who (role and account), when, what (import id, file names, row counts), never the data itself.

**10. Every data change refreshes the answer.** A data change is: an import run, a file replaced, added or removed, a row fixed or its fix undone, an import deleted, and an edit on the Setup or Calendar page. Each one starts a rebuild (where needed) and a recalculation of facts, detection and loss. While it runs every page shows a banner; the answer says how old its data is; a failed refresh keeps the last answer and says what failed and what to do.

**11. Who may do what.** Uploading, changing files, fixing rows and deleting are decisions in the access model (ADR-0007). Other roles see the history and the corrections read-only, with a line saying who can change them.

## Consequences

- A migration adds `import_id`/`source` to the plant tables, a corrections table, and a content-based event id. Existing data is tagged with the import it came from.
- `replace_plant_data` becomes the rebuild; `facts.py` reads the database through the new loader.
- Imports get a history page, file change, preview, rejected rows with fixes, and delete.
- Setup and Calendar edits trigger a recalculation, which costs a few seconds per change on the 8 GB Mac (measured in sequence 02).
- Known answers for split, repeated, corrected and deleted imports are fixed before code (`data/synthetic/import_cases/expected_answers.yaml`).
- Hosting later uses the same model: the same Postgres, with files in object storage instead of a volume.
