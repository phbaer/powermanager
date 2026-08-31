---
type: Roadmap
title: PowerManager roadmap
description: Remaining implementation work and safety gates.
tags: [roadmap, testing, safety]
status: draft
---

# Next milestones

1. Add Home Assistant fixture tests for options, entity conversion, unavailable
   states, reload, and diagnostics redaction.
2. Add stale-data and retry/backoff handling to the normalized energy state.
3. Decode Speedwire `0x6069` records only from reproducible fixtures captured
   from supported devices.
4. Add CI validation for `hassfest` and HACS. (HACS plus manifest/translation
   structure checks are now present; full hassfest remains pending.)
5. Add delayed charging policies using read-only telemetry.

# Explicitly gated work

Active battery control is not part of the current release. It requires verified
register semantics, explicit opt-in, command watchdogs, restore-normal behavior,
and hardware validation before implementation.

The documented register path is `40210=1079` plus cyclic `40149`/`40151`
setpoints. Before implementing it, read back the timeout/fallback configuration
(`41195`, `41193`, `44037`) and establish whether the Home Manager or
PowerManager owns active-power control. Competing writers are unsupported.
