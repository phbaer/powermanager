---
okf_version: "0.2"
title: PowerManager architecture and implementation
version: 0.1.0
description: Agent-readable documentation for the modular home battery monitor.
entries:
  - architecture.md
  - implementation.md
  - roadmap.md
  - control-plan.md
  - control-write-research.md
---

# PowerManager

This bundle documents the architecture, current implementation, and remaining
work for PowerManager. The Sunny Island battery backend is required; energy
telemetry providers are optional.

## Documents

- [Architecture](architecture.md) - Runtime layers and backend/provider boundaries.
- [Implementation](implementation.md) - What is implemented and how to operate it.
- [Roadmap](roadmap.md) - Open work and safety gates.
- [Control plan](control-plan.md) - Control infrastructure and declarative rules.
- [Control/write research](control-write-research.md) - Verified SMA register and fail-safe constraints.
