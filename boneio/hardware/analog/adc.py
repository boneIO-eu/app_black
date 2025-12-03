"""ADC (Analog-to-Digital Converter) sensor driver for BeagleBone Black.

This module provides support for reading analog values from BeagleBone Black's
ADC pins using the Linux IIO (Industrial I/O) subsystem instead of deprecated
Adafruit_BBIO library.

BeagleBone Black has 7 ADC pins (AIN0-AIN6) with 12-bit resolution (0-4095).
Input voltage range: 0-1.8V
"""

from __future__ import annotations

import logging
from pathlib import Path

from boneio.const import SENSOR
from boneio.core.messaging import BasicMqtt
from boneio.core.utils import AsyncUpdater, Filter

_LOGGER = logging.getLogger(name=__name__)

# IIO device path for BeagleBone Black ADC
IIO_DEVICE_PATH = Path("/sys/bus/iio/devices/iio:device0")

# ADC pin mapping (AIN0-AIN6)
ADC_PIN_MAP = {
    "AIN0": "in_voltage0_raw",
    "AIN1": "in_voltage1_raw",
    "AIN2": "in_voltage2_raw",
    "AIN3": "in_voltage3_raw",
    "AIN4": "in_voltage4_raw",
    "AIN5": "in_voltage5_raw",
    "AIN6": "in_voltage6_raw",
}


class ADCReader:
    """Low-level ADC reader using Linux IIO subsystem.
    
    This class provides direct access to BeagleBone Black's ADC through
    the IIO (Industrial I/O) subsystem. It replaces the deprecated
    Adafruit_BBIO.ADC module.
    
    Features:
    - 12-bit resolution (0-4095)
    - 0-1.8V input range
    - 7 analog input pins (AIN0-AIN6)
    
    Example:
        >>> adc = ADCReader()
        >>> value = adc.read("AIN0")  # Returns 0.0-1.0
        >>> raw = adc.read_raw("AIN0")  # Returns 0-4095
    """
    
    def __init__(self):
        """Initialize ADC reader."""
        self._initialized = False
        self._check_iio_device()
    
    def _check_iio_device(self):
        """Check if IIO device is available."""
        if not IIO_DEVICE_PATH.exists():
            _LOGGER.warning(
                "IIO device not found at %s. ADC may not be available.",
                IIO_DEVICE_PATH
            )
        else:
            self._initialized = True
            _LOGGER.debug("IIO ADC device found at %s", IIO_DEVICE_PATH)
    
    def read_raw(self, pin: str) -> int:
        """Read raw ADC value (0-4095).
        
        Args:
            pin: Pin name (e.g., "AIN0", "AIN1", etc.)
            
        Returns:
            Raw ADC value (0-4095)
            
        Raises:
            ValueError: If pin name is invalid
            RuntimeError: If ADC is not available
        """
        if not self._initialized:
            raise RuntimeError("ADC not available. Check IIO device.")
        
        if pin not in ADC_PIN_MAP:
            raise ValueError(
                f"Invalid ADC pin: {pin}. Valid pins: {list(ADC_PIN_MAP.keys())}"
            )
        
        iio_file = ADC_PIN_MAP[pin]
        value_path = IIO_DEVICE_PATH / iio_file
        
        try:
            with open(value_path, 'r') as f:
                raw_value = int(f.read().strip())
            _LOGGER.debug("Read ADC %s: %d", pin, raw_value)
            return raw_value
        except (IOError, ValueError) as err:
            _LOGGER.error("Error reading ADC pin %s: %s", pin, err)
            return 0
    
    def read(self, pin: str) -> float:
        """Read normalized ADC value (0.0-1.0).
        
        Args:
            pin: Pin name (e.g., "AIN0", "AIN1", etc.)
            
        Returns:
            Normalized value (0.0-1.0)
        """
        raw_value = self.read_raw(pin)
        return raw_value / 4095.0  # 12-bit ADC
    
    def read_voltage(self, pin: str) -> float:
        """Read voltage value (0.0-1.8V).
        
        Args:
            pin: Pin name (e.g., "AIN0", "AIN1", etc.)
            
        Returns:
            Voltage value (0.0-1.8V)
        """
        normalized = self.read(pin)
        return normalized * 1.8  # 1.8V reference


# Global ADC reader instance
_adc_reader: ADCReader | None = None


def initialize_adc():
    """Initialize the global ADC reader.
    
    This function should be called once before using ADC sensors.
    It creates a global ADCReader instance.
    
    Note: For compatibility with old Adafruit_BBIO code.
    """
    global _adc_reader
    if _adc_reader is None:
        _adc_reader = ADCReader()
        _LOGGER.info("ADC initialized using IIO subsystem")


def get_adc_reader() -> ADCReader:
    """Get the global ADC reader instance.
    
    Returns:
        Global ADCReader instance
        
    Raises:
        RuntimeError: If ADC not initialized
    """
    if _adc_reader is None:
        raise RuntimeError("ADC not initialized. Call initialize_adc() first.")
    return _adc_reader


class GpioADCSensor(BasicMqtt, AsyncUpdater, Filter):
    """GPIO ADC sensor for BeagleBone Black.
    
    This sensor reads analog values from BeagleBone Black's ADC pins
    and publishes them to MQTT. It uses the Linux IIO subsystem instead
    of the deprecated Adafruit_BBIO library.
    
    Args:
        pin: ADC pin name (e.g., "AIN0", "AIN1", etc.)
        filters: List of filter expressions to apply to readings
        **kwargs: Additional arguments (name, id, manager, update_interval, etc.)
        
    Example:
        >>> sensor = GpioADCSensor(
        ...     pin="AIN0",
        ...     filters=['round(x, 3)', 'x * 1.8'],  # Convert to voltage
        ...     name="Battery Voltage",
        ...     id="battery_voltage",
        ...     manager=manager,
        ...     update_interval=TimePeriod(seconds=10)
        ... )
    """

    def __init__(self, pin: str, filters: list, **kwargs) -> None:
        """Initialize GPIO ADC sensor."""
        super().__init__(topic_type=SENSOR, **kwargs)
        self._pin = pin
        self._state = None
        self._filters = filters
        
        # Validate pin name
        if pin not in ADC_PIN_MAP:
            raise ValueError(
                f"Invalid ADC pin: {pin}. Valid pins: {list(ADC_PIN_MAP.keys())}"
            )
        
        AsyncUpdater.__init__(self, **kwargs)
        _LOGGER.info("Configured ADC sensor on pin %s", self._pin)

    @property
    def state(self) -> float | None:
        """Get current sensor state.
        
        Returns:
            Filtered ADC value or None
        """
        return self._state

    def update(self, timestamp: float) -> None:
        """Read ADC value and publish to MQTT.
        
        This method is called periodically by AsyncUpdater.
        
        Args:
            timestamp: Current timestamp
        """
        try:
            adc = get_adc_reader()
            raw_value = adc.read(self._pin)
            
            _LOGGER.debug("Read ADC %s: %f (before filters)", self._pin, raw_value)
            
            _state = self._apply_filters(value=raw_value)
            if _state is None:
                return
            
            self._state = _state
            self._timestamp = timestamp
            
            self._message_bus.send_message(
                topic=self._send_topic,
                payload=str(self.state),
            )
            
        except Exception as err:
            _LOGGER.error("Error updating ADC sensor %s: %s", self._pin, err)
