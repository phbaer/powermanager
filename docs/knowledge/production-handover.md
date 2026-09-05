---
type: Handover
title: Production readiness handover
description: Ordered implementation tasks and acceptance gates after the production review.
tags: [handover, roadmap, testing, safety]
status: draft
---

# Production readiness handover — 2026-09-05

PowerManager remains monitor-only by default. The HA command path is now present
behind explicit commissioning gates, but no live operation is authorized by this
document. Physical commissioning, supervised failure testing, and operator
authorization remain required. This checklist supersedes older remaining-work lists in
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

Read-only deployment validation on 2026-09-05 reached the Home Assistant instance
at `10.0.1.6`. It runs Home Assistant Core `2026.9.0` on HA OS `18.2`; `ha core
check` completed successfully and no matching PowerManager, Sunny Island, or
Speedwire errors appeared in the recent core log. The configured PowerManager entry
is enabled and has 19 registered entities. The installed integration is an older
copy than this checkout: its manifest has no declared Home Assistant minimum or
`pymodbus` requirement, and its file hashes differ from the current source. The
deployed tree does not contain the current predictive/control modules. No files,
configuration, or inverter settings were changed during this check. Installing a
clean HACS release archive and repeating the clean-install/current-version
validation remains an open gate below. The supervised deployment gate was later
completed using the reviewed archive: the old directory was backed up at
`/config/.powermanager-backups/powermanager-20260905.tgz`, HA was restarted, and
the entry loaded 31 entities with no PowerManager-specific startup or polling
errors in the post-restart log.

After the Home Manager was disconnected, a 30-second read-only capture on the
LAN-side host interface `10.0.1.254` received no valid frames for
`239.12.255.254:9522`. This is a negative observation for that interface and
interval, not proof that every broadcaster is absent. The HA warning entity now
keeps observed and external sender addresses in its attributes so a later frame
identifies the source directly.

Completed passive detection improvements:

- Modbus polls preserve observed sources and possible-controller warnings.
- Every observation update immediately recomputes ownership eligibility.
- Health distinguishes offline, unknown, online, and stale. Listening without
  traffic is unknown. Traffic expires after 120 seconds, checked during five-second
  receive timeouts. Future timestamps are stale.
- Eligibility requires explicit confirmation, a running listener, fresh traffic,
  and no observed unknown sender. A manually entered list can classify verified
  reporting-only senders (such as a PV inverter) for telemetry; it does not
  identify a controller or suppress the warning.
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
- The Speedwire warning entity exposes observed sender IPv4 addresses and the
  subset classified as external; diagnostics expose the external subset so local
  debugging can identify a broadcaster. The configured inverter host remains
  redacted from diagnostics.
- An external sender address is not a device-role determination. A future verified
  source inventory may classify a device as telemetry-only, control-capable, or
  unknown and expose its normalized measurements as HA sensors. Unknown and
  control-capable sources remain safety blockers; observed control traffic is an
  immediate inhibit signal, while its absence never authorizes control.

This is conservative source detection, not positive Home Manager identification
or proof of exclusive ownership. Other SMA devices can trigger it. The listener
checks the common SMA prefix, not authenticated identity. Relayed packets identify
the relay as sender. Silence must never authorize control.

## Operator topology confirmation (2026-09-05)

The operator confirms that the installation is a single-phase system. The SMA
Sunny Home Manager is the only intended active-power controller and is currently
back in service; PowerManager must not compete with it. The Sunny Island's
existing external-setpoint, fallback, and timeout configuration must remain
unchanged. There is no dedicated emergency-stop device; the available physical
isolation is the device's LS circuit breaker and RCD. These provide a coarse
operator isolation procedure, not a supervised inverter stop or proof that the
installation is safe to switch under load.

## Required execution order

Complete each acceptance gate before advancing to its dependent stage.

### 1. Make monitor-only installation reproducible

- [x] Declare the supported `pymodbus` requirement in the HA manifest. The
  development extra and the HACS archive now declare the same pinned version.
- [x] Smoke-check a locally built archive for the required manifest, strings,
  translation, and runtime dependency files; this does not replace a real HACS
  installation.
- [x] Review optional Recorder behavior when absent; forecast history failures are
  caught and withheld so optional forecasting cannot break battery monitoring.
- [ ] Install the actual HACS release archive into a clean HA environment without
  manually installing dependencies.
- [x] Replace the stale deployment on the supervised HA instance with the reviewed
  archive using a restorable backup, restart HA, and repeat read-only entity and
  recovery checks; keep active control disabled. The 2026-09-05 deployment loaded
  31 entities and passed `ha core check`.
- [ ] Validate the declared minimum and a current supported HA version; correct
  compatibility metadata if necessary.
- [x] Keep the manifest and HACS metadata aligned on the declared minimum
  Home Assistant version (`2025.1.0`); validation against an actual current HA
  release remains open.
- [ ] Run HACS validation and full hassfest and record actual results.

Acceptance: a fresh installation exposes correct read-only entities and survives
restart without relying on packages installed by the development environment.

### 2. Finish monitoring reliability and release gates

- [x] Test full read-only setup/entity creation and connection failure/recovery
  with HA fixtures.
- [x] Exercise options reload through HA's config-entry lifecycle; unload and
  setup-failure cleanup are covered separately below.
- [x] Entry lifecycle cleanup is covered: successful forwarding is limited to
  monitor platforms, a failed forward stops the passive listener, and normal
  unload removes the coordinator before HA retries or releases the entry.
- [x] Coordinator read failures trigger backoff and a subsequent successful poll
  recovers through the same read-only path; full HA connection/entity lifecycle
  coverage remains open.
- [x] Options-flow validation checks independent telemetry, tariff, and rule
  sources together, including conflicts when valid YAML rules are supplied.
- [x] Observation tests cover timed silence plus DNS and socket failure/recovery
  alongside scheduled Modbus updates.
- [ ] Validate sustained multicast traffic and gaps on the deployment network
  alongside scheduled Modbus updates.
- [ ] Validate multicast reception/recovery on the deployment network; document
  interface/relay limitations and identify the Home Manager generation if required.
- [x] Add optional HA entity-backed multi-inverter ingestion. Each configured
  source declares a PV, battery, or hybrid role. PV generation and optional
  remaining-PV forecasts are normalized per source; signed battery power is
  available only for battery-capable roles. Grid import/export and household
  load forecasts remain site-level inputs, and fresh PV forecasts are aggregated
  only when every configured PV source is available. The options flow provides
  native entity selectors, while advanced YAML remains supported; all values are
  exposed read-only and do not create an inverter write path.
- [x] Import the Home Assistant Energy Dashboard topology as the default source
  mapping. Grid, solar, battery, tariff, and solar-forecast entries are shown in
  the options flow with missing instantaneous sensors called out. Saving is
  blocked until missing PV telemetry is supplied, and the operator must provide
  a whole-home remaining-load forecast or enable historical estimation. When
  fresh grid, PV, and battery telemetry is available, PowerManager supplies a
  derived whole-home load sensor for that estimate; the Energy Dashboard itself
  does not provide the remaining-load forecast.
- [ ] Build a fixture-backed Speedwire source inventory and role decoder. Expose
  verified SMA and non-SMA telemetry through normalized HA sensors where a
  protocol adapter exists; retain address, identity confidence, capability, and
  last-seen metadata. Do not infer a control role from an IP address or from
  silence.
- [x] Read stable serial and firmware identity from the documented SI registers
  `30057`, `30061`, and `30063`; decode SMA's packed firmware format. The device
  registry now carries a serial identifier alongside the legacy entry identifier;
  explicit migration and physical firmware support validation remain outstanding.
- [x] Expose the decoded firmware identity as a read-only HA sensor; this does
  not establish that the observed firmware is approved for active control.
- [x] Report unsupported device types and undecodable firmware as separate HA
  issues while keeping the integration unavailable/monitor-only.
- [ ] Establish the actual supported firmware matrix and validate it against
  the target hardware.
- [x] Require tests, Ruff, hassfest, and HACS validation before publishing. The
  HACS release job now depends on all three repository validation jobs; actual
  hosted workflow results still need to be recorded.
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
- [x] Define hold/cooldown and preemption for changed/missing inputs, higher-priority
  rules, disablement, and no-match decisions. Higher-priority matches preempt a
  held lower-priority rule; disablement clears state and requests restoration.
- [x] Define recoverable watchdog expiry and explicit restoration decisions. An
  expired watchdog requests restoration and the next cycle can recover cleanly.
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

- [x] Require a successful read-only failsafe preflight, explicit enablement,
  ownership, and bounded power/duration at the setpoint boundary. Current
  telemetry approval is supplied by the session validation callback.
- [x] Revalidate the command through an optional async validation callback before
  every heartbeat. HA still needs to provide the production callback with live
  telemetry and ownership state.
- [x] Prevent overlapping sessions; cancellation cleanup is covered by fake
  transport tests. Manual override and emergency-stop precedence still need the
  HA control surface, and revoked control permission must not block recovery.
- [x] Separate transport timeouts from normal session expiry and enforce a
  configurable maximum session duration. Transport heartbeat timeouts now fail
  the session rather than being treated as normal expiry; duration uses the
  event loop's monotonic clock.
- [x] Capture approved baseline operating settings and verify restoration. The
  session restores communication/mode values and reads them back; the dedicated
  restore-normal path remains available for recovery.
- [x] Test partial restoration writes, failed restoration reporting, cancellation,
  overlapping sessions, and disconnected transport with fake transport. Clock
  changes are isolated by the monotonic deadline. Process restart policy is
  explicit: sessions are in-memory and never resume automatically; a fresh
  process remains monitor-only until separately authorized recovery.
- [x] Separate raw write capability from the read-only transport. The Modbus
  client now exposes writes only through `PymodbusTcpWriteTransport`; the
  Sunny Island monitor retains the read-only transport.
- [x] Add bounded, sanitized command/recovery events for diagnostics. The core
  session exposes a fixed-size event buffer for starts, failures, expiry,
  cancellation, and baseline restoration; event reasons are fixed categories
  and never include transport exception text. HA still needs to connect this
  surface to a commissioned control entry point before any writes are exposed.

Acceptance: fault injection demonstrates bounded sessions and explicit recovery
failure reporting. Production entry points remain disabled.

### 6. Complete supervised physical commissioning

Use the [commissioning record template](commissioning-record-template.md) for
the required approvals, read-only snapshot, rollback procedure, and observed
failure tests.

- [ ] Confirm supported single-cluster topology, firmware, active-power owner,
  and physical emergency-stop/rollback procedure with the operator.
- [ ] Verify sign, scaling, limits, persistence, activation, and fallback against
  applicable SMA documentation and observed behavior.
- [x] Record the operator-confirmed single-phase topology, sole Home Manager
  ownership, and the requirement to preserve existing Sunny Island settings.
- [ ] Document and rehearse the LS/RCD isolation procedure as the physical
  emergency action before any supervised PowerManager write test.
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

The integration now exposes an explicit `monitor_only` mode, an active-control
status and block reason, and two HA services. `powermanager.start_control` is a
bounded, explicit action; `powermanager.stop_control` stops the heartbeat and
restores the captured state. Both services reject calls unless every software
and commissioning gate passes. Fresh installs, reloads, and restarts remain
monitor-only and do not resume a prior command.

- [x] Add explicit HA enablement, power/reserve limits, ownership confirmation,
  firmware/topology confirmations, and a supervised LS/RCD isolation acknowledgement.
- [x] Keep the existing Sunny Island external-setpoint, fallback, timeout, and
  power-bound configuration unchanged. The active path only reads those settings
  during preflight; it never calls the configuration setters automatically.
- [x] Default fresh installs and uncertain restart states to monitor-only; prevent
  old commands resuming automatically. Unload stops the heartbeat and closes the
  write transport.
- [x] Revalidate ownership, telemetry freshness, battery operating state, SoC
  reserve, and power bounds before every heartbeat. Home Manager traffic or an
  unknown Speedwire sender blocks the session immediately.
- [ ] Complete supervised manual operation and failure-mode tests before setting
  the active-control enable option. The only physical isolation available here is
  the LS/RCD procedure; it must be rehearsed by the operator.
- [ ] Distinguish normal operation, zero active-power target, and charge inhibition.
  target_power_w: 0 does not establish “prevent charging while allowing discharge.”
  Keep the example intent simulation-only until verified.
- [ ] Enable scheduled delayed charging only after bounded manual operation passes.

Acceptance: manual actions are bounded/recoverable and schedules cannot bypass
their safety boundaries.

### 8. Implement and validate predictive charging

- [x] Model usable capacity, end-of-day SoC target, charging limits, export
  constraints, forecast uncertainty, and remaining time. The core planner is
  deterministic and side-effect-free, and its output remains safety-validated.
- [x] Plan headroom across the day instead of only fixed surplus thresholds;
  the planner returns explicit headroom and charge-inhibit semantics. It is
  now exposed through read-only HA shadow sensors and diagnostics, but cannot
  write an inverter target.
- [ ] Backtest recorded days with poor/missing forecasts, tariff changes, and
  seasonal/DST cases; compare reserve and end-of-day outcomes. The reusable
  backtest primitive exists, but no recorded deployment days have been loaded.
- [ ] Complete a documented shadow-mode period before supervised activation.
- [ ] Verify Speedwire measurement mappings if direct meter telemetry is needed;
  existing HA grid entities can remain an alternative. Add verified control-frame
  detection only as a diagnostic and immediate inhibit path; never use the lack of
  a detected command as proof that another controller is absent.

Acceptance: documented energy/reserve objectives and predictable degradation on
forecast failure, with the independent safety layer retaining final authority.

## Working instructions

Use uv sync --extra sma --extra dev, uv run pytest, and uv run ruff check .
Commit coherent batches without discarding user work. Update README, this handover,
roadmap, and control plan when status changes. Preserve monitor-only release
metadata until software and physical commissioning gates pass.
