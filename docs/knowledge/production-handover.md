---
type: Handover
title: Production readiness handover
description: Ordered implementation tasks and acceptance gates after the production review.
tags: [handover, roadmap, testing, safety]
status: draft
---

# Production readiness handover — 2026-09-05

PowerManager remains a monitor-only prototype. Physical commissioning is not the
only blocker: installation, safety validation, command recovery, and simulation
consistency need work. This checklist supersedes older remaining-work lists in
the original handover. It does not authorize inverter writes or parameter changes.

## Evidence and completed follow-up

The review inspected the core, HA integration, tests, workflows, and documentation.
The initial baseline passed 56 tests and Ruff; the detection update passes 61 tests
and Ruff. No HACS installation, full hassfest run, or hardware validation was
performed during this work. No device was contacted.

The original handover records read-only observations from 2026-09-04: SI4.4M-12,
external-setpoint mode, apply-fallback behavior, a 300-second timeout, and 6000 W
fallback maximum power. These are historical observations, not proof of safe
recovery after controller failure. Re-read settings before commissioning.

Completed passive detection improvements:

- Modbus polls preserve observed sources and possible-controller warnings.
- Every observation update immediately recomputes ownership eligibility.
- Health distinguishes offline, unknown, online, and stale. Listening without
  traffic is unknown. Traffic expires after 120 seconds, checked during five-second
  receive timeouts. Future timestamps are stale.
- Eligibility requires explicit confirmation, a running listener, fresh traffic,
  and no observed non-inverter sender. It cannot authorize hardware control.
- Listener/DNS socket failures clear eligibility and retry after 30 seconds.
  Recovery requires new traffic before reporting online.
- IPv4 hostname resolution excludes the inverter's resolved addresses.
- Possible competitors remain latched across socket retries for the monitor's
  lifetime. Reload resets observation history to unknown.
- Packet updates notify entities without resetting Modbus polling or masking
  a failed battery read.
- The warning is unknown during silence/failure/staleness unless a competitor
  was already detected, in which case it stays on. Its observation_state attribute
  and diagnostics expose health separately.
- Diagnostics report sender count instead of exposing sender IP addresses.

This is conservative source detection, not positive Home Manager identification
or proof of exclusive ownership. Other SMA devices can trigger it. The listener
checks the common SMA prefix, not authenticated identity. Relayed packets identify
the relay as sender. Silence must never authorize control.

## Required execution order

Complete each acceptance gate before advancing to its dependent stage.

### 1. Make monitor-only installation reproducible

- [ ] Declare the supported pymodbus requirement in the HA manifest. The development
  extra currently hides its absence from the manifest.
- [ ] Review optional Recorder dependency ordering and behavior when absent;
  optional forecasting must not break battery monitoring.
- [ ] Install the actual HACS release archive into a clean HA environment without
  manually installing dependencies.
- [ ] Validate the declared minimum and a current supported HA version; correct
  compatibility metadata if necessary.
- [ ] Run HACS validation and full hassfest and record actual results.

Acceptance: a fresh installation exposes correct read-only entities and survives
restart without relying on packages installed by the development environment.

### 2. Finish monitoring reliability and release gates

- [ ] Test full setup/entity creation, connection failure/recovery, options reload,
  unload, and setup-failure cleanup with HA fixtures.
- [ ] Extend observation tests to timed silence, DNS failure/recovery, and sustained
  traffic alongside scheduled Modbus updates.
- [ ] Validate multicast reception/recovery on the deployment network; document
  interface/relay limitations and identify the Home Manager generation if required.
- [x] Read stable serial and firmware identity from the documented SI registers
  `30057`, `30061`, and `30063`; decode SMA's packed firmware format. Host-based
  identity migration and physical firmware support validation remain outstanding.
- [ ] Establish firmware support and unsupported/unavailable-state reporting.
- [ ] Require tests, Ruff, hassfest, and HACS validation before publishing.
  Currently the release job depends only on its HACS validation job.
- [ ] Record a monitoring soak test's duration, gaps, and recovery after network
  interruption, HA restart, and listener failure.

Acceptance: monitoring recovers predictably and release publication cannot bypass
required checks.

### 3. Unify simulation semantics

- [x] Route HA simulation through the same runtime/safety decisions as CLI
  simulation. The coordinator now uses `ControlRuntime` with the simulation
  actuator; it never calls the physical write adapter.
- [x] Use an explicit local timezone for rule windows. HA resolves its configured
  timezone and the core accepts it independently. Test Berlin summer/winter time,
  DST, and overnight windows with recorded fixtures.
- [ ] Define hold/cooldown and preemption for changed/missing inputs, higher-priority
  rules, disablement, and no-match decisions.
- [ ] Define recoverable watchdog expiry and explicit restoration decisions.
- [x] Expose rule, target, acceptance/rejection reason, held state, watchdog
  restoration, and simulation decision through HA sensors and diagnostics.

Acceptance: replayed timestamped inputs yield matching HA and CLI decisions,
including example-rule holds and local time windows.

### 4. Harden independent safety validation

- [x] Reject missing/nonfinite required SoC and targets, invalid safety bounds,
  future timestamps, stale individual sources, and unsupported operating states.
- [x] Validate required telemetry at command time; a fresh aggregate timestamp
  cannot hide stale battery/grid/price/forecast inputs.
- [x] Enforce maximum charging SoC, reserve plus dynamic discharge floor, and
  reported battery charge limits. Device-specific power-limit mapping and
  operating-state coverage still need validation on the target hardware.
- [x] Test directly constructed models independently of HA providers/YAML parsing,
  including held intents after telemetry changes.

Acceptance: invalid or unknown required safety inputs reject actions with a reason
and no transport writes.

### 5. Build a recoverable command-session lifecycle using fake transport

- [ ] Require preflight, explicit enablement, ownership, bounded power/duration,
  and current safety approval at the write boundary.
- [ ] Revalidate telemetry, ownership, and intent during heartbeats; currently the
  session repeatedly sends a fixed target without these checks.
- [ ] Prevent overlapping sessions and define override/emergency-stop precedence.
  Revoked control permission must not prevent necessary recovery.
- [ ] Separate transport timeouts from normal session expiry; run_for currently
  catches both as TimeoutError. Eliminate unbounded production sessions.
- [ ] Capture approved baseline settings and verify restoration. Current restore
  writes a hardcoded mode and stops if its first write fails.
- [ ] Test partial writes, failed readback, cancellation, disconnection, restoration
  failure, clock changes, and process restart policy.
- [ ] Separate raw write capability from the nominal read-only transport and
  correct its misleading read-only documentation.
- [ ] Add bounded, sanitized command/recovery events for diagnostics.

Acceptance: fault injection demonstrates bounded sessions and explicit recovery
failure reporting. Production entry points remain disabled.

### 6. Complete supervised physical commissioning

- [ ] Confirm supported single-cluster topology, firmware, active-power owner,
  and physical emergency-stop/rollback procedure with the operator.
- [ ] Verify sign, scaling, limits, persistence, activation, and fallback against
  applicable SMA documentation and observed behavior.
- [ ] Record baseline settings and explicitly decide whether the observed
  300-second timeout and fallback power are acceptable.
- [ ] Obtain authorization for each specific live operation or parameter change
  after documenting its command and rollback procedure.
- [ ] Test a small bounded setpoint/restoration, heartbeat loss, TCP disconnect,
  process termination, HA/controller restart, and inverter restart under an
  approved supervised plan.
- [ ] Record dated observations separately from documented expectations.

Acceptance: controller loss demonstrably returns the system to approved safe
behavior without relying on the failed process. Stop for operator feedback when
topology, ownership, firmware behavior, or emergency stop is unknown. Never race,
spoof, suppress, or firewall Home Manager traffic as a control strategy.

### 7. Expose opt-in manual control, then scheduled charging

- [ ] Connect the reviewed runtime only after stages 1–6 pass.
- [ ] Add explicit HA enablement, modes, power/reserve limits, ownership
  confirmation, restore-normal action, and emergency stop.
- [ ] Default fresh installs and uncertain restart states to monitor-only; prevent
  old commands resuming automatically. Test disable, reload, and unload.
- [ ] Distinguish normal operation, zero active-power target, and charge inhibition.
  target_power_w: 0 does not establish “prevent charging while allowing discharge.”
  Keep the example intent simulation-only until verified.
- [ ] Validate supervised manual operation before scheduled delayed charging.

Acceptance: manual actions are bounded/recoverable and schedules cannot bypass
their safety boundaries.

### 8. Implement and validate predictive charging

- [ ] Model usable capacity, end-of-day SoC target, charging limits, export
  constraints, forecast uncertainty, and remaining time.
- [ ] Plan headroom across the day instead of only fixed surplus thresholds;
  existing forecast inputs and rules are not a predictive planner.
- [ ] Backtest recorded days with poor/missing forecasts, tariff changes, and
  seasonal/DST cases; compare reserve and end-of-day outcomes.
- [ ] Complete a documented shadow-mode period before supervised activation.
- [ ] Verify Speedwire measurement mappings if direct meter telemetry is needed;
  existing HA grid entities can remain an alternative.

Acceptance: documented energy/reserve objectives and predictable degradation on
forecast failure, with the independent safety layer retaining final authority.

## Working instructions

Use uv sync --extra sma --extra dev, uv run pytest, and uv run ruff check .
Commit coherent batches without discarding user work. Update README, this handover,
roadmap, and control plan when status changes. Preserve monitor-only release
metadata until software and physical commissioning gates pass.
