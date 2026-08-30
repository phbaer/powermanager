# PowerManager

PowerManager is an unofficial, fully local Home Assistant integration and reusable
Python core for monitoring home batteries. Its first backend targets an SMA Sunny
Island used in older Viessmann Vitocharge systems.

## Safety status

`0.1.0` is **monitor only**. It performs read-only Modbus requests and contains no
Modbus write operation or battery-control command. Active control will not be added
until the exact Sunny Island register semantics and controller-failure behaviour have
been verified on the supported hardware.

## Development

The project uses [uv](https://docs.astral.sh/uv/) for fast, reproducible local
environment management. Install uv, then run:

```bash
uv sync --extra sma --extra dev
uv run pytest
uv run ruff check .
uv run powermanager status --host 192.168.1.50
uv run powermanager speedwire-capture --duration 60 --show-hex
```

The committed `uv.lock` keeps the development and SMA protocol dependencies
reproducible. Use `uv lock --upgrade` deliberately when updating dependencies.

The Home Assistant integration is located at `custom_components/powermanager` and is
packaged directly by the release workflows for HACS.

The polling interval can be adjusted from the integration's Home Assistant options
flow (5–300 seconds). Connection details remain in the config entry and all device
communication remains read-only.

`speedwire-capture` passively prints validated SMA multicast frames for protocol
analysis; it does not transmit packets or decode unverified measurement offsets.

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
documented `0x6069` energy-meter protocol. The protocol decoder remains pending
until the encapsulation and record alignment are covered by a reproducible fixture;
raw frames are therefore not converted into grid or PV values yet.

## Supported backend status

| Backend | Status |
| --- | --- |
| SMA Sunny Island Modbus TCP | Read-only identity and battery measurements verified against an SI4.4M-12 |
| SMA Sunny Home Manager / Speedwire | Planned passive telemetry provider |
| Active battery control | Not implemented |
