from pathlib import Path

import pytest
from powermanager_core.control import load_rules


def test_load_rules_rejects_enabled_document(tmp_path: Path) -> None:
    path = tmp_path / "rules.yaml"
    path.write_text("version: 1\nenabled: true\nrules: []\n", encoding="utf-8")
    with pytest.raises(ValueError, match="disabled"):
        load_rules(path)


def test_load_rules_parses_typed_rule(tmp_path: Path) -> None:
    path = tmp_path / "rules.yaml"
    path.write_text(
        "version: 1\nenabled: false\nrules:\n"
        "  - id: surplus\n    priority: 10\n"
        "    when: {grid_power_below_w: -500, between: ['09:00', '16:00']}\n"
        "    then: {target_power_w: 1500}\n    hold_seconds: 300\n",
        encoding="utf-8",
    )
    rule = load_rules(path)[0]
    assert rule.rule_id == "surplus"
    assert rule.conditions.grid_power_below_w == -500
    assert rule.target_power_w == 1500
