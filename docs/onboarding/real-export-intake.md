# Real-export intake

How we take in a factory's first real export: receive it, anonymise it, import it, read the data
quality report and fix the mapping. **Real data never enters this repository**: not the export,
not the anonymised export, not the key, not the client's mapping.

## 0. Before the export arrives

- Send the client `data-checklist.md` and `erp-export-guide.md`: which files, which columns, how.
- Agree the transfer: an encrypted share or SFTP the client controls. No e-mail attachments.
- Make one intake folder per client **outside the repository**, on an encrypted disk, e.g.
  `~/intake/<client>/` with `raw/`, `anon/`, `standard/` and `key.txt`. Delete it at the end of the
  diagnostic, as agreed in the data agreement.

## 1. Receive

- Save the files exactly as received in `raw/`. Do not open them in tools that sync to the cloud.
- Note what came in: file names, date, who sent it. No values.

## 2. Write the client's mapping

- Copy `packages/connectors/mappings/generic/mapping.yaml` to the intake folder as
  `~/intake/<client>/mapping.yaml` (not into the repository: its code tables hold the client's codes).
- Change separator, decimal sign, date format and time zone to match the files.
- For every standard field, set the client's column name (`from:`). Add their machine, station,
  status and calendar codes to the code tables. Add any column with people in it to
  `personal_columns` (on top of the built-in list: operator, employee, medewerker, badge, …).
- See `it-guide.md` §1 for how a mapping works.

## 3. Anonymise

```
uv run python scripts/anonymise_export.py ~/intake/<client>/raw ~/intake/<client>/anon \
  --key-file ~/intake/<client>/key.txt --mapping ~/intake/<client>/mapping.yaml \
  --standard ~/intake/<client>/standard
```

What it does:

| Column | What happens |
|---|---|
| Personal (by name or `personal_columns`) | Dropped, never read |
| Not read by the mapping | Dropped: nobody has checked what is in it |
| Codes and names: machines, stations, products, orders, product and colour families | Stable pseudonym, e.g. `RES-3FA2C19B7E`; machines become `MCH-01`, `MCH-02`… after import |
| Numbers, dates and times, statuses, reason codes, operation names | Kept as they are, so every number comes out the same |

- Files the mapping does not read are **not copied** (listed at the end of the run).
- Pseudonyms are a keyed hash: the same key gives the same pseudonyms on the next export, so
  weeks can be compared. Without the key a pseudonym cannot be traced back. The key file is
  made on the first run; it stays with the client's intake folder and is never shared or committed.
- The script refuses an output folder, key or standard folder inside the repository, and an
  output folder that is not empty.
- `anon/anonymise_report.json` lists per file the rows, the pseudonymised, kept and dropped
  columns, and how many values got a pseudonym. It holds no values: check it before going on.
- `anon/mapping.yaml` is the mapping for the anonymised files. It is the one used from here on.

## 4. Import and read the data quality report

`--standard` above already imported the anonymised export into the standard layout and printed
the rows, rejected rows and anything missing. Then:

```
uv run python -m constraint_engine.diagnose ~/intake/<client>/standard --section quality
```

It shows the score, rows and rejected rows per file, and the gaps with their effect on confidence
and how to fix them. These are the same numbers the Data quality page shows after an upload.

## 5. Fix the mapping and go again

| What the report says | Fix |
|---|---|
| Rows rejected: unknown code | Add the code to the code table in the client's mapping |
| Rows rejected: not a date/time or number | Fix `datetime_format` or `decimal` in the mapping |
| A standard field is missing | Set its `from:` column, or ask the client for the column (`erp-export-guide.md`) |
| A file is missing | Ask the client for it; the checklist says what it is used for |
| Gaps (no breakdowns, days without events) | Ask the client whether the machine was idle or the export missed it |

Run step 3 again into new, empty folders (`anon2/`, `standard2/`) with the same key, until no
rows are rejected and nothing required is missing.

## 6. What comes next, and what not yet

- Gaps that remain are not filled in: they are shown as gaps, with their impact on confidence.
- The Import page today reads the generic mapping. Choosing a client's own mapping on the Import
  page is a later step; until then a real export is checked here, offline, before the diagnostic
  starts in the platform.
- Synthetic plants A, B and C stay the only data in the repository and in the demo.
