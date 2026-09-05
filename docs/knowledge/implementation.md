---
type: Implementation
title: Current implementation
description: Operational details for the read-only PowerManager release.
tags: [implementation, operations, uv]
status: stable
---

# Components

- `custom_components/powermanager/core/powermanager_core`: reusable Python core.
- `custom_components/powermanager`: Home Assistant integration.
- `scripts/speedwire-relay.py`: dependency-free LAN-to-unicast relay.
- `.github/workflows` and `.forgejo/workflows`: CI and HACS packaging.

## Local development

```bash
uv sync --extra sma --extra dev
uv run pytest
uv run ruff check .
uv run powermanager status --host 10.0.1.240
```

## Optional HA telemetry

The integration options flow accepts entity IDs for grid, PV, and load power.
Values are read from the HA state machine, converted from kW to W when needed,
and exposed as read-only sensors. Empty fields leave `EnergyState.grid` unset.
Sources older than the configured maximum age are classified as stale and are
never supplied to a control policy. Market-price entities must state an explicit
`/kWh` or `/MWh` unit; `/MWh` prices are normalized to `/kWh` and ambiguous
unitless values are rejected.

The Home Assistant layer also accepts an optional `inverters_yaml` source list,
or the options flow can build the same list with native entity selectors. Each
source declares a `pv`, `battery`, or `hybrid` role. PV sources provide one
generation-power entity and may provide a remaining-PV forecast; battery-capable
sources may provide one signed battery-power entity. Grid import/export and the
household load forecast stay site-level inputs. PV forecasts are aggregated only
when every configured PV forecast is fresh. This adapter is read-only; direct
Speedwire identity and role decoding remains a separate fixture-backed task.

The adapter also reads Home Assistant's Energy Dashboard manager. Its grid
`stat_rate`, solar `stat_rate`, battery `stat_rate`, tariff, and configured solar
forecast entries are imported as defaults. The options flow displays the
imported PV topology and blocks saving when a configured source has no usable
instantaneous sensor. Since the dashboard stores no whole-home remaining-load
forecast, the operator must provide one or enable Recorder-based estimation. When
fresh grid, PV, and battery telemetry is available, the latter uses PowerManager's
derived whole-home load sensor automatically.

The core safety validator also checks direct model inputs: source communication
state, per-source freshness, timestamps in the future, finite targets, battery
SoC, operating state, maximum charge SoC, dynamic discharge floor, and reported
charge limits. HA simulation uses the same runtime as standalone simulation and
reports its decision reason, hold state, and watchdog restoration status.

The reusable predictive planner calculates forecast-adjusted surplus, required
energy, battery headroom, and bounded optional grid charging without side
effects. `replay_predictive_plans` and `backtest_predictive_day` provide
deterministic input replay and outcome aggregation for recorded-day backtests.
It is shadow-only and is not connected to the HA
write transport. HA can expose its target, headroom, inhibit flag, and reason
through read-only sensors after forecast options are configured.

The control adapter is not connected to the coordinator. Its setpoint boundary
requires a successful read-only failsafe preflight, explicit ownership and
enablement, bounded sessions, heartbeat validation, and baseline restoration with
readback. Recovery writes are isolated from the monitor transport and remain
available only to the separately reviewed adapter. Bounded sessions retain
sanitized start, failure, expiry, cancellation, and restoration events for a
future diagnostics surface; they never include transport exception text. HA
entry setup and unload also clean up the passive listener and coordinator state
when platform forwarding fails or the entry is released.

Command sessions use the event loop's monotonic clock for their duration bound.
Session state is intentionally not persisted: a process or Home Assistant
restart cannot resume an old command, and the fresh integration remains
monitor-only until a separately authorized recovery operation.

## CI validation

The HACS release job now gates packaging on the repository tests, Ruff, HACS
validation, and hassfest. A successful workflow run is still not a substitute
for the required physical monitoring soak or hardware commissioning. See the
[production handover](production-handover.md) for acceptance gates and current
passive observation behavior.

GitHub Actions run core tests and Ruff, HACS validation, and Home Assistant
`hassfest`. `hassfest` is scheduled daily as well as on integration changes.

## Speedwire relay

```bash
python3 scripts/speedwire-relay.py \
  --destination-host 10.0.12.2 --destination-port 19522
```

The relay forwards only datagrams with the verified common SMA Speedwire header.
It does not decode or modify payloads.
