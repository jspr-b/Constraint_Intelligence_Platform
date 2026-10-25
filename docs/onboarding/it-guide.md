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

## 2. How data comes in

| Stage | How | Status |
|---|---|---|
| 1. File upload | CSV/Excel exports on the Import page; the import runs in a background worker, then the data checklist and data quality report are updated | Available |
| 2. Scheduled export | The same files dropped nightly or hourly on SFTP, or a read-only database view queried on a schedule | Planned for the pilot; shown as *not configured* on the Connections page |
| 3. Live connections | ERP APIs; machine signals via OPC UA or MQTT through an edge gateway | Later |

All stages end in the same standard data model, so pages and calculations do not change when a plant moves from uploads to scheduled exports.

For stage 2 we will ask for: an SFTP account with write access to one folder (or a database user with `SELECT` on one view per export), the schedule, and the network route (IP allow-list or VPN). The platform only reads.

## 3. What the platform never does

- **No write-back.** It never changes data in your ERP or MES. Write-back is off and is not part of the pilot (shown as *Write-back to ERP: off* on Connections).
- **No personal data from the floor.** No employee names, badge numbers, who worked where or time per person. Station screens sign in as the machine, not as a person.
- **No guessed values.** Missing data is shown as missing, with its effect on confidence.

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
