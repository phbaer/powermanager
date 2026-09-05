import pytest
from powermanager_core.inverters import parse_inverter_sources


def test_parse_multiple_inverter_sources() -> None:
    sources = parse_inverter_sources(
        """
        inverters:
          - id: sunnyboy_main
            role: pv
            generation_power_entity: sensor.sunnyboy_power
            remaining_pv_forecast_entity: sensor.sunnyboy_forecast
          - id: third_party
            role: battery
            battery_power_entity: sensor.third_party_power
        """
    )

    assert [source.source_id for source in sources] == ["sunnyboy_main", "third_party"]
    assert sources[0].remaining_pv_forecast_entity == "sensor.sunnyboy_forecast"
    assert sources[1].battery_power_entity == "sensor.third_party_power"


@pytest.mark.parametrize(
    "document",
    [
        "inverters: [{id: SunnyBoy, generation_power_entity: sensor.pv}]",
        (
            "inverters: [{id: same, generation_power_entity: sensor.pv}, "
            "{id: same, battery_power_entity: sensor.x}]"
        ),
        "inverters: [{id: empty}]",
        "inverters: [{id: battery, role: battery}]",
        "inverters: [{id: battery, role: battery, battery_power_entity: sensor.battery, "
        "generation_power_entity: sensor.pv}]",
        "inverters: [{id: pv, role: pv, remaining_pv_forecast_entity: sensor.forecast}]",
    ],
)
def test_parse_inverter_sources_rejects_unsafe_or_incomplete_documents(document: str) -> None:
    with pytest.raises(ValueError):
        parse_inverter_sources(document)
