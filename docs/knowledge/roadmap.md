---
type: Roadmap
title: PowerManager roadmap
description: Remaining implementation work and safety gates.
tags: [roadmap, testing, safety]
status: draft
---

# Required milestone order

The [production handover](production-handover.md) contains the authoritative
checklists and acceptance criteria after the 2026-09-05 review.

1. Reproducible monitor-only installation and dependency declarations.
2. Monitoring lifecycle tests, stable identity, soak validation, and release gates.
3. Consistent HA/CLI simulation with local time and hold semantics.
4. Independent fail-closed safety validation for every required input.
5. Bounded command sessions and recovery tested with fake transport.
6. Explicitly authorized, supervised physical commissioning and failure tests.
7. Opt-in manual control, followed by scheduled delayed charging.
8. Predictive planning, backtesting, and shadow-mode validation. The reusable
   predictive planner and deterministic replay primitive now exist; recorded
   day backtests and an HA shadow period remain open.

# Current boundary

Active control remains disabled. Backoff, forecast inputs, tariff normalization,
and conservative passive sender observation are implemented. The guarded command
adapter exists but must not be wired into production yet. Neither a successful
read-only preflight nor quiet multicast proves safe ownership.
