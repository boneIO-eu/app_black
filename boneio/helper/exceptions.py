"""BoneIO Errors"""


class BoneIOException(Exception):
    """BoneIO standard exception."""


class GPIOInputException(BoneIOException):
    """GPIOInput Exception."""


class GPIOOutputException(BoneIOException):
    """GPIOInput Exception."""


class I2CError(BoneIOException):
    """I2C Exception."""


class OneWireError(BoneIOException):
    """One Wire Exception."""


class ConfigurationException(BoneIOException):
    """Configuration yaml exception."""


class CoverRelayException(BoneIOException):
    """Cover configuration exception."""


class ModbusUartException(BoneIOException):
    """Cover configuration exception."""


class RestartRequestException(BoneIOException):
    """Restart exception."""
