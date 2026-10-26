# ruff: noqa: E501, RUF001  (user-facing prose: long sentences and en dashes are intended)
"""Generate the onboarding documents from their single sources.

    uv run python scripts/gen_onboarding.py           # write
    uv run python scripts/gen_onboarding.py --check   # fail when a file is stale

- docs/onboarding/data-checklist.md and .html (printable; PDF via
  apps/web/scripts/onboarding-pdf.mjs) from docs/input-data.md (items, need, minimum set).
- The column appendix of docs/onboarding/erp-export-guide.md from the generic mapping.

Plain wording per item lives here, keyed by item number; a test fails when an item in
docs/input-data.md has no wording.
"""

import argparse
import html
import sys
from pathlib import Path

from cip_connectors.mapping import load_mapping
from constraint_engine.quality.checklist import (
    MINIMUM_SET,
    OPTIONAL_SET,
    Requirement,
    parse_requirements,
)

ROOT = Path(__file__).resolve().parents[1]
INPUT = ROOT / "docs" / "input-data.md"
OUT = ROOT / "docs" / "onboarding"
MAPPING = ROOT / "packages" / "connectors" / "mappings" / "generic" / "mapping.yaml"
GUIDE = OUT / "erp-export-guide.md"
START, END = "<!-- generated:columns -->", "<!-- /generated:columns -->"

# number -> plain wording: what it is, in words a plant director uses.
PLAIN: dict[int, str] = {
    1: "The plant: name and time zone.",
    2: "Your stations or departments and which steps are in them.",
    3: "Your steps: machines, work centres and handmade benches, with the codes you use.",
    4: "Which operations each step can do, with the ERP standard times.",
    5: "Products with sales price and truly variable cost (materials, bought parts, outsourcing; not labour).",
    6: "Routings: the steps each product goes through, in order.",
    7: "Setup families (e.g. colour groups) and changeover times between them.",
    8: "Code lists: your step codes, status codes, stop and scrap reasons.",
    9: "Jobs or orders: the last 8–12 weeks and the open order book, with due dates, and their value and material cost if you have them.",
    10: "A sales forecast beyond the open orders.",
    11: "When material is ready per order.",
    12: "The event log: start and finish per job and step, at least 8 weeks (MES, ERP hour bookings or scans at the bench).",
    13: "Stops with their reason.",
    14: "Scrap: how many and at which step it was found.",
    15: "Scans when work arrives at or leaves a station.",
    16: "Shift times per step, with the number of staffed positions at handmade steps (a count, never who).",
    17: "Breaks and shift changes, and whether a step keeps running during them.",
    18: "Planned maintenance per step.",
    19: "Holidays and plant closures.",
    20: "Overtime worked per step per week (never per person).",
    21: "What extra capacity costs: overtime per hour, an extra shift, outsourcing.",
    22: "The baseline period and who in finance signs off the results.",
    23: "The subscription price.",
    24: "Email and role of the people who will use the platform.",
    25: "A PIN per station screen (the screen belongs to the step, not a person).",
    26: "Company sign-in details (Microsoft Entra ID via Keycloak).",
    27: "A scheduled export: SFTP drop or read-only database view.",
    28: "Shared teams: which steps share people, and the team size per shift (a count, never who).",
}

TEXT: dict[str, str] = {
    "title": "Data checklist for a diagnostic",
    "intro": "What we need from your plant to find what limits your output and what it costs. Exports from your ERP, MES or spreadsheets are enough; we map your column names, you do not have to change them. Send new exports whenever you have them: new events are added (sent twice counts once), new lists replace the old ones, and the answer is recalculated by itself. A row the import cannot read can be fixed in the app; your file stays as you sent it.",
    "minimum": "Minimum to start: the event log, a steps list and a shift sheet",
    "minimum_note": "That is enough to find your bottleneck and its lost hours. Plant and stations (items 1–2) we fill in together at the kick-off.",
    "adds": "What each extra file adds",
    "should": "Also helpful: raises confidence, not required to start",
    "never": "Never needed: personal data",
    "never_text": "Employee names, badge numbers, who worked at which station, time per person, wages. If an export contains such columns, they are dropped while the file is read and never stored.",
    "appendix": "Appendix for IT: field names",
    "item": "Item",
    "data": "What",
    "fields": "Fields in the standard model",
    "history": "History",
    "weeks": "at least {n} weeks",
    "generated": "Generated from docs/input-data.md by scripts/gen_onboarding.py. Do not edit by hand.",
}


MINIMUM_TITLES: dict[str, str] = {
    "events": "Event log: start and finish per job and step (8+ weeks)",
    "steps": "Steps list: machines and handmade steps",
    "shifts": "Shift sheet: shifts with staffed positions, and team sizes when steps share people",
    "orders": "Jobs with value and material cost",
    "products": "Products with price and truly variable cost",
    "routings": "Routings and operations per step",
    "breaks": "Breaks and shift changes",
    "holidays": "Holidays and closures",
    "teams": "Shared teams and their sizes per shift",
}

ADDS: dict[str, str] = {
    "orders": "€ lost, late orders and on-time delivery",
    "products": "€ per product and the best product mix",
    "routings": "the planned path and standard times; higher confidence",
    "breaks": "the stagger-breaks action",
    "holidays": "the forecast",
    "teams": "the capacity of steps that share people; send it with the shift sheet when steps share people",
}
"""Same words as the app (apps/web/messages/en.json, import.adds)."""


def _plain(r: Requirement) -> str:
    return PLAIN[r.number]


def checklist_md(reqs: list[Requirement]) -> str:
    t = TEXT
    by_number = {r.number: r for r in reqs}
    minimum_numbers = {n for _k, ns in (*MINIMUM_SET, *OPTIONAL_SET) for n in ns}
    out = [
        f"# {t['title']}",
        "",
        f"_{t['generated']}_",
        "",
        t["intro"],
        "",
        f"## {t['minimum']}",
        "",
    ]
    for i, (key, numbers) in enumerate(MINIMUM_SET, 1):
        out.append(f"{i}. **{MINIMUM_TITLES[key]}** (#{', #'.join(map(str, numbers))})")
        for n in numbers:
            out.append(f"   - {_plain(by_number[n])}")
    out += ["", t["minimum_note"], "", f"## {t['adds']}", ""]
    for key, numbers in OPTIONAL_SET:
        out.append(f"- **{MINIMUM_TITLES[key]}** (#{', #'.join(map(str, numbers))}): {ADDS[key]}")
    out += ["", f"## {t['should']}", ""]
    for r in reqs:
        if r.level == "Should" and r.number not in minimum_numbers:
            out.append(f"- {_plain(r)} (#{r.number})")
    out += ["", f"## {t['never']}", "", t["never_text"], "", f"## {t['appendix']}", ""]
    out += [f"| {t['item']} | {t['data']} | {t['fields']} | {t['history']} |", "|---|---|---|---|"]
    for r in reqs:
        if r.level in ("Must", "Should"):
            weeks = t["weeks"].format(n=r.min_weeks) if r.min_weeks else ""
            out.append(f"| {r.number} | {r.data} | {r.key_fields} | {weeks} |")
    return "\n".join(out) + "\n"


def _code(text: str) -> str:
    """`field` -> <code>field</code> (text is already HTML-escaped)."""
    parts = text.split("`")
    return "".join(f"<code>{p}</code>" if i % 2 else p for i, p in enumerate(parts))


def checklist_html(markdown: str) -> str:
    """A small printable page (A4) from the generated markdown; no external assets."""
    body: list[str] = []
    in_table = False
    for line in markdown.splitlines():
        if line.startswith("|---"):
            continue
        if line.startswith("|"):
            cells = [_code(html.escape(c.strip())) for c in line.strip("|").split("|")]
            if not in_table:
                body.append("<table><tr>" + "".join(f"<th>{c}</th>" for c in cells) + "</tr>")
                in_table = True
            else:
                body.append("<tr>" + "".join(f"<td>{c}</td>" for c in cells) + "</tr>")
            continue
        if in_table:
            body.append("</table>")
            in_table = False
        text = html.escape(line).replace("**", "")
        if line.startswith("# "):
            body.append(f"<h1>{text[2:]}</h1>")
        elif line.startswith("## "):
            body.append(f"<h2>{text[3:]}</h2>")
        elif line.startswith("   - "):
            body.append(f"<p class='sub'>– {text[5:]}</p>")
        elif line.startswith("- "):
            body.append(f"<p class='item'>• {text[2:]}</p>")
        elif line[:3].rstrip(". ").isdigit():
            body.append(f"<p class='item'>{text}</p>")
        elif line.startswith("_"):
            body.append(f"<p class='note'>{text.strip('_')}</p>")
        elif line:
            body.append(f"<p>{text}</p>")
    if in_table:
        body.append("</table>")
    style = (
        "@page{size:A4;margin:18mm}body{font:11pt/1.45 Inter,system-ui,sans-serif;color:#0b0d0f}"
        "h1{font-size:20pt;margin:0 0 4pt}h2{font-size:12pt;margin:16pt 0 6pt;border-bottom:1px solid #cbd2d9}"
        ".note{color:#59616a;font-size:8pt}.sub{margin:0 0 2pt 14pt}.item{margin:4pt 0}"
        "table{border-collapse:collapse;width:100%;font-size:8pt}th,td{border-top:1px solid #e3e7eb;"
        "padding:3pt 4pt;text-align:left;vertical-align:top}th{color:#59616a}"
        "code{font:7.5pt 'JetBrains Mono',ui-monospace,monospace}"
    )
    return (
        f'<!doctype html><html lang="en"><head><meta charset="utf-8">'
        f"<title>{html.escape(TEXT['title'])}</title><style>{style}</style></head>"
        f"<body>{''.join(body)}</body></html>\n"
    )


def columns_md() -> str:
    mapping = load_mapping(MAPPING)
    out = [START, ""]
    for source in dict.fromkeys(t.source for t in mapping.tables):
        tables = [t for t in mapping.tables if t.source == source]
        out += [
            f"### `{source}.csv` (or `.xlsx`)",
            "",
            "| Column | Required | Type | Fills |",
            "|---|---|---|---|",
        ]
        seen: dict[str, tuple[bool, str, list[str]]] = {}
        for t in tables:
            for name, rule in t.fields.items():
                if rule.from_:
                    required, kind, fills = seen.get(rule.from_, (False, rule.type, []))
                    seen[rule.from_] = (
                        required or not rule.optional,
                        kind,
                        [*fills, f"{t.target}.{name}"],
                    )
        for column, (required, kind, fills) in seen.items():
            out.append(
                f"| {column} | {'yes' if required else 'no'} | {kind} | {', '.join(fills)} |"
            )
        out.append("")
    personal = ", ".join(mapping.personal_columns) or "none"
    out += [f"Columns dropped as personal data in this mapping: {personal}.", "", END]
    return "\n".join(out)


def outputs() -> dict[Path, str]:
    reqs = parse_requirements(INPUT.read_text())
    missing = [r.number for r in reqs if r.number not in PLAIN]
    if missing:
        raise SystemExit(f"no plain wording for input items {missing}: add them to PLAIN")
    files: dict[Path, str] = {}
    md = checklist_md(reqs)
    files[OUT / "data-checklist.md"] = md
    files[OUT / "data-checklist.html"] = checklist_html(md)
    guide = GUIDE.read_text()
    head, _, rest = guide.partition(START)
    _, _, tail = rest.partition(END)
    files[GUIDE] = head + columns_md() + tail
    return files


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    stale = []
    for path, content in outputs().items():
        if args.check:
            if not path.exists() or path.read_text() != content:
                stale.append(str(path.relative_to(ROOT)))
        else:
            path.write_text(content)
    if stale:
        print("stale: " + ", ".join(stale) + " (run uv run python scripts/gen_onboarding.py)")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
