# Datachecklist voor een diagnose

_Gegenereerd uit docs/input-data.md door scripts/gen_onboarding.py. Niet met de hand wijzigen._

Wat we van je fabriek nodig hebben om te vinden wat je output beperkt en wat dat kost. Exports uit je ERP en MES zijn genoeg; wij koppelen je kolomnamen, je hoeft niets aan te passen.

## Minimaal nodig om te starten: 5 exports en 1 sheet

1. **Orders** (#9)
   - Orders: de laatste 8–12 weken en de open orderportefeuille, met leverdata.
2. **Routings en bewerkingen per machine** (#4, #6)
   - Welke bewerkingen elke machine kan doen, met de ERP-normtijden.
   - Routings: de stappen die elk product doorloopt, op volgorde, per machine.
3. **Producten met prijs en echt variabele kosten** (#5)
   - Producten met verkoopprijs en echt variabele kosten (materiaal, inkoopdelen, uitbesteding; geen arbeid).
4. **Start- en gereedmeldingen (8+ weken)** (#12)
   - Start- en gereedmeldingen per order en machine, minimaal 8 weken (MES of urenboekingen in het ERP).
5. **Diensten, pauzes en feestdagen (één sheet)** (#16, #17, #19)
   - Diensttijden per machine.
   - Pauzes en ploegwissels, en of een machine dan doordraait.
   - Feestdagen en sluitingen.

Fabriek, stations en machines (items 1–3) vullen we samen in bij de kick-off.

## Ook nuttig: verhoogt de betrouwbaarheid, niet nodig om te starten

- Omstelfamilies (bijv. kleurgroepen) en de omsteltijden ertussen. (#7)
- Wanneer het materiaal per order klaar is. (#11)
- Machinestilstanden met hun reden. (#13)
- Afkeur: hoeveel en bij welke stap het is gevonden. (#14)
- Gepland onderhoud per machine. (#18)
- Overuren per machine per week (nooit per persoon). (#20)
- Wat extra capaciteit kost: overwerk per uur, een extra dienst, uitbesteding. (#21)
- De basisperiode en wie bij financiën de resultaten aftekent. (#22)
- Een pincode per stationscherm (het scherm hoort bij de machine, niet bij een persoon). (#25)
- Een geplande export: SFTP-map of alleen-lezen databaseview. (#27)

## Nooit nodig: persoonsgegevens

Namen van medewerkers, pasnummers, wie aan welk station werkte, tijd per persoon, lonen. Staan zulke kolommen in een export, dan vallen ze weg bij het inlezen en worden ze nooit opgeslagen.

## Bijlage voor IT: veldnamen

| Item | Wat | Velden in het standaardmodel | Historie |
|---|---|---|---|
| 1 | Plant | `plant_code`, `name`, `timezone_iana` |  |
| 2 | Stations | `station_code`, `name`, machines in it |  |
| 3 | Machines | `resource_code` (e.g. `PNT-01`), `name`, `station_code`, `parallel_units` |  |
| 4 | Operations per machine | `operation`, `resource_code`, ERP `standard_run_min_per_unit` and `standard_setup_min` (reference only), `alternative_resource_codes` |  |
| 5 | Products | `sku`, `family`, `sales_price_eur_cents`, `truly_variable_cost_eur_cents` (materials, bought parts, outsourcing; not labour) |  |
| 6 | Routings | `sku` → `operation_seq`, `operation`, `resource_code`, alternatives; second visits allowed |  |
| 7 | Setup families | colour/material family per product, changeover time between families |  |
| 8 | Code tables | ERP machine codes → `resource_code`; status → event type; downtime and scrap reason codes |  |
| 9 | Orders: history + open order book | `order_id`, `sku`, `quantity_units`, `due_at`, `released_at`, `shipped_at`, `status` | minimaal 8 weken |
| 11 | Material availability | `order_id`, `material_ready_at` |  |
| 12 | Operation events | `event_id`, `at`, `resource_code`, `order_id`, `operation_seq`, `event_type` (start, end, setup_start/end, down_start/end), `quantity_units` | minimaal 8 weken |
| 13 | Downtime reasons | `down_reason_code` per stop |  |
| 14 | Scrap | `scrap_units`, operation where found |  |
| 16 | Shifts | start/end per machine per weekday |  |
| 17 | Breaks and shift changes | start/end per machine, whether covered |  |
| 18 | Maintenance windows | planned start/end per machine |  |
| 19 | Holidays and closures | dates |  |
| 20 | Overtime worked | `overtime_h` per machine per week |  |
| 21 | Cost of extra capacity | overtime `eur_cents_per_h`, extra shift cost, outsourcing price per operation |  |
| 22 | Baseline agreement | baseline period, finance contact for sign-off |  |
| 24 | Personal accounts | `email`, `role`, `plant_code` |  |
| 25 | Station logins | station, PIN |  |
| 27 | Export connection | SFTP or read-only database view, schedule |  |
