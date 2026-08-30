# PowerManager

PowerManager is an unofficial, fully local Home Assistant integration and reusable
Python core for monitoring home batteries. Its first backend targets an SMA Sunny
Island used in older Viessmann Vitocharge systems.

## Safety status

`0.1.0` is **monitor only**. It performs read-only Modbus requests and contains no
Modbus write operation or battery-control command. Active control will not be added
until the exact Sunny Island register semantics and controller-failure behaviour have
been verified on the supported hardware.

## Development

The core can be installed independently for development:

```bash
python -m pip install -e '.[sma,dev]'
pytest
powermanager status --host 192.168.1.50
```

The Home Assistant integration is located at `custom_components/powermanager` and is
packaged directly by the release workflows for HACS.

## Supported backend status

| Backend | Status |
| --- | --- |
| SMA Sunny Island Modbus TCP | Read-only identity validation; measurement register map pending hardware/documentation verification |
| SMA Sunny Home Manager / Speedwire | Planned passive telemetry provider |
| Active battery control | Not implemented |
