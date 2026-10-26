# Demo script: 12 minutes, four plants, four lessons (+3 on data over time)

For a plant director, COO or planner in one meeting. Synthetic plants only; every number on
screen is calculated from the plant's own (made-up) export and opens its calculation.

## Before the meeting

```
bash scripts/build_images.sh && docker compose up -d --no-build && bash scripts/check_images.sh
uv run python scripts/demo_reset.py --loaded   # plants A, B, C and D, imported like a client would
                                               # (plant A over time: see "Your data over time")
```

- Sign in at http://localhost:53000/login with `it@demo.example`. Switch the role (top right) to
  **Plant director**: the preview banner says changes are switched off, which is what you want.
- For the live-upload version instead: `demo_reset.py --empty` (no plant yet) and have
  `data/synthetic/plant_a/erp_export/clean/csv/` or plant D's minimum export ready to drag in
  (see "Live upload" below).
- Close other tabs; white theme for a projector, dark if the room asks for it.

## The four lessons

| Plant | Lesson | What they see |
|---|---|---|
| A | Here is your bottleneck and its cost | Paint line (PNT-01); about €169,041 lost in September 2026; 4 of 4 checks agree; setups and breaks are the biggest causes |
| B | Here we found none, and we say so | "No step limits you: you could make more if you sold more." Busiest step 42.1% |
| C | Your history says paint | Paint line again (about €149,005 in September 2026). The coming shift to welding is not shown yet (forecast comes later) |
| D | Your bottleneck is handmade work, and we found it without knowing your products | Finishing team (FINISH-TEAM), shared by finishing and packing; about €62,560 lost in September 2026, from job values; 4 of 4 checks agree; confidence medium because some finish scans were forgotten |

## The 12 minutes

| Min | Click | Say |
|---|---|---|
| 0–1 | Overview, plant A | "Your systems show what happened. This shows what limits your output and what it costs. This is a made-up plant like yours: six machines, two shifts." |
| 1–2 | Read the answer sentence | "One machine limits what the whole plant ships: the paint line. Last full month that cost about €169,000 in throughput: sales price minus material, for every hour the paint line did not make good output." |
| 2–3 | Click **€169,041** | "Every number opens its calculation: the formula in words, what it is made from, the period, how sure. Nothing is typed in by hand." |
| 3–4 | Steps | "We never trust one method. Four independent checks: how busy, where work queues, who works longest without a pause, who never waits for work. All four point at paint." |
| 4–6 | Loss, per month, then a bar | "Where the hours went: setups and breaks. Breaks count because when paint stops, the plant stops. Click a bar: same calculation, that month." |
| 6–7 | Results report, Download PDF | "This is what you keep: the answer, the cost, the evidence, the data we used and what was missing, and where every number comes from." |
| 7–8 | Plant picker → B | "Same plant, less demand. No machine is full, so we say so: your limit is orders, not machines. We do not invent a bottleneck." |
| 8–9 | Plant picker → C | "History says paint again. In the order book the mix shifts to a weld-heavy product; showing that move ahead of time is the next step." |
| 9–10 | Data quality | "What your data covers and what is missing, with what to fix. Missing data is shown as missing, with its effect on how sure we are." |
| 10–11 | Plant picker → D | "A workshop: a laser and a press, then welding, assembly, finishing and packing by hand, with one team shared by finishing and packing. We know no products and no routings, only when each job passed each step and how many people were on shift. The bottleneck is the finishing team: not one bench, the team." |
| 11–12 | Steps, then click **€62,560** | "Handmade steps count in positions: three benches, three times the time. Some finish scans were forgotten; we leave those jobs out and say so, which is why we are fairly sure, not sure. The euros come from each job's value minus its material." |

## Your data over time (3 more minutes, when they ask "and next month?")

`--loaded` builds plant A the way a client does over weeks (ADR-0010), and still ends at the same
answer (€169,041 in September 2026), because every step has a known answer:

1. Part 1: weeks 1–6 and every list.
2. Part 2 cut wrong (weeks 4–12), then its event file replaced by the right one (weeks 7–12): a new version; the old one stays in the history as *replaced*.
3. A full re-export with five typing errors; one row fixed in the app, with a reason.
4. Part 2 sent twice by mistake, then deleted.

| Min | Click | Say |
|---|---|---|
| 12–13 | Import, plant A: Import history | "Your files are the source. Every upload stays in the history: who sent it, which weeks, how many events were new. Events sent twice count once. A wrong file is replaced, not edited; a mistake is deleted for good, with one line that says who deleted it and when." |
| 13–14 | Results and data checklist → Rejected rows | "Five rows could not be read. One was fixed here, with a reason; the file stays as it was sent. Data quality lists every fix, with who and when, as a CSV for your ERP owner." |
| 14–15 | Capacity calendar (as planner) → add maintenance on Paint → Overview | "Change the calendar and the answer is recalculated by itself. The banner on every page says why and when, and how old your data is." |

Do the calendar step on a copy of the demo (`--loaded` again afterwards): it changes plant A's
answer.

## Live upload (when they want to see their kind of file go in)

`--empty`, then as IT: Getting started → 1. Add your plant (Plant setup) → 2. Upload your exports
(Import: drop the ten files of `plant_a/erp_export/clean/csv/`, or for plant D only `scans`, `workstations`, `shift_plan`, `teams` and `team_plan` from `plant_d/erp_export/clean/csv/`: the minimum) → check the column preview, note
the **Medewerker** column marked *not imported: personal data* → run → 3. Data quality → 4. Overview
shows the answer when the numbers are calculated (about a minute).

## Likely questions, honest answers

| Question | Answer |
|---|---|
| What data do you need? | To start: your event log (start and finish per job and step), a steps list and a shift sheet. Jobs with value add euros; products and routings raise confidence (`docs/onboarding/data-checklist.md`). Files from your ERP, MES or spreadsheets; no connection needed to start |
| Do you track my people? | No. Columns with people in them are dropped on import and never stored. We measure steps and stations, never named employees |
| How sure are you? | Every answer has a confidence, from how many checks agree and how complete the data is. The Data quality page says what would make it surer |
| What if my data is messy? | Rows that do not fit are rejected with the reason and listed; IT or the planner can fix a row in the app (the original stays, with who, when and why) or send a new file. Gaps are shown, never filled in |
| What if we send new data next week? | Upload it: events are added (sent twice counts once), lists replace the old ones, and the answer is recalculated by itself |
| Does it change my ERP? | No. It only reads exports |
| Where does my data go? | Today the demo runs on this laptop. Planned: hosting in the EU, separate per customer, encrypted; on-premise for defence and regulated plants |
| How long does a diagnostic take? | 4–8 weeks, starting from your first export; the first answer comes the day the export imports cleanly |
| What does it cost? | A paid diagnostic, credited against the subscription; the subscription is anchored to the gain we measure |

## Do not promise yet

- **Forecast** of where the bottleneck moves (plant C's shift to welding): later step.
- **Recommendations** with euro gain, cost and confidence: later step. Today's report states facts only.
- Live machine connections, scheduled exports, write-back to the ERP.
- A client's own mapping chosen on the Import page: real exports go through the intake first
  (`docs/onboarding/real-export-intake.md`).
- Anything about a real plant's numbers before its export has been through the data quality report.
