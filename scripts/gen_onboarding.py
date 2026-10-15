# ruff: noqa: E501, RUF001  (user-facing prose: long sentences and en dashes are intended)
"""Generate the onboarding documents from their single sources.

    uv run python scripts/gen_onboarding.py           # write
    uv run python scripts/gen_onboarding.py --check   # fail when a file is stale

- docs/onboarding/data-checklist.{en,nl}.md and .html (printable; PDF via
  apps/web/scripts/onboarding-pdf.mjs) from docs/input-data.md (items, need, minimum set).
- The column appendix of docs/onboarding/erp-export-guide.md from the generic mapping.

Plain wording per item lives here, keyed by item number; a test fails when an item in
docs/input-data.md has no wording in both languages.
"""

import argparse
import html
import sys
from pathlib import Path

from cip_connectors.mapping import load_mapping
from constraint_engine.quality.checklist import MINIMUM_SET, Requirement, parse_requirements

ROOT = Path(__file__).resolve().parents[1]
INPUT = ROOT / "docs" / "input-data.md"
OUT = ROOT / "docs" / "onboarding"
MAPPING = ROOT / "packages" / "connectors" / "mappings" / "generic" / "mapping.yaml"
GUIDE = OUT / "erp-export-guide.md"
START, END = "<!-- generated:columns -->", "<!-- /generated:columns -->"

# number -> (English plain, Dutch plain): what it is, in words a plant director uses.
PLAIN: dict[int, tuple[str, str]] = {
    1: ("The plant: name and time zone.", "De fabriek: naam en tijdzone."),
    2: (
        "Your stations or departments and which machines stand there.",
        "Je stations of afdelingen en welke machines daar staan.",
    ),
    3: (
        "Your machines and work centres, with the codes your ERP uses.",
        "Je machines en werkplekken, met de codes uit je ERP.",
    ),
    4: (
        "Which operations each machine can do, with the ERP standard times.",
        "Welke bewerkingen elke machine kan doen, met de ERP-normtijden.",
    ),
    5: (
        "Products with sales price and truly variable cost (materials, bought parts, outsourcing; not labour).",
        "Producten met verkoopprijs en echt variabele kosten (materiaal, inkoopdelen, uitbesteding; geen arbeid).",
    ),
    6: (
        "Routings: the steps each product goes through, in order, per machine.",
        "Routings: de stappen die elk product doorloopt, op volgorde, per machine.",
    ),
    7: (
        "Setup families (e.g. colour groups) and changeover times between them.",
        "Omstelfamilies (bijv. kleurgroepen) en de omsteltijden ertussen.",
    ),
    8: (
        "Code lists: your machine codes, status codes, stop and scrap reasons.",
        "Codelijsten: je machinecodes, statuscodes, storings- en afkeurredenen.",
    ),
    9: (
        "Orders: the last 8–12 weeks and the open order book, with due dates.",
        "Orders: de laatste 8–12 weken en de open orderportefeuille, met leverdata.",
    ),
    10: ("A sales forecast beyond the open orders.", "Een verkoopprognose voorbij de open orders."),
    11: ("When material is ready per order.", "Wanneer het materiaal per order klaar is."),
    12: (
        "Start and finish bookings per order and machine, at least 8 weeks (MES or ERP hour bookings).",
        "Start- en gereedmeldingen per order en machine, minimaal 8 weken (MES of urenboekingen in het ERP).",
    ),
    13: ("Machine stops with their reason.", "Machinestilstanden met hun reden."),
    14: (
        "Scrap: how many and at which step it was found.",
        "Afkeur: hoeveel en bij welke stap het is gevonden.",
    ),
    15: (
        "Scans when work arrives at or leaves a station.",
        "Scans wanneer werk bij een station aankomt of vertrekt.",
    ),
    16: ("Shift times per machine.", "Diensttijden per machine."),
    17: (
        "Breaks and shift changes, and whether a machine keeps running during them.",
        "Pauzes en ploegwissels, en of een machine dan doordraait.",
    ),
    18: ("Planned maintenance per machine.", "Gepland onderhoud per machine."),
    19: ("Holidays and plant closures.", "Feestdagen en sluitingen."),
    20: (
        "Overtime worked per machine per week (never per person).",
        "Overuren per machine per week (nooit per persoon).",
    ),
    21: (
        "What extra capacity costs: overtime per hour, an extra shift, outsourcing.",
        "Wat extra capaciteit kost: overwerk per uur, een extra dienst, uitbesteding.",
    ),
    22: (
        "The baseline period and who in finance signs off the results.",
        "De basisperiode en wie bij financiën de resultaten aftekent.",
    ),
    23: ("The subscription price.", "De abonnementsprijs."),
    24: (
        "Email and role of the people who will use the platform.",
        "E-mail en rol van de mensen die het platform gaan gebruiken.",
    ),
    25: (
        "A PIN per station screen (the screen belongs to the machine, not a person).",
        "Een pincode per stationscherm (het scherm hoort bij de machine, niet bij een persoon).",
    ),
    26: (
        "Company sign-in details (Microsoft Entra ID via Keycloak).",
        "Gegevens voor inloggen met het bedrijfsaccount (Microsoft Entra ID via Keycloak).",
    ),
    27: (
        "A scheduled export: SFTP drop or read-only database view.",
        "Een geplande export: SFTP-map of alleen-lezen databaseview.",
    ),
}

TEXT = {
    "en": {
        "title": "Data checklist for a diagnostic",
        "intro": "What we need from your plant to find what limits your output and what it costs. "
        "Exports from your ERP and MES are enough; we map your column names, you do not have to change them.",
        "minimum": "Minimum to start: 5 exports and 1 sheet",
        "minimum_note": "Plant, stations and machines (items 1–3) we fill in together at the kick-off.",
        "should": "Also helpful: raises confidence, not required to start",
        "never": "Never needed: personal data",
        "never_text": "Employee names, badge numbers, who worked at which station, time per person, wages. "
        "If an export contains such columns, they are dropped while the file is read and never stored.",
        "appendix": "Appendix for IT: field names",
        "item": "Item",
        "data": "What",
        "fields": "Fields in the standard model",
        "history": "History",
        "weeks": "at least {n} weeks",
        "generated": "Generated from docs/input-data.md by scripts/gen_onboarding.py. Do not edit by hand.",
        "minimum_titles": {
            "orders": "Orders",
            "routings": "Routings and operations per machine",
            "products": "Products with price and truly variable cost",
            "events": "Start and finish bookings (8+ weeks)",
            "calendar": "Shifts, breaks and holidays (one sheet)",
        },
    },
    "nl": {
        "title": "Datachecklist voor een diagnose",
        "intro": "Wat we van je fabriek nodig hebben om te vinden wat je output beperkt en wat dat kost. "
        "Exports uit je ERP en MES zijn genoeg; wij koppelen je kolomnamen, je hoeft niets aan te passen.",
        "minimum": "Minimaal nodig om te starten: 5 exports en 1 sheet",
        "minimum_note": "Fabriek, stations en machines (items 1–3) vullen we samen in bij de kick-off.",
        "should": "Ook nuttig: verhoogt de betrouwbaarheid, niet nodig om te starten",
        "never": "Nooit nodig: persoonsgegevens",
        "never_text": "Namen van medewerkers, pasnummers, wie aan welk station werkte, tijd per persoon, lonen. "
        "Staan zulke kolommen in een export, dan vallen ze weg bij het inlezen en worden ze nooit opgeslagen.",
        "appendix": "Bijlage voor IT: veldnamen",
        "item": "Item",
        "data": "Wat",
        "fields": "Velden in het standaardmodel",
        "history": "Historie",
        "weeks": "minimaal {n} weken",
        "generated": "Gegenereerd uit docs/input-data.md door scripts/gen_onboarding.py. Niet met de hand wijzigen.",
        "minimum_titles": {
            "orders": "Orders",
            "routings": "Routings en bewerkingen per machine",
            "products": "Producten met prijs en echt variabele kosten",
            "events": "Start- en gereedmeldingen (8+ weken)",
            "calendar": "Diensten, pauzes en feestdagen (één sheet)",
        },
    },
}


def _plain(r: Requirement, lang: str) -> str:
    en, nl = PLAIN[r.number]
    return en if lang == "en" else nl


def checklist_md(reqs: list[Requirement], lang: str) -> str:
    t = TEXT[lang]
    by_number = {r.number: r for r in reqs}
    minimum_numbers = {n for _k, ns in MINIMUM_SET for n in ns}
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
        out.append(f"{i}. **{t['minimum_titles'][key]}** (#{', #'.join(map(str, numbers))})")
        for n in numbers:
            out.append(f"   - {_plain(by_number[n], lang)}")
    out += ["", t["minimum_note"], "", f"## {t['should']}", ""]
    for r in reqs:
        if r.level == "Should" and r.number not in minimum_numbers:
            out.append(f"- {_plain(r, lang)} (#{r.number})")
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


def checklist_html(markdown: str, lang: str) -> str:
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
        f'<!doctype html><html lang="{lang}"><head><meta charset="utf-8">'
        f"<title>{html.escape(TEXT[lang]['title'])}</title><style>{style}</style></head>"
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
    for lang in ("en", "nl"):
        md = checklist_md(reqs, lang)
        files[OUT / f"data-checklist.{lang}.md"] = md
        files[OUT / f"data-checklist.{lang}.html"] = checklist_html(md, lang)
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
