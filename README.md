# PowerManager

PowerManager is an unofficial, fully local Home Assistant integration and reusable
Python core for monitoring home batteries. Its first backend targets an SMA Sunny
Island used in older Viessmann Vitocharge systems.

## Safety status

`0.1.0` remains **monitor only by default**. A guarded write adapter, heartbeat,
restore-normal path, and read-only commissioning preflight are present. Active
control requires explicit commissioning confirmations and remains fail-closed on
ownership, telemetry, operating state, power bounds, watchdog, and session
lifecycle. See the [production handover](docs/knowledge/production-handover.md)
for the ordered implementation checklist and acceptance gates.

Passive Home Manager detection warns about other SMA senders; it does not prove
their identity or exclusive control ownership. Warnings persist across polls and
listener retries. The warning's `observation_state` attribute distinguishes unknown,
offline, stale, and online observation. Its `observed_sources` and
`external_sources` attributes show the IPv4 senders seen on Speedwire; diagnostics
include the external list for identifying a broadcaster on the local LAN.
Failed listeners retry after 30 seconds; traffic expires after 300 seconds in the
HA coordinator. Silence never grants ownership eligibility. Reload starts a new
observation history. No indicator enables writes.

An observed sender address is not treated as a device-role determination. Verified
telemetry-only devices can be added to normalized HA sensors in future protocol
adapters, while unknown or control-capable sources remain a control blocker. Any
verified control datagram must inhibit control immediately; silence or missing
packets can never authorize it.

## Development

The project uses [uv](https://docs.astral.sh/uv/) for fast, reproducible local
environment management. Install uv, then run:

```bash
uv sync --extra sma --extra dev
uv run pytest
uv run ruff check .
uv run powermanager status --host 192.168.1.50
uv run powermanager commission --host 192.168.1.50
uv run powermanager speedwire-capture --duration 60 --show-hex
```

When selecting a specific LAN interface, pass its local address with
`--interface` (for example `10.0.1.254`). The listener binds the UDP socket to
the wildcard address and uses that value only to select the multicast interface.

The committed `uv.lock` keeps the development and SMA protocol dependencies
reproducible. Use `uv lock --upgrade` deliberately when updating dependencies.

The Home Assistant integration is located at `custom_components/powermanager` and is
packaged directly by the release workflows for HACS.

The planned control architecture and declarative rule format are documented in
[`docs/knowledge/control-plan.md`](docs/knowledge/control-plan.md). Control remains
disabled unless the operator explicitly enables the commissioned scheduled or
manual path. The predictive scheduler is an opt-in constrained to measured PV
surplus.

The polling interval can be adjusted from the integration's Home Assistant options
flow (5–300 seconds). Connection details remain in the config entry; device
communication is read-only unless the explicit active-control gates are enabled.

The integration exposes the current control mode and includes the block reason in
diagnostics. It also reads the Sunny Island serial number and packed firmware
identity for stable device metadata. These indicators do not authorize control;
supervised hardware commissioning is still required before any command adapter
can be used.

The integration includes explicit `powermanager.start_control` and
`powermanager.stop_control` services for a bounded manual session. They remain
locked unless the operator enables active control and confirms the single-phase
topology, firmware/fallback behavior, sole ownership, and the LS/RCD isolation
procedure. Every heartbeat rechecks fresh telemetry, SoC reserve, operating
state, ownership, and configured power bounds. Existing Sunny Island external
setpoint, fallback, timeout, and power-bound settings are read during preflight
and never rewritten by PowerManager. A restart or unload cannot resume a prior
session. Scheduled control is a separate opt-in and must follow supervised
manual testing. The supervised HA instance has the predictive option enabled;
loading and health checks passed, but a successful live write has not been
independently verified in this handover.

Sunny Island event `7613` (“communication with meter faulty”) is treated as a
charge-only warning: a bounded charge request may proceed when all other safety
inputs are fresh, while discharge remains blocked and grid-dependent rules still
require valid grid telemetry. Other warning or error events remain blocked.

The disconnected command-session adapter keeps a bounded, sanitized event buffer
for future diagnostics and verifies baseline restoration after each bounded test
session. Home Assistant setup removes that passive monitor state if platform
forwarding fails or the entry unloads, so retries cannot inherit a leaked
listener.

Optional grid/PV/load and price telemetry is accepted only while fresh. Grid
power is normalized from kW to W. Configure either a market-price entity or a
fixed contract import price in EUR/kWh; a fixed price does not require a Home
Assistant helper. A market-price entity must expose an explicit
currency-per-energy unit: prices in `/MWh` are normalized to `/kWh`, while
unitless or ambiguous prices are not used.

For grid exchange, configure either one signed instantaneous-power entity
(positive import, negative export), or both separate import and export power
entities. The latter normally map to OBIS `1.7.0` and `2.7.0`. OBIS `1.8.0`
and `2.8.0` are cumulative energy counters, so they are deliberately not
accepted as grid-power sources.

The options flow accepts one or more local remaining-PV forecast entities and
an expected-remaining-load forecast entity. They must expose Wh, kWh, or MWh.
Separate PV forecasts are summed only when every selected value is fresh. They
are used only for simulation/policy eligibility; neither forecast data nor a
policy can enable a device write.

Charging is additionally bounded by the current measured PV surplus. A positive
charge target is rejected when fresh site telemetry cannot prove enough PV power
is available, or when the target would exceed the conservative minimum of PV
minus load and measured grid export. PV generation and household load telemetry
are required; grid export alone is not treated as proof that solar energy is
available. The example rules keep their targets at or below their export
thresholds as an additional policy guard.

Energy Dashboard interval forecasts also expose the predicted PV power for the
currently active interval. Rules can use `forecast_pv_power_above_w` to choose
charge tiers from the forecast itself, so a policy does not assume that noon is
the daily production peak. If the forecast platform does not provide an active
interval, that condition remains ineligible and the policy can fall back to
measured-export rules.

Multiple inverter telemetry sources can be configured with the optional
`inverters_yaml` option. The options flow also offers native Home Assistant
entity pickers: set the number of profiles and complete one role-aware form per
inverter. The YAML field remains available for advanced import/export. Each
source is read from existing Home Assistant entities:

When the Home Assistant Energy Dashboard is configured, PowerManager imports its
grid, solar, battery, tariff, and solar-forecast topology automatically. The
options form prints every imported PV source and any missing instantaneous
sensor. It refuses to save an incomplete dashboard topology until the missing
source is supplied manually. A whole-home remaining-load forecast (or the
automatically derived PowerManager whole-home load sensor plus historical
estimation) is also required because the Energy Dashboard has no household load
forecast. The derived sensor is only populated when signed grid, PV, and battery
telemetry is fresh.

```yaml
inverters:
  - id: sunnyboy_main
    role: pv
    generation_power_entity: sensor.sunnyboy_power
    remaining_pv_forecast_entity: sensor.sunnyboy_remaining_forecast
  - id: garage_hybrid
    role: hybrid
    generation_power_entity: sensor.garage_pv_power
    battery_power_entity: sensor.garage_battery_power
    remaining_pv_forecast_entity: sensor.garage_remaining_forecast
```

PV generation values are normalized to watts and PV forecasts to kWh. Battery
power is an optional signed value for battery-capable or hybrid sources. Grid
import/export and household load forecasts remain site-level inputs; they are
never inferred from PV inverter output and are not duplicated per inverter.
When no site PV forecast is configured, all configured PV forecasts must be
fresh before they are combined for simulation and the predictive planner.
The sources remain read-only and do not create an inverter write path.

Simulation-only rules can be edited as versioned YAML in the integration
options. PowerManager exposes the currently matching simulated rule and its
requested target power, but never sends that target to the Sunny Island.

The core also includes a predictive planner that accounts for usable capacity,
reserve and end-of-day targets, forecast uncertainty, export capacity, current
PV surplus, and charge limits. It produces explainable recommendations and
deterministic replay and SoC/reserve outcome results for backtesting. Home
Assistant exposes the recommendation and its reason as sensors. The
`predictive_control_enabled` option can promote that recommendation into the
existing bounded scheduled-control path after all active-control commissioning
gates pass; it remains disabled by default and never authorizes grid charging
or a target above measured PV surplus.
The Sunny Island remains the authority for battery SoC estimation, charging
phases, and battery protection. PowerManager must send bounded power targets and
must never write or invent a battery SoC.

PowerManager adds recorder-friendly forecast sensors for PV power now, estimated
household load power now, planned charge power, planned discharge power, and the
PV/load forecast errors. The PV and estimated-load sensors include a timestamped
`forecast_profile` attribute for the next 24 hours. Add the sensors to a native
Home Assistant history graph to compare predictions with measured PV and load:

```yaml
type: history-graph
title: PowerManager forecast validation
hours_to_show: 24
entities:
  - sensor.<device>_forecast_pv_power_now
  - sensor.<device>_pv_power
  - sensor.<device>_forecast_load_power_now
  - sensor.<device>_load_power
  - sensor.<device>_planned_charge_power
  - sensor.<device>_planned_discharge_power
  - sensor.<device>_forecast_pv_error
  - sensor.<device>_forecast_load_error
```

The exact entity IDs are shown in the integration device. This graph records
what PowerManager predicted at each poll and what actually happened afterward;
the forecast profile attribute exposes the next 24 hours of future PV/load
points used by the planner. The profile is deliberately bounded so Home
Assistant Recorder can retain the attributes. Load estimation prefers recent
complete days with the same weekday and
falls back to recent complete days when Recorder lacks enough matching history.

Instead of supplying an expected-load forecast entity, PowerManager can estimate
the remaining load until local midnight from the selected whole-home load-power
entity. It averages the same remainder of each of the configured number of
complete prior days (seven by default) using local Recorder history. The
estimate is withheld if any required day is incomplete, stale, or invalid.

`powermanager commission` performs a read-only preflight of the Sunny Island's
external-setpoint and fallback configuration. It never sends a setpoint or changes
an inverter parameter.

`speedwire-capture` passively prints validated SMA multicast frames for protocol
analysis; it does not transmit packets or decode unverified measurement offsets.

### Speedwire capture troubleshooting

If the Home Manager is transmitting but capture is empty, check the host
firewall. UFW commonly blocks SMA multicast UDP even when the switch has IGMP
snooping disabled. For a host whose LAN interface is
`enp0s13f0u1u4`, allow only the Home Manager sender and Speedwire port:

```bash
sudo ufw allow in on enp0s13f0u1u4 from 10.0.1.192 to any port 9522 proto udp
```

Adjust the interface and Home Manager address for your network. The rule is
optional when the host firewall is disabled; do not broadly expose UDP/9522 to
untrusted networks.

For a remote Home Assistant host, `scripts/speedwire-relay.py` can run on a LAN-side
machine and forward validated frames over unicast UDP:

```bash
python3 scripts/speedwire-relay.py --destination-host 10.0.12.2
```

The receiving listener must be configured for the chosen unicast port (default
`19522`). The relay is intentionally raw and read-only: it never sends anything to
the SMA multicast group.

### Speedwire protocol status

A live capture from a Sunny Home Manager on the local LAN produced 608-byte
telegrams from `10.0.1.192` to `239.12.255.254:9522`. The payload contains SMA's
documented `0x6069` energy-meter protocol. The captured fixture now validates
telegram framing and individual raw records. Semantic mapping of those records
to grid or PV values remains pending independent verification.

## Supported backend status

| Backend | Status |
| --- | --- |
| SMA Sunny Island Modbus TCP | Read-only identity and battery measurements verified against an SI4.4M-12 |
| SMA Sunny Home Manager / Speedwire | Planned passive telemetry provider |
| Active battery control | Not implemented |

Continuous integration runs unit tests, Ruff, HACS validation, and Home
Assistant `hassfest`. Hardware commissioning is deliberately not a CI task and
remains a supervised, read-only-first field procedure.
