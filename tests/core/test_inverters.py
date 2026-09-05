import pytest
from powermanager_core.inverters import parse_inverter_sources


def test_parse_multiple_inverter_sources() -> None:
    sources = parse_inverter_sources(
        """
        inverters:
          - id: sunnyboy_main
            pv_power_entity: sensor.sunnyboy_power
            remaining_pv_forecast_entity: sensor.sunnyboy_forecast
          - id: third_party
            import_power_entity: sensor.third_party_import
            export_power_entity: sensor.third_party_export
        """
    )

    assert [source.source_id for source in sources] == ["sunnyboy_main", "third_party"]
    assert sources[0].remaining_pv_forecast_entity == "sensor.sunnyboy_forecast"
    assert sources[1].export_power_entity == "sensor.third_party_export"


@pytest.mark.parametrize(
    "document",
    [
        "inverters: [{id: SunnyBoy, pv_power_entity: sensor.pv}]",
        (
            "inverters: [{id: same, pv_power_entity: sensor.pv}, "
            "{id: same, export_power_entity: sensor.x}]"
        ),
        "inverters: [{id: empty}]",
    ],
)
def test_parse_inverter_sources_rejects_unsafe_or_incomplete_documents(document: str) -> None:
    with pytest.raises(ValueError):
        parse_inverter_sources(document)
