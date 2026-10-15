# ADR-0008: Plant flow views

- **Status:** Proposed
- **Date:** 2026-10-15
- **CLAUDE.md reference:** Flow view (input → transformation → output), Key screens (plant flow)

## Context

The user is still weighing how the plant flow should be shown: per station, per machine, per transition between steps, or per touchpoint of an order. Machines are multi-purpose, stations group machines, and products can visit a machine twice.

## Decision

- **Four views, one data source.** Machines, Stations, Transitions (handoffs and waits between steps) and Touchpoints (one order's journey) are all derived from the same station events.
- **Default view: Stations**, with the other three one click away.
- **Events must support all four:** start, end, setup, down and scrap per machine and operation, plus `move` and `scan` when an order arrives at or leaves a station. A station groups one or more machines; a machine belongs to exactly one station.
- **Operations are separate from machines:** a machine can run several operations, routings may revisit a machine, and operations can list alternative machines. Load and constraint detection add up per machine across all its operations.
- **Touchpoints are scans by a station, never by a person.**

## Consequences

- Choosing a different default later is a UI setting, not a data change.
- Plants without move/scan events still get Machines, Stations and Transitions (waits estimated from end and start times, with lower confidence); Touchpoints then show only start and end events.
