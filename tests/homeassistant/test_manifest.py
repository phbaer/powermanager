"""Release metadata keeps clean Home Assistant installs self-contained."""

from __future__ import annotations

import json
from pathlib import Path


def test_manifest_declares_runtime_modbus_dependency() -> None:
    """The HACS archive must install the dependency used by the integration."""
    manifest_path = (
        Path(__file__).parents[2]
        / "custom_components"
        / "powermanager"
        / "manifest.json"
    )
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    assert "pymodbus==3.13.1" in manifest["requirements"]
    assert manifest["homeassistant"] == "2025.1.0"
