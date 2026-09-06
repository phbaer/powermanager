---
type: Control Plan
title: Battery control architecture and rules
description: Safe infrastructure for defining, simulating, and executing battery control processes.
tags: [control, rules, safety, planning]
status: draft
---

# Control architecture

Control is a separate layer above telemetry and below Home Assistant:

```text
Telemetry → normalized EnergyState → policy engine → ControlIntent
                                      ↓
                              safety validator
                                      ↓
                              actuator adapter
```

The policy engine must be deterministic and testable without hardware. It emits
an intent, never a raw Modbus write. The safety validator checks reserves,
limits, freshness, bounds, operating state, and explicit enablement. Only the
actuator adapter may communicate with a device.

## Rule/process definition

Rules should be versioned YAML stored in the repository or supplied through a
Home Assistant package. A rule has a priority, conditions, an action, and an
optional hold/cooldown period:

```yaml
version: 1
enabled: false
rules:
  - id: charge-surplus
    priority: 100
    when:
      grid_power_below_w: -500
      battery_soc_below_percent: 90
      between: ["09:00", "16:00"]
    then:
      target_power_w: 1500
    hold_seconds: 300
```

Rules are evaluated in priority order. A missing or stale input makes a rule
ineligible. Hysteresis and minimum hold times prevent rapid toggling. The
default mode is simulation/dry-run; execution requires an explicit control
enable switch and a valid safety configuration.

## Forecast inputs

The Home Assistant options flow can use existing local entities for remaining
PV forecast and expected remaining load. Values must have an explicit
Wh/kWh/MWh unit and are normalized to kWh. A rule can use
`forecast_surplus_above_kwh`; it is eligible only when both fresh values are
available. This is a planning/simulation input, not authorization for active
control. Energy Dashboard interval forecasts additionally provide the current
predicted PV power in watts. Use `forecast_pv_power_above_w` for charge tiers
that should follow the predicted production peak instead of a fixed clock
window. If that interval value is unavailable, the condition does not match.

## Predictive shadow planning

`control.predictive` provides a deterministic, side-effect-free planner for
remaining PV/load energy, forecast uncertainty, usable capacity, reserve and
end-of-day SoC targets, export capacity, and reported charge limits. It returns
an explainable target, required energy, headroom, and an explicit charge-inhibit
flag. A zero target is never interpreted as a generic inverter mode. The
planner can replay timestamped inputs and report SoC, reserve, grid-energy, and
curtailment outcomes for backtests. It is not connected to Home Assistant write
control and remains subordinate to `control.safety`.

## Control milestones

1. Define typed conditions/actions and deterministic policy evaluation.
2. Add simulation and trace output using recorded `EnergyState` fixtures.
3. Add safety validation and a no-op actuator.
4. Add a verified Sunny Island write adapter with watchdog and restore-normal.
5. Expose enablement, policy selection, preview, and emergency stop in HA.

# Safety gates

- No write is possible when control is disabled or telemetry is stale.
- Every command has a bounded duration and a fallback target.
- A watchdog restores normal inverter behavior after missed heartbeats.
- Manual stop supersedes rules. Where no dedicated emergency stop exists, the
  operator's documented LS/RCD isolation procedure remains the physical boundary.
- Production execution requires hardware-specific register verification.

The adapter, heartbeat, restore-normal operation, and read-only preflight exist.
The core now has per-source freshness and operating-limit validation, consistent
HA simulation, continuous session validation callbacks, bounded sessions, and
verified baseline restoration after failures. Home Assistant exposes a bounded
manual command service and an optional scheduled path, but both remain locked
behind explicit commissioning gates and are disabled by default. The HA path
reads the configured external-setpoint/fallback settings and does not rewrite
them.

Session timing uses a monotonic deadline and session state is not persisted, so
restarts never resume a prior command. Recovery after a restart remains an
explicitly authorized commissioning action.

Physical commissioning is a separate mandatory gate. Confirm topology, ownership,
firmware behavior, fallback, and an emergency-stop procedure before wiring any
live control path. Follow the ordered [production handover](production-handover.md).
