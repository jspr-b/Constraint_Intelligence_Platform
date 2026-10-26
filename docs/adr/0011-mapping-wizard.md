# ADR-0011: Mapping wizard: the app suggests, the client confirms

- **Status:** Accepted (2026-10-26)
- **Date:** 2026-10-26
- **CLAUDE.md reference:** Hard constraints (no individual employee monitoring, no invented data, done means a client can do it, no dead ends, plain words), Recommendations and AI (the language model never generates numbers), Architecture (ingestion), Core concepts (steps and touchpoints), Conventions

## Context

The app reads two export formats (`packages/connectors/mappings/generic` and `workshop_scans`). "Generic" is in fact plant A's: fixed Dutch column names, `;` as separator, day-month dates and plant A's machine codes. A new plant needs a developer to copy a mapping file and fill in its column names and code tables. That does not scale, and the product cannot launch without the founder.

The flow of the plant (the steps jobs pass, in which order, and how often) is already derived per job from touchpoint times (`constraint_engine.reconstruct.flow`), but the client never sees it, so they cannot tell us when we read their plant wrong.

The user decided on 2026-10-26: importing must be as simple as possible; the client uploads whatever export they have; the app works out the rest and asks only what it cannot guess; right after upload the client sees the flow found in the data and can correct it.

## Decision

**1. The app suggests, the client confirms.** Every match (file role, column, code, format) is either certain by rule or a suggestion. Nothing a client did not confirm, and that was not certain, is used. The app never guesses silently. One summary screen shows all matches; only the unclear ones are asked, one plain question each.

**2. The whole export at once.** The client uploads every file of the export together (CSV, Excel with several sheets, a zip). The app sorts each file or sheet into a role and links them:

| Role | Needed | What it gives |
|---|---|---|
| Event log (touchpoints) | yes, or hour bookings | job, step, time, what happened |
| Hour bookings | instead of an event log | job, step, start + duration or date + hours |
| Steps list | yes | step codes, names, stations, kind |
| Shift sheet | yes | shifts, breaks, positions per step |
| Jobs (orders) | no | due dates, job value, material cost |
| Products, routings | no | prices, standard times, setup families |
| Not used | | shown with the reason, never silently dropped |

Links (which column in the event log is the step code of the steps list, which is the job of the jobs file) are found from shared values and confirmed like any other match.

**3. How matches are found.**

- **Rules first:** known column names in several languages and ERP styles, value patterns (dates, codes, numbers), and the values themselves (a column whose values are the step codes of the steps list is the step).
- **AI second (Claude API), privacy limited.** The AI sees only file and column names, the rejected-row reasons, and at most 5 anonymised example values per column. Never whole files, never personal columns, never numbers to calculate. It may suggest: column matches, the meaning of codes (`GEREED` → finish), and a plain explanation of a data problem. It may not suggest flow corrections, figures or actions. Every AI suggestion is marked "suggested by AI" and confirmed by the client like a rule suggestion.
- **Without an API key** the wizard runs on rules only and shows "AI not connected" where AI would help. All AI code is built and tested now with a fake client; setting the key is the only step to switch it on (CLAUDE.md, "AI API: to connect").

**4. Codes and formats.** Machine and step codes, status codes, date and time formats, the time zone, decimal and thousands separators, and true/false words are read from the values and shown as plain examples ("20-07-2026 10:11 is 20 July 2026, 10:11 Amsterdam time"). A status code that cannot be matched is asked; until it is answered its rows are not used and the import waits.

**5. Hour bookings are accepted with lower confidence.** A booking (start + duration, or date + hours per job and step) becomes a start and a finish touchpoint. Queues, waits and states that need real scan times are Missing or lower in confidence, and every answer that uses bookings says so in plain words. Nothing is invented between bookings.

**6. The flow after upload.** Right after the matches are confirmed, the app shows the flow found in the data on a canvas: stations as boxes, steps as cards inside them, arrows with the share of jobs (main route, side routes, rework). The client may:

- add a step (name, kind: machine, handmade, check, transport or storage; station; place in the flow; capacity optional),
- add a touchpoint (a scan point without work, shown as a dot on an arrow),
- add a station, move a step to another station, rename, or mark an arrow as wrong,
- then confirm the flow.

Steps, stations or touchpoints the client adds without data are shown as "not measured"; nothing is invented for them. The flow found in the data is never changed by the app or the AI; the client's corrections are stored next to it. Each flow edit is a data change and recalculates the answer (ADR-0010 §10). A clickable mockup of the canvas is approved by the user before it is built.

**7. Remembered per plant.** The confirmed mapping (file roles, column matches, code tables, formats, links) and the flow corrections are stored per plant, as a versioned mapping in the database, with who confirmed it (role) and when. The next export uses it without questions. Only what is new (a new column, a new code, a changed file) is asked, and that import waits until it is answered. The built-in mapping files stay for the demo and tests; a plant's stored mapping has the same shape (`MappingSet`).

**8. Who confirms.** IT / ERP owner and planner confirm matches and the flow, as an access decision (ADR-0007) the COO can move. Other roles see the confirmed mapping and flow read-only with who can change them.

**9. Never per person.** Personal columns (names, badges, employee numbers) are recognised and dropped on read. They are never shown, stored, matched or sent to the AI; the summary says only "1 personal column not read".

**10. Excel template as fallback.** A downloadable Excel template (tabs: events, steps, shifts, each with example rows) always works without questions, for plants whose export the wizard cannot read.

**What is stored per plant:** the confirmed mapping (versions), the code tables, the flow corrections, who confirmed each (role) and when. **What is never sent to the AI:** file contents beyond 5 anonymised examples per column, personal columns, numbers to calculate, plant or company names, account details.

## Consequences

- New tables for a plant's mapping versions and flow corrections; a migration.
- `cip_connectors` gains recognisers (file roles, columns, codes, formats) that produce a `MappingSet`; the importer runs it like the built-in mappings.
- An AI client interface with a fake for tests; the real client is used only when the key is set.
- The import page gets the wizard steps: upload all → summary of matches → questions → flow → confirm → run.
- The flow canvas needs React Flow (already in the stack) and an approved mockup first.
- Test exports in the style of several ERPs/MES, each built from a plant with a known answer, are fixed before code (`data/synthetic/wizard_cases/*/expected.yaml`).
- The data checklist, export guide and IT guide say: send what you have; the app will ask.
