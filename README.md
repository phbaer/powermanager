# PowerManager

PowerManager is an unofficial, fully local Home Assistant integration and reusable
Python core for monitoring home batteries. Its first backend targets an SMA Sunny
Island used in older Viessmann Vitocharge systems.

## Safety status

`0.1.0` is **monitor only**. A guarded write adapter, heartbeat, restore-normal
path, and read-only commissioning preflight are present, but no production
control is enabled. Active control remains gated on ownership and failure-mode
validation on the supported hardware, plus software safety and session-lifecycle
hardening. See the [production handover](docs/knowledge/production-handover.md)
for the ordered implementation checklist and acceptance gates.

Passive Home Manager detection warns about other SMA senders; it does not prove
their identity or exclusive control ownership. Warnings persist across polls and
listener retries. The warning's `observation_state` attribute distinguishes unknown,
offline, stale, and online observation. Failed listeners retry after 30 seconds;
traffic expires after 120 seconds. Silence never grants ownership eligibility.
Reload starts a new observation history. No indicator enables writes.

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
disabled until its simulation, safety validation, watchdog, hardware-specific
write adapter, and physical commissioning are complete.

The polling interval can be adjusted from the integration's Home Assistant options
flow (5–300 seconds). Connection details remain in the config entry and all device
communication remains read-only.

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

Simulation-only rules can be edited as versioned YAML in the integration
options. PowerManager exposes the currently matching simulated rule and its
requested target power, but never sends that target to the Sunny Island.

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
