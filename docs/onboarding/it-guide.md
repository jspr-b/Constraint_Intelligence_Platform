# Mapping and connection guide for IT

For the plant's IT or ERP owner. It covers how your exports are mapped, how data gets in now and in the pilot, what the platform never does, and how logins work. It matches the Import, Connections and Users pages.

**What to send:** to start, the event log, a steps list and a shift sheet; everything else adds euros, actions or confidence (`erp-export-guide.md`, `data-checklist.md`). The Import page says the same, per file.

## 1. How mapping works

Your files keep their own column names. A **mapping** (one YAML file per source system) says, for every field of the standard data model, which of your columns fills it and how the value is converted. The generic mapping for a Dutch ERP + MES export is `packages/connectors/mappings/generic/mapping.yaml`; the columns it reads are listed in `erp-export-guide.md`.

What a mapping contains:

| Part | Example | Notes |
|---|---|---|
| Source settings | separator `;`, decimal `,`, date format `%d-%m-%Y %H:%M`, time zone `Europe/Amsterdam` | Local times become UTC on import |
| Tables | `mes_events` → `events` | One source file can fill several standard tables |
| Fields | `resource_code: { from: Werkplek, code_table: resource }` | `type` converts numbers, money (to euro cents), dates, lists |
| Code tables | `resource: { LAS2: WLD-02 }`, `event_status: { GEREED: end }` | Your codes → standard codes |
| Personal columns | `personal_columns: [Medewerker]` | Dropped while reading, on top of the built-in list of personal column names |

**Adjusting a mapping or code table.** Copy the generic mapping for your source system, change column names and code tables, and keep it under version control. During the pilot we make these changes with you; editing mappings in the platform is a later step.

**Unknown codes are never guessed.** A row with a code that is not in the code table (e.g. machine `LAS9`) is rejected with its reason. The Data quality page lists rejected rows per file; add the code to the code table and run the import again.

**Check before running.** After uploading, the Import page shows every column of every file: what it maps to, an example value, the conversion, and which columns are *not imported* because they are personal data. Personal columns never show an example value.

**Exports in another layout: the mapping wizard.** When your export does not match a built-in mapping, upload it as it is (whole export, zip or workbook). Step 1 on the Import page says what each file is; step 2 (*Map columns*) says which column fills which field, asks only about columns it cannot tell, and shows one summary for you to confirm. Columns are matched by rules first (column names in English, Dutch and German, and what the values look like: times, numbers, codes that appear in another file). You can change any choice before confirming.

## 2. How data comes in

| Stage | How | Status |
|---|---|---|
| 1. File upload | The whole export on the Import page (CSV, TXT, Excel with several sheets, or a zip). The page shows what each file is, how sure, and how the files link; you name or skip a file it cannot place. The import runs in a background worker, then the data checklist and data quality report are updated | Available |
| 2. Scheduled export | The same files dropped nightly or hourly on SFTP, or a read-only database view queried on a schedule | Planned for the pilot; shown as *not configured* on the Connections page |
| 3. Live connections | ERP APIs; machine signals via OPC UA or MQTT through an edge gateway | Later |

All stages end in the same standard data model, so pages and calculations do not change when a plant moves from uploads to scheduled exports.

For stage 2 we will ask for: an SFTP account with write access to one folder (or a database user with `SELECT` on one view per export), the schedule, and the network route (IP allow-list or VPN). The platform only reads.

### After the first upload

| What you do | What happens |
|---|---|
| Upload a new export (Import page) | Nothing changes until you run it. The page first shows what it will change: events added, events already there, lists replaced. |
| Run it | A new event log **adds** to what is there; an event sent before counts once. A new steps list, shift sheet, order list or product list **replaces** the earlier one. The answer is recalculated by itself. |
| Replace or add a file in an upload | Before the run the upload changes; after it, a **new version** takes the old one's place, and the old one stays in the history as *replaced*. |
| Fix a row the import could not read | IT or the planner types the right value (or leaves the row out) with a reason. The file stays as sent; the fix is stored next to the original, with who and when, and can be undone. Data quality lists every fix, also as a CSV for the ERP owner. |
| Delete an upload or import | Gone for good: its files, rows, fixes and numbers. One history line says who deleted it and when. The plant is rebuilt from the other uploads; a confirmation shows first what changes. IT can delete all data of a plant with the plant code typed. |
| Change Plant setup or the Capacity calendar | The answer is recalculated by itself. |

Every page shows a banner while the answer is recalculated, why, when the numbers are from, and how old the newest data is (older than 7 days: upload new events). By default IT and the planner upload, fix and delete; only IT deletes all data of a plant; the COO can change this on the Access page.

## 3. What the platform never does

- **No write-back.** It never changes data in your ERP or MES. Write-back is off and is not part of the pilot (shown as *Write-back to ERP: off* on Connections).
- **No personal data from the floor.** No employee names, badge numbers, who worked where or time per person. Station screens sign in as the machine, not as a person.
- **No guessed values.** Missing data is shown as missing, with its effect on confidence.
- **No files to the AI.** The mapping wizard (ADR-0011) can ask an AI (Claude API) to suggest column matches, code meanings and plain explanations of data problems. It sees only file and column names, rejected-row reasons and at most 5 anonymised example values per column; never whole files, personal columns, numbers, or plant, company or account names. Every AI suggestion is marked and someone in your team confirms it. The AI is not connected yet: until it is, the wizard works on rules alone and says "AI not connected".

## 4. Logins and access

| Login | For | How |
|---|---|---|
| Personal | Plant director, COO, planner, shift lead, IT | Company account via single sign-on (Keycloak, which brokers Microsoft Entra ID); during a pilot, email sign-in for accounts IT created |
| Station | The screen at a machine | Plant + machine + PIN (4–8 digits); five wrong PINs lock it until IT enables it again |

- **IT manages accounts** on the Users page: invite people, disable or enable them, add station logins. Disabling ends open sessions at once.
- **The COO decides access** on the Access page: which pages each role opens, whether money shows as € or as constraint hours, all plants or own plant, and who may take which decisions.
- Every account and access change is in the audit log (who, what, when).

Settings for single sign-on are in `docs/auth.md` (Keycloak realm, client id, issuer, keys URL).

## 5. Security facts

| Topic | Fact |
|---|---|
| Tenant isolation | Each customer is its own tenant; row-level security in the database applies to every table, and every request runs inside its tenant |
| Sessions | Opaque token in an httpOnly cookie; only its SHA-256 is stored; 12-hour sessions |
| Uploaded files | Stored per tenant and plant; personal columns are removed before any value is read |
| Region and encryption | EU region, encryption at rest and in transit: set by the deployment. The Connections page says *not verified* where it cannot confirm this, e.g. on a local test install |
| On-premise | The same container images run in a private cloud or on-premise for regulated plants |

## 6. Connecting the AI (optional)

The mapping wizard works without AI. With the AI connected it also suggests a field for columns the rules cannot place; each suggestion is marked *Suggested by AI* and stays a question until someone in your team says yes. To connect it:

1. Agree the data processing terms with us (the AI provider is Anthropic; only the content below is sent).
2. Set the key as the environment variable `CIP_ANTHROPIC_API_KEY` in the host's secret store (never in a file under version control). Optional: `CIP_AI_MODEL`, and the cost limits `CIP_AI_MAX_EUR_PER_IMPORT` (default €0.50) and `CIP_AI_MAX_EUR_PER_MONTH` (default €20).
3. Restart the API. The "AI not connected" note on the Import page disappears.

What is sent per unclear column: the file and column name, what the file holds (e.g. "event log"), the fields it may be, and at most 5 example values reduced to their shape (`JOB-24000` is sent as `AAA-99999`). Never whole files, real values, personal columns, numbers to calculate, or plant, company or account names. Above a cost limit, on an error or a timeout, the wizard falls back to rules for that upload and says so.
