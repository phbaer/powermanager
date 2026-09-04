---
type: Roadmap
title: PowerManager roadmap
description: Remaining implementation work and safety gates.
tags: [roadmap, testing, safety]
status: draft
---

# Next milestones

1. Expand Home Assistant tests beyond config-flow and diagnostics redaction to
   cover options, entity conversion, unavailable states, and reload.
2. Add retry/backoff handling to the normalized energy state. Stale/offline
   source classification and tariff-unit normalization are implemented.
3. Validate semantic mappings for the structurally decoded Speedwire `0x6069`
   records before converting them into grid/PV measurements.
4. Keep CI validation for `hassfest` and HACS healthy. Both are configured.
5. Add delayed charging policies using read-only telemetry.

# Explicitly gated work

Active battery control is not part of the current release. It requires verified
register semantics, explicit opt-in, command watchdogs, restore-normal behavior,
and hardware validation before implementation.

The documented register path is `40210=1079` plus cyclic `40149`/`40151`
setpoints. Before implementing it, read back the timeout/fallback configuration
(`41195`, `41193`, `44037`) and establish whether the Home Manager or
PowerManager owns active-power control. Competing writers are unsupported.
