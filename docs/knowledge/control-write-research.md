---
type: Technical Note
title: Sunny Island control register and fail-safe research
description: Verified constraints for a future write adapter and Home Manager coexistence.
tags: [sma, modbus, control, safety]
status: verified-documentation
---

# Scope

This note records facts from SMA's *Communication via SMA Modbus interface*
manual for the SI4.4M-12 family. It is a design input, not authorization to
enable writes. Device firmware, wiring mode, and installer configuration must
still be checked on the actual installation.

## Direct Modbus setpoints

For a single or single-cluster system, SMA documents these write-only registers:

- `40149` — active-power setpoint in watts (`S32`, signed; positive discharge,
  negative charge).
- `40151` — active/reactive power control via communication (`802` active,
  `803` inactive).
- `44039` / `44041` — maximum/minimum active-power bounds as a percentage of
  nominal device power.

The operating mode must be set to external setpoint (`40210 = 1079`). In
parallel-grid operation, SMA says a new setpoint must be transmitted at least
every 500 ms or it may not be accepted. This is substantially faster than the
normal monitoring poll interval, so the future adapter needs a dedicated,
deadline-monitored command loop.

The current battery protection limit is dynamic. While remotely controlled the
controller must continuously read `31009` and refuse discharge at or below that
limit. The existing safety validator already models this rule.

## Inverter-side fail-safe behavior

The inverter exposes configuration registers for loss of the external command:

- `41195` — external-setpoint timeout (1–1800 seconds; SMA recommends 5–10 s in
  stand-alone mode).
- `41193` — fallback behavior: keep values (`2506`) or apply fallback values
  (`2507`).
- `44037` — fallback maximum active power, 0–10000 W.

Production configuration should use *apply fallback values*, with a conservative
fallback power selected for the installation. The adapter must refresh the
setpoint well inside the configured timeout, detect missed deadlines, stop
sending on any safety fault, and verify that the inverter returns to the normal
operating mode after expiry. The fallback setting itself must be read back and
reported before active control is allowed.

SMA also documents an important recovery detail: when setpoints stop in
`SelfConsOnly`/`SelfCsmpBackup`, the inverter may fully charge the battery after
the timeout. A restore-normal operation therefore needs an explicit, tested
transition rather than simply closing the TCP connection.

## Home Manager coexistence

The Sunny Island manual distinguishes direct Modbus power specification from
specification through an SMA Data Manager/Home Manager. Two controllers must
not independently write the same active-power path. The supported design choices
are:

1. **Monitor-only Home Manager:** keep Home Manager telemetry, but disable its
   time-control/grid-management setpoint functions and make PowerManager the
   sole setpoint owner.
2. **Monitor-only PowerManager:** leave Home Manager in charge and use this
   integration only for readouts and rule simulation.

There is no safe software workaround that can reliably “win” a race against
Home Manager writes. A future setup flow must require an explicit ownership
choice, show a warning when external setpoint mode is requested, and provide a
restore-normal action. Do not attempt to spoof or suppress Home Manager network
traffic.

## Required hardware validation before writes

Before implementing a write transport, capture (read-only) the following from
the target SI and record firmware/mode: `30053`, `30201`, `33003`, `31009`,
`40210`, `41193`, `41195`, `44037`, `44039`, and `44041`. Confirm whether the
installation is single-phase, three-phase single-cluster, or multicluster;
SMA explicitly excludes Modbus setpoints for multicluster systems.

Then validate, with a physical emergency stop available: bounded setpoint,
heartbeat loss, timeout fallback, TCP disconnect, inverter restart, and
restoration of the original operating mode. No production write should be
enabled until every case has an observed result.
