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
- Manual override and emergency stop always supersede rules.
- Production execution requires hardware-specific register verification.
