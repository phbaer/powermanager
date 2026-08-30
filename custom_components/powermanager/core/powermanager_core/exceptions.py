"""Domain-specific exceptions for backend implementations."""


class PowerManagerError(Exception):
    """Base exception for expected PowerManager failures."""


class BackendConnectionError(PowerManagerError):
    """The device could not be reached or returned a protocol error."""


class UnsupportedDeviceError(PowerManagerError):
    """The discovered device is not a supported backend target."""


class RegisterDecodeError(PowerManagerError):
    """A register value cannot be decoded according to its definition."""
