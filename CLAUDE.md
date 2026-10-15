# CLAUDE.md

Project context for building the Constraint Intelligence Platform. Read this before writing code.

## Product

A visual decision layer for manufacturing plants. It sits on top of existing ERP, MES and machine data and shows:

1. **Past** – where output was lost and what it cost in euros.
2. **Present** – which resource limits output now (the constraint), and its buffer status.
3. **Future** – projected load vs capacity per resource per week, and where the constraint will move.
4. **Actions** – ranked, TOC-based recommendations with the expected euro gain.

It replaces nothing. It reads from ERP/MES/machines and shows what those systems do not: the constraint, its cost, and what to do about it.

### Flow view: input → transformation → output

The whole plant is shown as one flow:

- **Input** – order intake, material availability, work released to the floor.
- **Transformation** – every production step: efficiency per machine (OEE: availability × performance × quality), queue in front of each step, state (running, idle, starved, blocked, down, setup), cycle time per task.
- **Output** – units shipped, on-time delivery, lead time, backlog.

Problems the flow view must surface directly:

| Problem | Where it shows |
| --- | --- |
| Late deliveries | Output: orders past due date, projected late orders |
| Too little output | Output vs demand; lost constraint hours |
| Too much overtime | Overtime hours per resource, overtime spent on non-constraints |
| Bottlenecks | Transformation: growing queues, constraint marker |
| Backlog filling up | Input vs output rate; queue growth per step |

Machine efficiency is an input to finding the constraint, not a goal on its own. The UI must make clear that efficiency at the constraint counts and efficiency elsewhere mostly does not.

### Task-level timing

Cycle time is measured per task and per station, so actual task times replace ERP standard times and feed the detection and forecast engines. Timing is never attributed to named individuals (see Hard constraints).

### Time horizons

| Horizon | Question it answers | Main visual |
| --- | --- | --- |
| Past | Where and when was output lost, and what did it cost? | Loss timeline per resource, € per month |
| Present | What limits output right now? | Live flow view, constraint marker, buffer board |
| Future | Where will the constraint be in the next 8–12 weeks? | Load heatmap (resources × weeks), constraint path |

Positioning: "Your systems show what happened. This shows what limits your output, what it costs, and where it moves next."

## Target customer

Mid-size manufacturers with a serious production line: multiple production steps, roughly 20+ machines, demand above capacity, and ERP or machine data available. First segment: high-mix, low-volume discrete manufacturing (metalworking, plastics, batch food, defence/aerospace suppliers).

## Users

| User | Needs | Main view |
| --- | --- | --- |
| Plant director | Lost euros, output, delivery reliability | Weekly value view |
| COO | Multi-plant comparison, investment cases | Monthly overview |
| Production planner | Constraint, buffer status, release advice | Daily planning view |
| Shift lead | Is the constraint running, starved or blocked | Floor screen |
| IT / ERP owner | Secure, low-effort data connections | Connection status |

## Domain model: Theory of Constraints (TOC)

All logic follows Goldratt's Five Focusing Steps:

1. **Identify** the constraint: the resource that limits system throughput.
2. **Exploit** it: no idle time, no defective input, best product mix, setups minimised.
3. **Subordinate** everything else: release work at the constraint's pace (rope), protect it with a buffer, stop overproduction at non-constraints.
4. **Elevate** it: overtime, extra shift, outsourcing, new capacity — only after Exploit and Subordinate.
5. **Repeat**: detect when the constraint moves.

Key consequences for the code:

- Efficiency at a non-constraint is not a goal. Only constraint time converts to throughput.
- Lost throughput (€) = constraint hours lost × throughput per constraint hour.
- Throughput = sales price − truly variable costs (throughput accounting), not cost-accounting margin.
- Buffer status: green (0–33% consumed), yellow (33–67%), red (67–100%+).

## Core concepts and entities

- `Plant`, `Resource` (machine, station, work centre), `Routing`, `Operation`, `Order`, `Product`.
- `OperationEvent`: timestamped start/end/setup/downtime per operation and resource.
- `ResourceState`: running, idle, starved, blocked, down, setup.
- `CapacityCalendar`: shifts, maintenance, holidays per resource.
- `ConstraintDetection`: resource, period, method results, agreement score, confidence.
- `LoadForecast`: resource × time bucket → projected load % of effective capacity (P50 and P90).
- `Recommendation`: catalogue action, trigger data, expected gain (€), cost (€), confidence, status (proposed, accepted, rejected, postponed, done), measured gain.

## Architecture

| Layer | Responsibility |
| --- | --- |
| Ingestion | Connectors: CSV/SQL exports first, ERP/MES APIs and machine gateways (OPC UA, MQTT) later |
| Data model | One standard schema for plants, resources, routings, orders and events |
| Event reconstruction | Raw logs → operation durations, queue times, resource states |
| Detection engine | Multiple bottleneck methods + cross-check → constraint with confidence |
| Forecast engine | Order book × routings × effective capacity → load per resource per week, with variability |
| Decision layer | Recommendation catalogue, trigger rules, euro quantification, ranking |
| Interface | Past / present / future views, buffer board, alerts |
| Write-back (later) | Push release and sequencing decisions into ERP/APS |

Build order: ingestion → data model → event reconstruction → detection → forecast → decision layer → interface → write-back.

## Detection rules

- Never rely on one method. Run several (utilisation, waiting time / queue length, active period method, starved/blocked analysis) and report agreement.
- Always output a confidence level and the data that supports the finding.
- Use effective capacity (actual measured rates), not nominal or ERP standard times.
- Explicitly detect the case where no internal resource is binding (market or material is the constraint) and say so.

## Recommendations and AI

- Recommendations come from a fixed catalogue, organised by Exploit / Subordinate / Elevate / Repeat, each with explicit trigger conditions in the data.
- Every number is calculated, never generated. The language model only ranks, explains and answers follow-up questions.
- Every recommendation shows: trigger data, calculation of the euro gain, cost, confidence.
- Humans decide. No automatic execution until accuracy is proven per plant.
- Log predicted vs actual gain for every action taken.
- Start with zero-cost Exploit and Subordinate actions; Elevate needs more evidence.

## Hard constraints

- **No individual employee monitoring.** Measure operations, tasks and stations, never named people (GDPR / AVG; Dutch Works Councils Act art. 27 requires works council consent for performance monitoring).
- **No invented data.** Missing data is shown as missing, with its impact on confidence.
- **Euros must be traceable.** Every euro figure links back to its inputs and formula.
- **Read-only by default.** The platform does not change ERP/MES data unless write-back is explicitly enabled.
- Plant data is confidential: tenant isolation per customer, encryption at rest and in transit.

## MVP scope

In:
- CSV/SQL import of orders, routings, operation events, capacity calendar.
- Constraint detection for the past period with confidence.
- Lost throughput in € per month.
- Load forecast heatmap (resources × next 8–12 weeks).
- Top recommendations from the Exploit and Subordinate catalogue.

Out (later):
- Live machine connectors, write-back to ERP, multi-plant benchmarks, automatic execution.

## Success metrics

- Constraint identified and confirmed by the planner in the diagnostic.
- At least one recommendation acted on within the pilot.
- Measured throughput gain ≥ 5× subscription cost.
- Planner uses the daily view at least 4 days a week.

## Conventions

- Units in every field name or column header (`load_pct`, `duration_min`, `gain_eur_month`).
- Times stored in UTC; displayed in plant local time.
- Currency stored as integer cents in EUR.
- Every calculation function is pure and unit-tested with small synthetic plants.
- Keep detection, forecast and decision logic in a standalone library, independent of the UI, so it can be open-sourced later.
- UI language: English and Dutch from the start; all labels in translation files.

## Recommendation catalogue (v1)

| Step | Action | Trigger in the data |
| --- | --- | --- |
| Exploit | Stagger breaks and shift changes on the constraint | Constraint idle during breaks |
| Exploit | Move quality inspection before the constraint | Scrap found after the constraint |
| Exploit | Reduce or resequence setups on the constraint | High setup share at the constraint |
| Exploit | Plan maintenance outside constraint production hours | Downtime during production on the constraint |
| Exploit | Prioritise orders with highest throughput per constraint minute | Mixed throughput per constraint minute |
| Subordinate | Release orders at the constraint's pace | WIP rising before the constraint |
| Subordinate | Stop overproduction at non-constraints | Non-constraints far ahead of the constraint |
| Subordinate | Size and protect the buffer before the constraint | Constraint starved |
| Subordinate | Route work to an alternative resource | Alternative routing with spare capacity |
| Elevate | Overtime or extra shift on the constraint only | Forecast overload; gain > cost |
| Elevate | Outsource constraint operations | Gain > outsourcing cost |
| Elevate | Business case for new capacity | Structural overload in the forecast |
| Repeat | Warn that the constraint will move to resource X in week Y | Forecast heatmap |

Example output:

> Constraint: Paint line. Lost throughput last month: €41,000.
> 1. Stagger lunch breaks on Paint: +6 h/week, ≈ €12,000/month, no cost. Confidence: high.
> 2. Release orders to Welding at Paint's pace: WIP −30%, lead time −4 days.
> 3. Saturday shift on Paint, weeks 47–49: ≈ €18,000 gain vs €7,500 overtime. Net €10,500.
> 4. Warning: constraint moves to Welding in week 50.

## Key screens

1. **Plant flow** – input → steps → output, live states, queue sizes, constraint highlighted.
2. **Loss view (past)** – lost constraint hours and € per week/month, causes (downtime, setup, starvation, blocking, scrap).
3. **Forecast heatmap (future)** – resources × weeks, load % of effective capacity, binding constraint per week outlined, what-if toggles (extra shift, alternative routing, order shifts).
4. **Buffer board** – orders in front of the constraint coloured green/yellow/red.
5. **Recommendations** – ranked list with € gain, cost, confidence, trigger data; accept/reject/postpone.
6. **Value report** – predicted vs measured gain, baseline comparison, exportable for finance.
7. **Floor screen** – one large signal per shift: constraint running, starved, blocked or down.
8. **Machine view** – OEE, states and cycle times per resource and task.

## Customer journey (summary)

Full version: `customer-journey.md`.

1. Trigger – late orders, flat output, overtime.
2. Discovery – content, consultants, trade fairs, referrals.
3. Evaluation – demo on sample data, data checklist.
4. Paid diagnostic (4–8 weeks) – own constraint, lost €, top 3 actions.
5. Onboarding – live within 30 days.
6. Daily use – planner, shift lead, plant director routines.
7. Proven value – predicted vs measured gain, signed off by finance.
8. Expansion – more lines, more plants, referrals, partners.

The product must support the diagnostic as a first-class workflow: import exports, produce a data quality report, run detection and forecast offline, and generate the results report.

## Business model

- Paid diagnostic (4–8 weeks), fee credited against the subscription.
- Subscription per plant, anchored to measured throughput gain; long term, value-based pricing.
- Partners: TOC/Lean consultants, ERP implementers and system integrators resell the diagnostic and implementation.

## Open-core strategy

| Open source | Paid platform |
| --- | --- |
| Standard data model for production flow | Hosted continuous detection and alerts |
| Connectors (ERP, MES, machine data) | Forecast heatmap and what-if scenarios |
| Constraint detection library with cross-check | Buffer management and release control |
| Public benchmark datasets | Recommendations with € quantification |
|  | Value reporting, multi-plant, security, support, ERP write-back |

Open source spreads through integrators, consultants, manufacturers' data teams and universities, not plant managers. The library must be packaged to run on common data platforms (Databricks, Snowflake, Microsoft Fabric).

## Competitive landscape

| Category | Examples | What they miss |
| --- | --- | --- |
| ERP capacity planning | SAP, Dynamics, Infor, Odoo, Exact | Planned standard times only; no constraint logic |
| APS | PlanetTogether, Siemens Opcenter APS, Asprova, DELMIA Ortems | Planner must interpret overloads; no measured-flow calibration, no € view |
| MES / OEE | MachineMetrics, Tulip, Ignition, Siemens Opcenter | Efficiency per machine, not which machine limits the plant |
| Process mining | Celonis, UiPath, Apromore | Detects waits from event logs; no TOC actions or forecast |
| Simulation | Plant Simulation, FlexSim, Simul8 | Design-time analysis, not continuous |
| TOC software | Synchrono, legacy DBR packages | Constraint must be designated manually; no auto re-detection |
| In-house systems | Tesla (Warp, MOS), Anduril (Arsenal OS, Forge MES) | Not for sale; built by large software teams |

Differentiator: measured-flow constraint detection + forecast of constraint movement + € quantification + TOC recommendations with measured outcomes, in one view.

## Moat (to build over time)

- Accumulated constraint and outcome data across plants (better detection and gain predictions).
- Connector library that lowers onboarding cost.
- Standard data model adopted by integrators.
- Switching costs once daily release decisions run through the platform.
- Documented € results per industry.

## Key risks

| Risk | Mitigation |
| --- | --- |
| Data quality too low for detection | Data quality report in week 1; target plants with machine data |
| Integration cost per ERP | One ERP/MES stack first; exports before live connectors |
| Long industrial sales cycles | Paid diagnostic as entry; partner channel |
| Seen as a feature of APS/MES | Own the decision and the € proof, not just the visual |
| Constraint is market or policy, not production | Detect and state it honestly |
| Floor resistance to monitoring | Measure tasks and stations, never individuals |
| Cloud refused (defence, regulated) | Architecture must allow on-premise deployment |

## Validation plan (before scaling the build)

1. One-page problem, buyer and € promise.
2. 20–30 interviews with plant directors, COOs and planners in one segment.
3. 3–5 manual paid diagnostics using scripts and spreadsheets.
4. Build only what was repeated across diagnostics.

The three questions that decide the product:
1. Which plant loses the most money because it does not know its current and future constraint?
2. What would that plant do differently on Monday morning if it knew?
3. Would it pay for a manual diagnostic before the software exists?

## Deployment

- Cloud by default, multi-tenant with strict tenant isolation.
- On-premise or private-cloud option for defence and regulated customers.
- Data residency in the EU.

## Tech stack

| Layer | Choice | Why |
| --- | --- | --- |
| Frontend | TypeScript, React, Next.js (App Router) | Mature ecosystem, server rendering for dashboards |
| UI components | Own component library in `packages/ui`, built on React Aria Components (headless) and styled with Tailwind CSS from the design tokens | Distinct industrial look, no template aesthetic; accessibility handled by React Aria. Do not use shadcn/ui |
| Charts / heatmaps | Apache ECharts (heatmaps, large series); D3 for custom flow view | Handles dense industrial data; full control where needed |
| Flow diagram | React Flow | Interactive input → steps → output graph |
| Tables | TanStack Table | Large sortable/filterable order and resource tables |
| Client data | TanStack Query | Caching, polling for live views |
| Backend API | Python 3.12, FastAPI, Pydantic v2 | Same language as the analytics engine; typed contracts |
| Analytics engine | Python library (`constraint_engine`): pandas/Polars, NumPy, SciPy | Detection, forecast, € quantification; open-sourceable |
| Simulation | SimPy (discrete-event) + NumPy Monte Carlo | P50/P90 load forecasts, what-if scenarios |
| Optimisation (later) | OR-Tools | Sequencing and release suggestions |
| Database | PostgreSQL 16 + TimescaleDB | Relational model + time-series events in one place |
| Analytics storage | Parquet files, DuckDB for local/diagnostic runs | Diagnostics run on a laptop without infrastructure |
| Background jobs | Celery or Dramatiq with Redis | Imports, detection runs, forecast recalculation |
| Machine data | OPC UA (asyncua), MQTT (paho-mqtt) via edge gateway | Standard industrial protocols |
| ERP connectors | Per-ERP adapters: CSV/SQL first, then APIs (Exact Online, SAP OData, Odoo XML-RPC) | Exports before live integration |
| LLM | Anthropic Claude API, explanation and ranking only | Never generates numbers or actions (see Recommendations) |
| Auth | Keycloak or Auth0 with OIDC; SSO via Azure AD for enterprise | Plants use Microsoft identities |
| Infrastructure | Docker, Kubernetes on an EU cloud region (Azure West Europe or AWS eu-central-1) | EU data residency; same images for on-premise |
| IaC | Terraform | Reproducible environments per customer |
| Observability | OpenTelemetry, Grafana, Sentry | Traces across ingestion → detection → UI |

## Dev stack

| Area | Tool |
| --- | --- |
| Monorepo | pnpm workspaces (frontend) + uv (Python) in one repo |
| Python lint/format | Ruff (lint + format), mypy (strict) |
| TS lint/format | ESLint, Prettier, TypeScript strict mode |
| Python tests | pytest, hypothesis (property tests for calculations) |
| Frontend tests | Vitest, Testing Library, Playwright (end-to-end) |
| API contract | OpenAPI generated from FastAPI → typed TS client via openapi-typescript |
| Migrations | Alembic |
| Local env | Docker Compose (Postgres/Timescale, Redis, API, web, worker) |
| CI/CD | GitHub Actions: lint, type-check, tests, build images, deploy |
| Pre-commit | pre-commit hooks for Ruff, Prettier, mypy, secret scanning |
| Dependencies | Renovate |
| Docs | MkDocs for the open-source engine; ADRs in `docs/adr/` |

## Repository structure

```
/
├── apps/
│   ├── web/                 # Next.js frontend
│   └── api/                 # FastAPI service
├── packages/
│   ├── constraint_engine/   # Python: detection, forecast, € quantification, catalogue (open-source candidate)
│   ├── connectors/          # Python: ERP/MES/machine adapters → standard schema
│   ├── schema/              # Standard production-flow data model (Pydantic + JSON Schema)
│   └── ui/                  # Shared React components and design tokens
├── workers/                 # Background jobs: import, detection, forecast
├── data/
│   └── synthetic/           # Synthetic plants for tests and demos (never real customer data)
├── infra/                   # Terraform, Kubernetes manifests, Docker files
├── docs/
│   └── adr/                 # Architecture decision records
├── CLAUDE.md
└── customer-journey.md
```

## Commands

```
docker compose up              # full local stack
uv run pytest                  # Python tests
uv run ruff check . && uv run mypy .
pnpm --filter web dev          # frontend dev server
pnpm --filter web test         # frontend unit tests
pnpm --filter web e2e          # Playwright
uv run python -m constraint_engine.diagnose data/synthetic/plant_a  # offline diagnostic run
```

## Code rules

- Calculation code lives only in `constraint_engine`; the API and UI never compute € or load figures themselves.
- Every calculation function is pure, typed, documented with its formula, and covered by tests on synthetic plants with known answers.
- Every API response that contains a number also contains its provenance (inputs, formula id, data period).
- No real customer data in the repo, tests, fixtures or logs.
- Small PRs, one concern each; conventional commits (`feat:`, `fix:`, `refactor:`).
- Architecture decisions recorded as ADRs before implementation.

## Styling and design system

### Direction: mission control for manufacturing

The visual style follows the aesthetic of modern defence and aerospace software: SpaceX, Anduril and Palantir-style mission-control interfaces. Dark, monochrome, technical, precise. The plant is presented like a system under live command: every number matters, nothing is decorative.

Take the aesthetic only. Never copy logos, wordmarks, proprietary fonts, icons or brand assets of these companies.

### Principles

- **Operator-grade.** The interface looks like a control system, not a consumer app. Dense, exact, calm.
- **Dark first.** Near-black canvas; light theme exists but is secondary.
- **Monochrome base, signal colour only.** Greys and white carry the UI; colour appears only for status and the constraint.
- **Data is the hero.** Large numerals, monospaced values, thin lines. No illustrations, no stock imagery, no rounded "friendly" shapes.
- **Grid and precision.** Hairline borders, strict alignment, visible structure, coordinates and timestamps everywhere.
- **Restraint.** One signal colour per screen dominates; everything else stays grey.

### Colour tokens (dark, default)

| Token | Value | Use |
| --- | --- | --- |
| `--bg` | #050607 | Canvas, near-black |
| `--surface` | #0B0D0F | Panels |
| `--surface-raised` | #121518 | Hover, selected rows, popovers |
| `--line` | #1E2328 | Hairline borders, grid |
| `--line-strong` | #2C333A | Dividers, active borders |
| `--text` | #E8ECEF | Primary text and numerals |
| `--text-muted` | #7C868F | Labels, secondary text |
| `--text-faint` | #4A535B | Axis ticks, disabled |
| `--accent` | #E8ECEF | Interactive elements are white, not blue |
| `--constraint` | #FF5A1F | The constraint only: marker, outline, label |
| `--status-ok` | #3DDC97 | Running, buffer green |
| `--status-warn` | #FFB020 | Buffer yellow, 85–100% load |
| `--status-bad` | #FF3B3B | Buffer red, >100% load, down |
| `--status-idle` | #4A535B | Idle, no data |

Light theme (secondary): `--bg` #F4F5F6, `--surface` #FFFFFF, `--line` #DADDE0, `--text` #0B0D0F, `--text-muted` #5B636B; status and constraint colours darkened one step for contrast.

Rules: the constraint colour is used for nothing else. Status colours always appear with a label or glyph, never colour alone. No gradients, glows or glassmorphism.

### Typography

| Role | Font | Style |
| --- | --- | --- |
| Display numerals and headings | D-DIN (open licence, SIL OFL) | Condensed, technical; large KPI numbers |
| UI text | Inter | 13–15 px, regular |
| Data, IDs, timestamps, coordinates | JetBrains Mono | Tabular, 12–13 px |
| Micro labels | Inter, uppercase, letter-spacing 0.08em | 10–11 px, `--text-muted` |

- Scale: 11 / 13 / 15 / 20 / 28 / 40 / 64 px. Floor screen main signal: 96–160 px.
- Uppercase is used only for micro labels, section tags and status codes (e.g. `CONSTRAINT`, `STARVED`, `WK 47`). Headings and sentences stay sentence case.
- Weights: 400 and 500; display numerals may use 700 in D-DIN. Nothing else.
- All numbers tabular (`font-variant-numeric: tabular-nums`).

### Layout and components

- 4 px base grid, 8 px rhythm. Square or near-square corners: radius 2 px on controls, 4 px on panels. No pill shapes except status chips.
- 1 px hairlines everywhere; no shadows. Focus ring: 1 px white outline offset 2 px.
- Panels have a header strip: uppercase micro label left, live timestamp or status right (e.g. `PAINT LINE · LIVE 14:32:07 UTC`).
- Multi-panel console layout for planners: left navigation rail (icons + labels), main canvas, right detail drawer.
- Components: KPI readout (micro label, large D-DIN numeral, delta, € impact), constraint marker, status chip, heatmap cell, buffer bar, recommendation card (action, € gain, cost, confidence, accept/reject/postpone), alert strip, timeline scrubber for past/present/future.
- Icons: thin-stroke line icons (1.5 px), e.g. Lucide or Tabler outline; never filled or colourful.
- Motion: minimal and functional, 120–200 ms, linear or ease-out. Live values update in place; no bouncing or decorative animation.

### Signature elements

- **Live state everywhere:** a pulsing dot and UTC timestamp on every live panel.
- **Constraint lock-on:** the constraint resource gets a bracketed orange outline (corner brackets, like a target lock) and a `CONSTRAINT` tag.
- **Time scrubber:** one horizontal timeline at the bottom of the plant view to move between past, now and forecast; the forecast region is hatched.
- **Coordinates and codes:** resources shown with short codes (`WLD-02`, `PNT-01`) in mono next to their names.
- **Command palette:** `Cmd/Ctrl + K` to jump to any resource, order or week.

### Data visualisation rules

- Charts on near-black with `--line` grid at low contrast; data in white or grey, signal colour only where it carries meaning.
- Heatmap: resources × weeks; cells neutral grey below 85%, `--status-warn` 85–100%, `--status-bad` above 100%; binding constraint per week marked with the constraint bracket.
- Loss view: thin bars in € per week, stacked by cause in grey tones; the largest cause highlighted.
- Forecasts: P50 as a solid line, P90 as a faint band; forecast region hatched.
- Every chart title states the finding ("PNT-01 becomes the constraint in week 47"), with an uppercase micro label above it.
- Units in every axis title and column header (€, %, h, min). No 3D, no pie charts, no gradients.

### Tone of UI copy

- Terse and operational: "PNT-01 idle 42 min during lunch", "Buffer red: 3 orders at risk", "Constraint shifts to WLD-02 in wk 50".
- € and hours before percentages.
- English and Dutch, same tone in both.

### Accessibility

- WCAG 2.2 AA contrast in both themes; check muted text against `--bg` and `--surface`.
- Full keyboard navigation for all planner views; command palette as keyboard entry point.
- Status never conveyed by colour alone.
- Respect `prefers-reduced-motion`: disable pulsing and transitions.
