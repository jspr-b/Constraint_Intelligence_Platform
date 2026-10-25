# Demo script: 10 minutes, three plants, three lessons

For a plant director, COO or planner in one meeting. Synthetic plants only; every number on
screen is calculated from the plant's own (made-up) export and opens its calculation.

## Before the meeting

```
bash scripts/build_images.sh && docker compose up -d --no-build && bash scripts/check_images.sh
uv run python scripts/demo_reset.py --loaded   # plants A, B and C, imported like a client would
```

- Sign in at http://localhost:53000/login with `it@demo.example`. Switch the role (top right) to
  **Plant director**: the preview banner says changes are switched off, which is what you want.
- For the live-upload version instead: `demo_reset.py --empty` (no plant yet) and have
  `data/synthetic/plant_a/erp_export/clean/csv/` ready to drag in (see "Live upload" below).
- Close other tabs; white theme for a projector, dark if the room asks for it.

## The three lessons

| Plant | Lesson | What they see |
|---|---|---|
| A | Here is your bottleneck and its cost | Paint line (PNT-01); about €169,041 lost in September 2026; 4 of 4 checks agree; setups and breaks are the biggest causes |
| B | Here we found none, and we say so | "No machine limits you: you could make more if you sold more." Busiest machine 42.1% |
| C | Your history says paint | Paint line again (about €149,005 in September 2026). The coming shift to welding is not shown yet (forecast comes later) |

## The 10 minutes

| Min | Click | Say |
|---|---|---|
| 0–1 | Overview, plant A | "Your systems show what happened. This shows what limits your output and what it costs. This is a made-up plant like yours: six machines, two shifts." |
| 1–2 | Read the answer sentence | "One machine limits what the whole plant ships: the paint line. Last full month that cost about €169,000 in throughput: sales price minus material, for every hour the paint line did not make good output." |
| 2–3 | Click **€169,041** | "Every number opens its calculation: the formula in words, what it is made from, the period, how sure. Nothing is typed in by hand." |
| 3–4 | Machines | "We never trust one method. Four independent checks: how busy, where work queues, who works longest without a pause, who never waits for work. All four point at paint." |
| 4–6 | Loss, per month, then a bar | "Where the hours went: setups and breaks. Breaks count because when paint stops, the plant stops. Click a bar: same calculation, that month." |
| 6–7 | Results report, Download PDF | "This is what you keep: the answer, the cost, the evidence, the data we used and what was missing, and where every number comes from." |
| 7–8 | Plant picker → B | "Same plant, less demand. No machine is full, so we say so: your limit is orders, not machines. We do not invent a bottleneck." |
| 8–9 | Plant picker → C | "History says paint again. In the order book the mix shifts to a weld-heavy product; showing that move ahead of time is the next step." |
| 9–10 | Data quality | "What your data covers and what is missing, with what to fix. Missing data is shown as missing, with its effect on how sure we are." |

## Live upload (when they want to see their kind of file go in)

`--empty`, then as IT: Getting started → 1. Add your plant (Plant setup) → 2. Upload your exports
(Import: drop the ten files of `plant_a/erp_export/clean/csv/`) → check the column preview, note
the **Medewerker** column marked *not imported: personal data* → run → 3. Data quality → 4. Overview
shows the answer when the numbers are calculated (about a minute).

## Likely questions, honest answers

| Question | Answer |
|---|---|
| What data do you need? | To start: your event log (start and finish per job and step), a steps list and a shift sheet. Jobs with value add euros; products and routings raise confidence (`docs/onboarding/data-checklist.md`). Files from your ERP, MES or spreadsheets; no connection needed to start |
| Do you track my people? | No. Columns with people in them are dropped on import and never stored. We measure machines and stations, never named employees |
| How sure are you? | Every answer has a confidence, from how many checks agree and how complete the data is. The Data quality page says what would make it surer |
| What if my data is messy? | Rows that do not fit are rejected with the reason and listed; gaps are shown, never filled in |
| Does it change my ERP? | No. It only reads exports |
| Where does my data go? | EU hosting, separate per customer, encrypted. On-premise is possible for defence and regulated plants |
| How long does a diagnostic take? | 4–8 weeks, starting from your first export; the first answer comes the day the export imports cleanly |
| What does it cost? | A paid diagnostic, credited against the subscription; the subscription is anchored to the gain we measure |

## Do not promise yet

- **Forecast** of where the bottleneck moves (plant C's shift to welding): later step.
- **Recommendations** with euro gain, cost and confidence: later step. Today's report states facts only.
- Live machine connections, scheduled exports, write-back to the ERP.
- A client's own mapping chosen on the Import page: real exports go through the intake first
  (`docs/onboarding/real-export-intake.md`).
- Anything about a real plant's numbers before its export has been through the data quality report.
