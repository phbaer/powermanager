---
type: Commissioning record
title: Sunny Island supervised commissioning record
description: Evidence template for authorized read-only and live commissioning steps.
tags: [commissioning, sma, safety, handover]
status: template
---

# Scope and authorization

Complete this record for the target installation. This template does not
authorize inverter writes. Each live step requires separate operator approval,
a defined rollback, and a physically available emergency stop.

| Field | Value |
| --- | --- |
| Date/time and timezone | |
| Operator and reviewer | |
| Home Assistant/controller version | |
| Sunny Island model and serial | |
| Firmware (primary/secondary) | |
| Network path and Modbus unit ID | |
| Topology (single, three-phase, multicluster) | |
| Active-power owner before test | |
| Emergency stop and rollback procedure | |

Stop if topology, firmware behavior, active ownership, or emergency-stop access
is unknown. Multicluster operation is not an approved target for the direct
Modbus setpoint path.

# Read-only preflight

Record the value, timestamp, source, and interpretation. Re-read immediately
before any authorized live step.

| Register | Value | Timestamp | Interpretation |
| ---: | ---: | --- | --- |
| 30053 device type | | | |
| 30057 serial | | | |
| 30061 firmware | | | |
| 30063 secondary firmware | | | |
| 30201 operating state | | | |
| 33003 operating mode/topology | | | |
| 31009 dynamic discharge floor | | | |
| 40210 external-setpoint mode | | | |
| 41193 fallback behavior | | | |
| 41195 command timeout | | | |
| 44037 fallback power | | | |
| 44039/44041 power bounds | | | |

Confirm that Home Manager and every other possible sender are either the
documented owner or explicitly disabled for the tested setpoint path. A quiet
Speedwire listener is not proof of exclusive ownership.

# Authorized test sequence

Do not continue after a failed step. Record the exact command, approval, start
and end time, observed inverter state, and rollback result.

1. **Baseline capture:** read and record operating mode, communication control,
   fallback behavior, timeout, fallback power, and power bounds.
2. **Small bounded setpoint:** issue only the approved minimum test target for
   the approved duration. Confirm sign, scaling, limit enforcement, and that
   the expected owner accepts the command.
3. **Normal stop:** stop the heartbeat and verify the configured fallback and
   explicit restore-normal transition.
4. **Heartbeat loss:** terminate heartbeat delivery and measure fallback time
   and resulting operating state.
5. **TCP disconnect:** disconnect the controller transport and confirm the same
   safe fallback without relying on process cleanup.
6. **Controller termination/restart:** terminate and restart the controller;
   confirm no old session resumes automatically and that the inverter remains
   in the approved safe state.
7. **Home Assistant restart:** restart HA under supervision and confirm the
   integration returns monitor-only with no command resumption.
8. **Inverter restart:** only if separately approved, restart the inverter and
   repeat read-only identity, state, fallback, and ownership checks.

| Step | Approval reference | Expected result | Observed result/time | Rollback result | Pass/stop |
| --- | --- | --- | --- | --- | --- |
| Baseline capture | | | | | |
| Small setpoint | | | | | |
| Normal stop | | | | | |
| Heartbeat loss | | | | | |
| TCP disconnect | | | | | |
| Controller restart | | | | | |
| Home Assistant restart | | | | | |
| Inverter restart | | | | | |

# Acceptance and follow-up

Attach read-only traces, controller logs, timestamps, and operator sign-off.
Separate documented SMA expectations from observed installation behavior. Keep
the release metadata and Home Assistant integration in `monitor_only` until all
required steps pass and the owner explicitly approves the next control stage.
