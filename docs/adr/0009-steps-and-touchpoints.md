# ADR-0009: Steps and touchpoints, not machines or products

- **Status:** Accepted (2026-10-23)
- **Date:** 2026-10-23
- **CLAUDE.md reference:** Core concepts, Task-level timing, Hard constraints (no individual employee monitoring, no invented data), Detection rules

## Context

Physical transformation is not an industry standard. In one plant a part is cut by a laser, welded by hand at a bench, checked by eye and packed by a team that also does finishing. The model so far assumed machines: step codes had to look like `PNT-01`, products and routings were required, capacity was counted in machines and every euro needed a price per product.

To find what limits output we do not need to know what the plant makes. We need to know the steps work passes through, when work passes them, and how much capacity each step has. Asking for less also makes a plant's first export smaller.

## Decision

**Four concepts carry the model:**

| Concept | Meaning | In code |
|---|---|---|
| Step | Any place where work happens: a machine, a handmade bench, a check, packing | `Resource` with a `kind`; the client sees "step" |
| Job | Whatever moves through the steps: an order, batch, ticket or work order | `Order` (`order_id`) |
| Touchpoint | A job passing a step: arrive, start, finish, leave (and setup, stop, scrap) | `OperationEvent` |
| Capacity | How many jobs a step can work on at once, per shift | `parallel_units`, positions per shift, or a team |

`Resource` stays the internal name to avoid a rewrite; every client-facing text says step.

**Step kinds:** `machine` and `manual` (shown as *handmade*). `station` and `work_centre` remain for grouping. Detection, facts and loss treat every kind the same way; only capacity and some explanations differ.

**Step codes are the plant's own short codes:** upper case letters, digits and hyphens, 2–32 characters (`WELD-BENCH`, `FIN`, `PNT-01`), the same rule as station codes. A code is never a person's name; the mapping's code table translates plant codes to these.

**Capacity of a handmade step is positions per shift:** the number of benches or places that are staffed, from the shift sheet. When the sheet gives no positions, the step's `parallel_units` is used and the data checklist says so. Positions are a count.

**Shared teams:** a team has a code, the steps it covers, and a size per shift (a count). When steps share a team, their combined busy positions cannot exceed the team's size, and the team itself can be the answer to "what limits output". The answer then names the team and its steps.

**Never per person.** No field anywhere for who did the work, who is in a team, names, badges, or time per person. Touchpoints are recorded by the step (scan at the bench, station screen signed in as the step, ERP booking per job), never by a person. This is a schema-level rule with a test.

**Products and routings are optional.** They add money, standard times and setup families, which raise confidence; they are not needed to find the bottleneck.

- **Path from history:** when a job has no routing or step number, its steps are ordered by its touchpoint times. Queues, waits and hand-offs use that order, and their confidence says the path came from history.
- **Money, in this order:**
  1. Product: sales price − truly variable cost per unit (`throughput_per_unit_v1`), when the job's product has both.
  2. Job: job value − material cost of the job (a new registered formula), when the order carries both.
  3. Neither: no euro figure; lost hours only, with a plain Missing reason. Never a guessed euro.

  A job with a product price uses the product; the rule is per job, and the Figure's inputs say which one was used.

**Noisy touchpoints from handmade work:** a start without a finish (a forgotten scan) is excluded from task times and busy time, counted per step, and lowers confidence by a registered rule. It is never closed with a guessed time.

**Smallest useful export:** a steps list, a shift sheet with positions (and team sizes), and one event log with job, step, time and what happened. Orders with value add euros; products and routings add confidence.

## Consequences

- Schema, database and API accept the wider step code rule; plants A, B and C keep their codes and answers.
- The data checklist, export guide, IT guide, demo script and app say the same thing about what to send.
- Synthetic plant D (machines, benches, a shared team, no product data, forgotten scans) is the known-answer test for this ADR.
- OEE parts that need a machine's standard time (performance) are Missing for handmade steps without standard times, with a plain reason; they are not zero.
- Pages keep their keys; labels read right for both kinds ("Steps", "handmade", "positions").
