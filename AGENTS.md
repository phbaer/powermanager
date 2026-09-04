# PowerManager agent rules

## Project context

- Read `Handover_ Local Predictive Battery Control for Viessmann Vitocharge - SMA Sunny Island.md` before making architectural or hardware-control changes.
- Keep the reusable Python core independent of Home Assistant. Home Assistant code belongs under `custom_components/powermanager` and protocol logic belongs in the core.
- Use English for source code, documentation, commit messages, and user-facing text.
- Update the README and OKF documents when implementation status or safety boundaries change.

## Development workflow

- Use `uv` for environment and command management:
  - `uv sync --extra sma --extra dev`
  - `uv run pytest`
  - `uv run ruff check .`
- Run tests and Ruff after each implementation batch.
- Commit useful, coherent batches automatically as work progresses. Use a concise Conventional Commit message (for example, `feat(control): ...` or `docs: ...`).
- Keep the worktree clean after a completed batch. Do not rewrite or discard unrelated user changes.
- Prefer `rg` for repository searches and `apply_patch` for file edits.

## Safety and hardware rules

- Treat the Sunny Island as production hardware. Read-only checks and commissioning preflights are allowed; never send a live write implicitly.
- Active control must remain fail-closed and disabled by default.
- Any write path must require explicit enablement, confirmed control ownership, bounded power, fresh telemetry, watchdog/heartbeat handling, timeout fallback, and restore-normal behavior.
- Never race, spoof, suppress, or firewall Sunny Home Manager traffic as a control strategy. Detect possible competing senders and warn the user.
- Do not change inverter parameters or setpoints without explicit user authorization for that specific live operation and a documented rollback/emergency-stop procedure.
- Stop and request feedback when hardware topology, control ownership, firmware behavior, or emergency-stop capability is unknown.

## Validation and documentation

- Prefer pure, hardware-independent tests for policy, safety, decoding, and command encoding.
- Record live observations as dated, read-only commissioning notes; clearly distinguish documented facts, observed values, and assumptions.
- Do not claim full `hassfest` or hardware validation unless it has actually run or been observed.
- Preserve the monitor-only safety status in release metadata and documentation until physical commissioning is complete.
