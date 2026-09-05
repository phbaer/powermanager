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
