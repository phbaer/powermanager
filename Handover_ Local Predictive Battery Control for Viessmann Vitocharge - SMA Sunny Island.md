# Handover: Local Predictive Battery Control for Viessmann Vitocharge / SMA Sunny Island

## Objective

Build a robust, fully local controller for an older Viessmann Vitocharge battery system based on an SMA Sunny Island.

The main goal is to control *when* the battery charges from PV.

Currently, normal self-consumption behavior tends to charge the battery as soon as PV surplus becomes available in the morning. I want to delay or limit morning charging so that battery capacity remains available for the midday PV peak.

Longer term, charging should be dynamically optimized based on PV/weather forecasts rather than fixed time windows.

The control loop itself must work locally and must not depend on Sunny Portal or another cloud service.

The software architecture should be **independent of Home Assistant at its core**, but the default deployment and user-facing integration should be a **Home Assistant custom integration installable via HACS**.

---

# Existing Hardware

Battery system:
- Viessmann Vitocharge, older generation using SMA technology
- Battery capacity: 2 × 4.5 kWh ≈ 9 kWh nominal

Battery inverter:
- SMA Sunny Island SI4.4M-12

Energy management:
- SMA Sunny Home Manager
- Hostname observed on LAN: `SMA3006136122`

The exact Sunny Home Manager generation should still be identified if relevant.

Preferred controller runtime:
- Home Assistant installation as the default deployment target
- Python core library reusable independently of Home Assistant
- Raspberry Pi / Linux mini-PC also supported for standalone development/testing

Optional later components:
- MQTT
- Node-RED
- ESP32 / ESPHome

ESP32/ESPHome should not be the primary controller.

---

# Fundamental Requirements

The actual battery control must be local.

Internet access may optionally be used later for weather/PV forecasts, but:

- Sunny Portal must not be required for the control loop.
- Loss of Internet must not break normal battery operation.
- Loss of Home Assistant must leave the Sunny Island in a safe operating state.
- The protocol and control implementation must not depend on Home Assistant internals.
- Home Assistant must act as an integration/wrapper around a reusable Python library.

---

# Core Architectural Principle

Use a layered architecture:

    Home Assistant Integration
             |
             v
    Independent Python Core
      /       |        \
     /        |         \
Modbus   Home Manager   Control
Client    Listener       Logic
     \        |         /
      \       |        /
       Unified Energy State

The independent core must contain:

- SMA Modbus communication
- SMA register definitions
- SMA value decoding
- Sunny Island abstraction
- Sunny Home Manager / Speedwire listener
- unified state model
- control algorithm
- safety logic
- optional forecast abstraction

The Home Assistant integration should primarily provide:

- configuration
- setup/discovery
- entities
- diagnostics
- services
- options
- lifecycle management
- UI exposure

Do not place critical protocol logic directly inside Home Assistant entity classes.

---

# Default Distribution Model

The project should be designed as a **HACS-compatible Home Assistant integration from the start**.

Repository should be structured so a user can add it as a custom HACS repository and install it without manually copying files.

Target installation flow:

1. User adds GitHub repository to HACS as a custom repository.
2. Repository appears as an Integration.
3. User installs it through HACS.
4. Home Assistant restarts.
5. Integration is added through:

       Settings
       → Devices & Services
       → Add Integration
       → SMA Local Battery Controller

6. User enters/discovers Sunny Island and Sunny Home Manager settings.
7. Integration exposes sensors and controller configuration.

No YAML configuration should be required for normal installation.

---

# Suggested Repository Structure

Use a repository layout approximately like:

    sma-local-battery-controller/
    ├── README.md
    ├── LICENSE
    ├── hacs.json
    ├── pyproject.toml
    ├── requirements-dev.txt
    ├── .gitignore
    ├── .github/
    │   └── workflows/
    │       ├── tests.yml
    │       ├── hassfest.yml
    │       └── hacs.yml
    │
    ├── sma_local/
    │   ├── __init__.py
    │   ├── config.py
    │   ├── models.py
    │   ├── constants.py
    │   ├── exceptions.py
    │   │
    │   ├── modbus/
    │   │   ├── __init__.py
    │   │   ├── client.py
    │   │   ├── decoder.py
    │   │   ├── registers.py
    │   │   └── types.py
    │   │
    │   ├── sunny_island/
    │   │   ├── __init__.py
    │   │   ├── device.py
    │   │   ├── state.py
    │   │   └── control.py
    │   │
    │   ├── home_manager/
    │   │   ├── __init__.py
    │   │   ├── listener.py
    │   │   ├── parser.py
    │   │   └── state.py
    │   │
    │   ├── controller/
    │   │   ├── __init__.py
    │   │   ├── engine.py
    │   │   ├── safety.py
    │   │   ├── modes.py
    │   │   └── policy.py
    │   │
    │   └── forecast/
    │       ├── __init__.py
    │       ├── base.py
    │       └── models.py
    │
    ├── custom_components/
    │   └── sma_local_battery/
    │       ├── __init__.py
    │       ├── manifest.json
    │       ├── const.py
    │       ├── config_flow.py
    │       ├── coordinator.py
    │       ├── sensor.py
    │       ├── binary_sensor.py
    │       ├── number.py
    │       ├── select.py
    │       ├── switch.py
    │       ├── diagnostics.py
    │       ├── services.yaml
    │       ├── translations/
    │       │   └── en.json
    │       └── strings.json
    │
    └── tests/
        ├── core/
        │   ├── test_decoder.py
        │   ├── test_registers.py
        │   ├── test_sunny_island.py
        │   └── test_controller.py
        │
        └── homeassistant/
            ├── test_config_flow.py
            ├── test_coordinator.py
            └── test_entities.py

The exact packaging can be adjusted if Home Assistant packaging constraints make a different layout cleaner.

The key principle is:

**Home Assistant must consume the same standalone Python core used by tests and optional CLI tooling.**

---

# HACS Requirements

Include a valid `hacs.json`.

Example intent:

    {
      "name": "SMA Local Battery Controller",
      "render_readme": true,
      "homeassistant": "2025.x.x"
    }

Use the currently supported HACS schema when implementing.

Add GitHub Actions for:

- Python unit tests
- Home Assistant `hassfest`
- HACS validation

The repository should pass both HACS and Home Assistant custom integration validation.

---

# Home Assistant Integration Domain

Suggested domain:

    sma_local_battery

Suggested integration name:

    SMA Local Battery Controller

Avoid naming that implies official SMA endorsement.

README should clearly state that this is an unofficial local integration.

---

# Home Assistant Configuration Flow

Use `config_flow.py`.

Normal setup should be entirely UI-based.

Initial setup fields:

- Sunny Island host/IP
- Modbus port
- Modbus Unit ID
- enable Sunny Home Manager listener
- optional Home Manager serial/device identifier if required

Defaults:

    port = 502
    unit_id = 3

Do not hard-code the IP.

Where possible, attempt local discovery.

If mDNS, SSDP, SMA discovery, or another reliable LAN discovery mechanism is available, support it.

Do not make discovery a hard requirement.

---

# Config Entry Validation

During setup:

1. Connect READ ONLY to Sunny Island.
2. Read device type.
3. Verify that the device is compatible.
4. Confirm expected SI4.4M-12 device identifier if documented.
5. Reject setup with a clear error if Modbus is unavailable or the device is unsupported.

Do not write anything during setup.

---

# Options Flow

Use a Home Assistant Options Flow for runtime configuration such as:

- polling interval
- control mode
- minimum battery SoC
- maximum target SoC
- morning charge inhibition
- forecast reserve
- Home Manager usage
- forecast provider
- safety timeout

Any setting that can affect battery control must have conservative defaults.

---

# Home Assistant Coordinator

Use a central coordinator rather than having every entity poll independently.

For example:

    SMADataUpdateCoordinator

Responsibilities:

- periodically read Sunny Island state
- maintain Home Manager state
- merge data into unified `EnergyState`
- expose freshness/health information
- handle reconnects
- execute control engine at a controlled interval
- make state available to entities

Protocol calls should still live in the independent core.

The coordinator should orchestrate the core, not implement SMA protocols itself.

---

# Home Assistant Entities

Initial READ-ONLY entities should include sensors such as:

Battery:
- battery SoC
- battery power
- battery voltage
- battery current
- battery charge power
- battery discharge power
- dynamic discharge limit
- Sunny Island operating state

Grid:
- grid import/export power
- grid L1/L2/L3 power if available
- Home Manager communication state

Controller:
- controller mode
- data freshness
- Sunny Island communication state
- Home Manager communication state
- last successful update
- control safety state

Use proper Home Assistant device classes and units where possible.

---

# Device Registry

Create Home Assistant devices for at least:

## Sunny Island

Identifiers should use stable SMA device information such as serial number/device identifier if available.

Expose:
- manufacturer: SMA
- model: Sunny Island SI4.4M-12
- firmware version if available
- serial number if available

## Sunny Home Manager

If enough identity information is available, register it as a separate device.

The controller integration itself may also expose a logical controller device if useful.

---

# Home Assistant Controls — Later Phase

Once write support is proven safe, expose explicit control entities.

Potential entities:

`select`:
- Off / Monitor Only
- Normal
- Delay Charging
- Predictive
- Manual

`number`:
- minimum SoC
- reserve SoC
- maximum charge power
- desired end-of-day SoC

`switch`:
- enable active control

The active-control switch must default to OFF.

A fresh installation must therefore start in:

    Monitor Only

No write-capable behavior should activate automatically after installing the integration.

---

# Home Assistant Services

Later, optionally provide explicit services such as:

    sma_local_battery.set_control_mode

    sma_local_battery.set_power_limits

    sma_local_battery.restore_normal_operation

Services that cause writes must perform full validation and must fail closed.

`restore_normal_operation` should be especially easy to call.

---

# Diagnostics

Implement Home Assistant diagnostics support.

Diagnostics should include:

- integration configuration with secrets/IPs redacted as appropriate
- device model
- firmware version
- recent communication health
- latest decoded state
- active control mode
- controller safety state
- last command sent
- Home Manager listener state

Never include credentials.

---

# Repairs / Warnings

Use Home Assistant Repairs or persistent issues where appropriate for states such as:

- unsupported Sunny Island firmware
- Modbus disabled
- stale Home Manager data
- control mode requested but write support unavailable
- repeated communication failures
- forecast unavailable while predictive mode requested

Do not silently fall back from an explicitly requested control mode without notifying the user.

---

# Sunny Island Communication

The Sunny Island SI4.4M-12 supports SMA Modbus TCP.

Expected defaults / known information from SMA documentation:

- Modbus TCP
- TCP port typically `502`
- Unit ID commonly `3`

These values must be configurable.

The controller should communicate directly with the Sunny Island.

---

# Important Modbus Registers Identified So Far

These addresses came from prior research but MUST be verified against official SMA Modbus documentation applicable to the SI4.4M-12.

Known/expected:

`30053`
Device type

Expected SI4.4M-12 device ID:
`9332`

`30201`
Device status

`31009`
Relevant dynamic battery discharge limit / lower discharge boundary.

Potential external active-power control:

`44039`
Maximum active power

`44041`
Minimum active power

Working assumption:

- positive → battery discharge
- negative → battery charge

Conceptually:

Normal bidirectional operation:

    min = -100 %
    max = +100 %

Prevent charging while allowing discharge:

    min = 0 %
    max = +100 %

Force charging:

    min = negative value
    max = same negative value

Force discharging:

    min = positive value
    max = same positive value

DO NOT implement writes based solely on this handover.

Verify:

- exact addresses
- datatype
- scaling
- sign convention
- allowed range
- write permissions
- persistence
- activation requirements
- supported operating modes
- firmware compatibility
- timeout/fallback behavior

against official SMA documentation.

---

# Development Phase 1 — Read Only

The first implementation MUST NOT contain active Modbus write behavior.

Build the independent Python core first.

Requirements:

1. Configurable Sunny Island host.
2. Configurable TCP port.
3. Configurable Unit ID.
4. Connection timeout.
5. Automatic reconnect.
6. Structured logging.
7. Graceful handling of unreachable devices.
8. No battery-control writes.

Read and decode at least:

- device type
- serial number
- firmware version if available
- device status
- battery SoC
- battery active power
- battery voltage
- battery current
- relevant battery limits
- grid power if useful and available

All data handling must be reusable from both standalone tests and the Home Assistant integration.

---

# SMA Modbus Data Handling

Implement typed reusable register definitions.

For example:

    RegisterDefinition(
        key="battery_soc",
        address=...,
        width=2,
        data_type=S32,
        scale=0.01,
        unit="%",
        invalid_values=(...),
        writable=False
    )

Support as required:

- U16
- S16
- U32
- S32
- SMA enumerations
- scaling
- invalid/sentinel values

Never interpret an SMA invalid sentinel as a valid physical measurement.

Convert unavailable values to `None`.

Raw register addresses should exist in one register-definition module, not throughout the application.

---

# Standalone Core API

Design the core so this works without Home Assistant:

    async with SunnyIslandClient(...) as si:
        state = await si.read_state()

    print(state.battery_soc)
    print(state.battery_power_w)

Potential high-level API:

    class SunnyIsland:
        async def read_state(self) -> SunnyIslandState:
            ...

        async def get_device_info(self) -> DeviceInfo:
            ...

Write methods should not be implemented in Phase 1.

---

# Optional Standalone CLI

Even though Home Assistant/HACS is the primary deployment target, provide a small developer CLI.

Example:

    python -m sma_local status --host 192.168.1.50

or:

    sma-local status --host 192.168.1.50

Output example:

    SMA Sunny Island SI4.4M-12
    Serial:           ...
    Device ID:        9332
    Status:           Operating
    Battery SoC:      42.0 %
    Battery Power:    -820 W
    Battery Voltage:  ...
    Grid Power:       ...
    Discharge Limit:  ...

The CLI is for development/debugging and should use the exact same core library as Home Assistant.

---

# Development Phase 2 — Sunny Home Manager Listener

Implement a passive local listener for Sunny Home Manager / SMA Speedwire multicast traffic.

Known candidate network details:

- UDP 9522
- multicast group commonly `239.12.255.254`

Verify protocol behavior before assuming packet layouts.

Desired measurements:

- grid import/export
- phase power
- possibly consumption/PV-derived values

The Home Manager listener belongs in the independent core.

The Home Assistant wrapper should simply consume its decoded state.

---

# Unified Energy State

Create a unified model independent of Home Assistant.

For example:

    EnergyState(
        timestamp=...,
        battery_soc=0.42,
        battery_power_w=-820,
        battery_voltage_v=...,
        battery_current_a=...,
        grid_power_w=-2100,
        pv_power_w=...,
        load_power_w=...,
        battery_charge_limit_w=...,
        battery_discharge_limit_w=...,
        sunny_island_online=True,
        home_manager_online=True,
    )

Use SI units internally.

Home Assistant-specific units/conversion should happen only in the integration layer where necessary.

---

# Development Phase 3 — Home Assistant Integration

Once the independent read-only core works:

1. implement config flow
2. implement coordinator
3. expose read-only entities
4. add diagnostics
5. package for HACS
6. validate with `hassfest`
7. validate with HACS action

The first HACS release should be monitor-only.

Suggested first release scope:

    v0.1.0
    - HACS installation
    - UI config flow
    - Sunny Island read-only monitoring
    - Sunny Home Manager passive listener
    - sensors
    - diagnostics
    - no active battery control

---

# Development Phase 4 — Safe Write Layer

Only after read-only functionality is verified against the physical SI4.4M-12 should write support be implemented in the core.

Write control must require explicit enablement.

The core could contain:

    ControllerSafetyConfig(
        allow_writes=False,
        min_soc=...,
        max_soc=...,
        command_timeout=...,
    )

The Home Assistant integration should require an explicit opt-in before write functionality appears or activates.

Monitor-only must remain the default.

---

# Fail-Safe Behavior

Investigate and document the Sunny Island's behavior when external Modbus commands stop.

Critical questions:

- Are power limits persistent?
- Do they expire?
- Is there a watchdog?
- Is there an explicit "external control enable" state?
- What happens after Sunny Island reboot?
- What happens after controller reboot?
- What happens when Modbus TCP disappears?

Do not enable active control until these are verified.

The design goal is:

    controller failure
          ↓
    battery returns to documented safe/normal SMA behavior

not:

    controller failure
          ↓
    stale external command remains indefinitely

If the device does not provide safe automatic fallback, implement an alternative conservative strategy and document its limitations prominently.

---

# Control Objective

First useful mode:

## Delayed PV Charging

Example:

Morning:
- household consumes PV
- battery charging inhibited or limited
- discharge may remain enabled

Midday:
- charging permitted
- battery absorbs PV peak

Afternoon:
- normal self-consumption behavior

A fixed schedule can exist as a test mode.

Example:

    before 11:00:
        inhibit charging

    11:00–15:00:
        allow charging

    after 15:00:
        normal operation

This should not be the final predictive algorithm.

---

# Final Goal — Predictive Charging

Inputs:

- battery SoC
- usable capacity
- remaining PV forecast
- expected remaining load
- current PV generation
- current grid power
- current time
- charge/discharge limits
- export limit if applicable
- minimum reserve
- forecast uncertainty

Conceptually:

    Battery capacity:               ~9.0 kWh
    Current SoC:                    35 %
    Free capacity:                  ~5.8 kWh

    Remaining PV forecast:          13.5 kWh
    Expected remaining load:         6.0 kWh
    Expected surplus:                7.5 kWh

The controller should preserve sufficient battery headroom to absorb expected later surplus.

The target is not:

    "charge at 11:00"

but:

    "maintain enough empty capacity to absorb expected future PV while still reaching the required end-of-day SoC."

---

# Forecast Abstraction

Keep forecasting independent of Home Assistant and independent of any specific provider.

Example:

    class ForecastProvider(Protocol):
        async def get_forecast(self) -> PVForecast:
            ...

Potential providers:

- Home Assistant weather/solar entities
- Open-Meteo
- Forecast.Solar
- local forecast model
- historical PV model

A Home Assistant adapter may translate HA entity states into the generic forecast interface.

The controller core must not import Home Assistant to use forecasts.

---

# Home Assistant Forecast Adapters

The HA integration may later let the user select:

- existing forecast entity
- weather entity
- PV forecast integration
- manually configured forecast source

This lets the project reuse data already available in Home Assistant without coupling the core to those integrations.

---

# Home Assistant Automation Compatibility

Expose enough entities that users can initially experiment with Home Assistant automations without enabling the internal predictive controller.

For example:

- battery SoC sensor
- grid power sensor
- control mode select
- charge inhibition switch
- manual charge limit number

However, critical validation and safety checks must still live in the integration/core, not in arbitrary user automations.

---

# Logging and History

The core should expose structured state and control events.

Home Assistant already provides Recorder/history, so avoid unnecessary duplicate persistence for standard sensors.

For controller debugging, optionally retain a lightweight ring buffer or structured log containing:

- timestamp
- battery SoC
- battery power
- grid power
- PV power
- forecast
- requested limits
- actual mode
- safety decision
- communication errors

Diagnostics should be able to expose a sanitized recent subset.

---

# Testing Strategy

## Core tests

Unit test:

- SMA U16/S16/U32/S32 decoding
- sentinel handling
- scaling
- register parsing
- device identification
- state construction
- stale-data handling
- safety rules
- control policy

Mock Modbus transport.

No test should require a physical Sunny Island.

## Home Assistant tests

Use Home Assistant pytest fixtures.

Test:

- config flow success
- config flow connection failure
- unsupported device
- entity creation
- coordinator updates
- unavailable state
- reload
- options flow
- diagnostics redaction

Later test write mode separately and conservatively.

---

# CI Requirements

GitHub Actions should run:

- Python tests
- linting
- type checking if practical
- Home Assistant `hassfest`
- HACS validation

Prefer standard Home Assistant custom-integration tooling and conventions.

---

# Release Strategy

Recommended stages:

## v0.1.x

Monitor-only:
- HACS install
- config flow
- Sunny Island read
- Home Manager local listener
- sensors
- diagnostics

## v0.2.x

Manual control, explicitly opt-in:
- verified external power-limit writes
- safety layer
- restore-normal service
- manual control entities

## v0.3.x

Scheduled delayed charging:
- time-window policy
- configurable reserve

## v0.4.x

Predictive charging:
- forecast abstraction
- Home Assistant forecast adapter
- headroom optimization

Do not combine all of these into the first release.

---

# Immediate Task for Codex

Start with the monitor-only HACS integration and independent Python core.

Please:

1. Verify official SMA Modbus documentation applicable to the SI4.4M-12.
2. Verify all register addresses before coding them.
3. Create the repository skeleton as a HACS-compatible custom integration.
4. Create an independent `sma_local` Python core package.
5. Implement typed SMA register definitions and decoding.
6. Implement a read-only asynchronous Sunny Island Modbus client.
7. Add a reusable `SunnyIslandState` model.
8. Add an optional standalone CLI using the same core library.
9. Implement Home Assistant config flow.
10. Validate the configured Sunny Island by reading device identity.
11. Implement a Home Assistant coordinator.
12. Add initial read-only sensors.
13. Add diagnostics.
14. Add `hacs.json`.
15. Add HACS and `hassfest` GitHub Actions.
16. Add core and Home Assistant tests.
17. Do not implement any active Modbus writes yet.

The first milestone is complete when:

- the repository can be installed through HACS,
- the integration can be configured through the Home Assistant UI,
- it connects locally to the SI4.4M-12,
- it exposes correct read-only battery state,
- the same protocol library can run independently of Home Assistant,
- and there is no active battery-control code path enabled.

---

# Current implementation status (2026-09-04)

Update (2026-09-05): the [production readiness handover](docs/knowledge/production-handover.md)
supersedes the remaining-work list below. It records the production review,
passive detection improvements, and the required order of software and physical
commissioning gates. Physical commissioning is not the only remaining blocker.

The repository has progressed beyond the original monitor-only skeleton. It is
now `powermanager`, with a reusable core under
`custom_components/powermanager/core/powermanager_core` and a HACS-compatible
Home Assistant integration under `custom_components/powermanager`.

Implemented and tested:

- UV-managed project (Python 3.12) with GitHub and Forgejo workflows.
- Read-only SMA Sunny Island Modbus TCP backend and normalized battery models.
- Home Assistant config/options flow, coordinator, sensors, diagnostics, and
  optional HA providers for grid/PV/load and market price.
- Passive Speedwire listener and unicast relay tooling.
- Declarative YAML rules, deterministic policy evaluation, safety validation,
  hold/cooldown handling, simulation runtime, and watchdog.
- Guarded Sunny Island command adapter for the documented control/fallback
  registers, cyclic heartbeat, bounded duration, and restore-normal operation.
- Passive Speedwire ownership warning for non-Sunny-Island senders.
- Rule validation and a read-only CLI commissioning preflight.

The live installation at `10.0.1.240` was queried read-only. It identified as
SI4.4M-12 (`9332`), in parallel-grid operation, with a 30% dynamic discharge
floor. External setpoint mode is configured (`40210=1079`), fallback behavior is
apply-fallback (`41193=2507`), timeout is 300 seconds, and fallback maximum
power is 6000 W. The commissioning preflight passed. No write has ever been
sent by PowerManager.

## Safety boundary and remaining blockers

Production control is still disabled. The write adapter is not connected to the
Home Assistant coordinator or an automatic control loop. The Speedwire warning
is conservative: any non-Sunny-Island sender may be a Home Manager or another
SMA device and must be treated as a possible competing controller.

Before enabling a live setpoint:

1. Confirm whether the Sunny Home Manager currently owns active-power control.
2. Confirm single-phase or three-phase single-cluster topology; multicluster
   Modbus setpoint control is not supported by the SMA documentation.
3. Confirm a physical emergency-stop procedure and supervised test window.
4. Record the original operating mode and fallback settings.
5. Test a small bounded setpoint, heartbeat loss, TCP disconnect, process exit,
   inverter restart, fallback behavior, and restore-normal operation.
6. Decide whether the current 300-second timeout is acceptable; any change must
   be deliberate and verified on the device.

After commissioning, wire the production actuator into the control runtime and
add explicit Home Assistant ownership confirmation, control UI, and services.
Separate follow-up work includes full Speedwire `0x6069` decoding, HA fixture
tests and hassfest validation, tariff-unit normalization, forecast providers,
and additional battery/meter backends.

## Handoff instructions

Run `uv sync --extra sma --extra dev`, then `uv run pytest` and
`uv run ruff check .`. Use `uv run powermanager commission --host 10.0.1.240`
for a read-only preflight. Do not add a live-write command or enable the adapter
without resolving the blockers above and documenting observed recovery behavior.
