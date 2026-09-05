---
type: Architecture
title: PowerManager architecture
description: Layered design separating battery backends, telemetry providers, and Home Assistant.
tags: [architecture, modularity, safety]
status: stable
---

# Runtime layers

```text
Home Assistant integration
  config flow · coordinator · sensors · diagnostics
             │
             ├── HA entity telemetry adapter (optional)
             │
Reusable Python core
  BatteryBackend · GridTelemetryProvider · normalized models
             │
             ├── SMA Sunny Island Modbus TCP (required battery backend)
             └── SMA Speedwire (optional grid provider)
```

The core has no Home Assistant dependency. It exposes normalized `BatteryState`,
`GridState`, and `EnergyState` models. Implementations of
`GridTelemetryProvider` may live in the Home Assistant layer or in independent
network backends.

## Safety boundary

Version 0.1 is monitor-only by default. A guarded Modbus write adapter and
Home Assistant command path exist for supervised commissioning, but explicit
enablement, time limits, ownership, fresh telemetry, and fail-safe checks keep
them locked until the operator enables them. Any future write backend must
preserve the same hardware safety boundary.

## Deployment modes

- Same LAN: Home Assistant or a collector joins Speedwire multicast directly.
- Routed/VPN: a LAN-side relay forwards validated frames as unicast UDP.
- ESPHome meters: the HA adapter reads existing numeric entities; Speedwire is
  unnecessary.
