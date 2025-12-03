from __future__ import annotations

import asyncio
import logging
import struct
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Any

from pymodbus.client import ModbusSerialClient
from pymodbus.exceptions import ModbusException
from pymodbus.framer import FramerType
from pymodbus.pdu import ExceptionResponse

from boneio.const import ID, REGISTERS, RX, TX
from boneio.exceptions import ModbusUartException

_LOGGER = logging.getLogger(__name__)

VALUE_TYPES = {
    "U_WORD": {
        "format": "H",  # unsigned short
        "byteorder": ">",  # Big endian
        "count": 1,
        "size": 2,
    },
    "S_WORD": {
        "format": "h",  # signed short
        "byteorder": ">",  # Big endian
        "count": 1,
        "size": 2,
    },
    "U_DWORD": {
        "format": "I",  # unsigned int
        "byteorder": ">",  # Big endian
        "count": 2,
        "size": 4,
    },
    "S_DWORD": {
        "format": "i",  # signed int
        "byteorder": ">",  # Big endian
        "count": 2,
        "size": 4,
    },
    "U_DWORD_R": {
        "format": "I",  # unsigned int
        "byteorder": "<",  # Little endian
        "count": 2,
        "size": 4,
    },
    "S_DWORD_R": {
        "format": "i",  # signed int
        "byteorder": "<",  # Little endian
        "count": 2,
        "size": 4,
    },
    "U_QWORD": {
        "format": "Q",  # unsigned long long
        "byteorder": ">",  # Big endian
        "count": 4,
        "size": 8,
    },
    "S_QWORD": {
        "format": "q",  # signed long long
        "byteorder": ">",  # Big endian
        "count": 4,
        "size": 8,
    },
    "U_QWORD_R": {
        "format": "Q",  # unsigned long long
        "byteorder": "<",  # Little endian
        "count": 4,
        "size": 8,
    },
    "FP32": {
        "format": "f",  # float
        "byteorder": ">",  # Big endian
        "count": 2,
        "size": 4,
    },
    "FP32_R": {
        "format": "f",  # float
        "byteorder": "<",  # Little endian
        "count": 2,
        "size": 4,
    },
}

# Maximum number of worker threads for Modbus operations
MAX_WORKERS = 4
# Timeout for Modbus operations in seconds
OPERATION_TIMEOUT = 5


class Modbus:
    """Represent modbus connection over chosen UART."""

    def __init__(
        self,
        uart: dict[str, Any],
        baudrate: int = 9600,
        stopbits: int = 1,
        bytesize: int = 8,
        parity: str = "N",
        timeout: float = 3,
    ) -> None:
        """Initialize the Modbus hub."""
        rx = uart.get(RX)
        tx = uart.get(TX)
        if not tx or not rx:
            raise ModbusUartException
        _LOGGER.debug(
            f"Setting UART for modbus communication: {uart} with baudrate {baudrate}, parity {parity}, stopbits {stopbits}, bytesize {bytesize}",
        )
        self._uart = uart
        self._loop = asyncio.get_event_loop()
        self._lock = asyncio.Lock()
        self._executor = ThreadPoolExecutor(max_workers=MAX_WORKERS, thread_name_prefix="modbus_worker")

        _LOGGER.debug(f"Creating ModbusSerialClient for port: {self._uart[ID]}")
        self._client = ModbusSerialClient(
            port=self._uart[ID],
            framer=FramerType.RTU,
            baudrate=baudrate,
            stopbits=stopbits,
            bytesize=bytesize,
            parity=parity,
            timeout=timeout,
            retries=3,
        )
        _LOGGER.debug("ModbusSerialClient created successfully")

    @property
    def client(self) -> ModbusSerialClient | None:
        """Return client. May be None after async_close()."""
        return self._client

    async def async_close(self) -> None:
        """Disconnect client."""
        if self._client:
            try:
                # Run close in the executor
                await self._loop.run_in_executor(self._executor, self._client.close)
            except asyncio.CancelledError:
                _LOGGER.warning("modbus communication closed")
                pass
            except ModbusException as exception_error:
                _LOGGER.error(exception_error)
            finally:
                del self._client
                self._client = None
                self._executor.shutdown(wait=False)
                _LOGGER.warning("modbus communication closed")

    def _pymodbus_connect(self) -> bool:
        """Connect to Modbus device.
        
        This method ensures the client is ready and connected.
        Returns False if client was closed.
        """
        try:
            if not self._client:
                _LOGGER.error("Modbus client was closed")
                return False
            
            _LOGGER.debug(f"Attempting to connect to Modbus port: {self._uart[ID]}")
            _LOGGER.debug(f"Client state before connect: connected={self._client.connected}")
            
            # Check if already connected
            if self._client.connected:
                _LOGGER.debug("Modbus client already connected")
                return True
            
            # Try to connect (pymodbus 3.x handles this automatically on first request)
            # But we can call it explicitly to verify connection
            result = self._client.connect()
            
            _LOGGER.debug(f"Connect result: {result}, client.connected={self._client.connected}")
            
            if result:
                _LOGGER.debug("Modbus client connected successfully")
                return True
            else:
                _LOGGER.error(f"Failed to connect Modbus client to {self._uart[ID]}")
                _LOGGER.error("Possible causes: port doesn't exist, no permissions, port busy, or hardware issue")
                return False
                
        except ModbusException as exception_error:
            _LOGGER.error(f"ModbusException during connect: {exception_error}")
            return False
        except Exception as e:
            _LOGGER.error(f"Unexpected error during Modbus connect: {type(e).__name__}: {e}")
            import traceback
            _LOGGER.debug(f"Traceback: {traceback.format_exc()}")
            return False

    async def read_and_decode(
        self,
        unit: int | str,
        address: int,
        payload_type: str,
        count: int = 2,
        method: str = "input",
    ) -> float | None:
        """Call read_registers and decode."""
        result = await self.read_registers(
            unit=unit, address=address, count=count, method=method
        )
        if not result or isinstance(result, ExceptionResponse):
            return None
        if not hasattr(result, 'registers'):
            return None
        decoded_value = self.decode_value(
            payload=result.registers, value_type=payload_type
        )
        return decoded_value

    def read_registers_blocking(self, unit: int | str, address: int, count: int = 2, method: str = "input"):
        """Read registers blocking (synchronous)."""
        start_time = time.perf_counter()
        result = None
        
        try:
            # In pymodbus 3.x, connection is automatic
            connected = self._pymodbus_connect()
            if not connected:
                _LOGGER.error("Can't connect to Modbus.")
                return None

            _LOGGER.debug(
                "Reading %s registers from %s with method %s from device %s.",
                count,
                address,
                method,
                unit,
            )

            # Use direct client methods (pymodbus 3.10+ uses device_id instead of slave)
            # _pymodbus_connect() guarantees self._client is not None here
            assert self._client is not None
            kwargs = {"address": address, "count": count, "device_id": int(unit)}
            
            if method == "input":
                result = self._client.read_input_registers(**kwargs, no_response_expected=False)
            elif method == "holding":
                result = self._client.read_holding_registers(**kwargs, no_response_expected=False)
            elif method == "coil":
                result = self._client.read_coils(**kwargs, no_response_expected=False)
            else:
                _LOGGER.error(f"Unknown method: {method}")
                return None

            if not hasattr(result, REGISTERS):
                _LOGGER.error("No result from read: %s", str(result))
                result = None

        except ValueError as exception_error:
            _LOGGER.error("Error reading registers: %s", exception_error)
            pass
        except (ModbusException, struct.error) as exception_error:
            _LOGGER.error("Error reading registers: %s", exception_error)
            pass
        except TimeoutError:
            _LOGGER.error("Timeout reading registers from device %s", unit)
            pass
        except asyncio.CancelledError as err:
            _LOGGER.error("Operation cancelled reading registers from device %s with error %s", unit, err)
            pass
        except Exception as e:
            _LOGGER.error(f"Unexpected error reading registers: {type(e).__name__} - {e}")
            pass
        finally:
            end_time = time.perf_counter()
            _LOGGER.debug(
                "Read completed in %.3f seconds: %s",
                end_time - start_time,
                result.registers if result and hasattr(result, REGISTERS) else None,
            )
            return result

    def write_register_blocking(self, unit: int | str, address: int, value: int | float):
        """Write register blocking (synchronous)."""
        start_time = time.perf_counter()
        result = None
        try:
            # In pymodbus 3.x, connection is automatic
            connected = self._pymodbus_connect()
            if not connected:
                _LOGGER.error("Can't connect to Modbus.")
                return None

            _LOGGER.debug(
                "Writing register %s with value %s to device %s.",
                address,
                value,
                unit,
            )

            # Use device_id parameter (pymodbus 3.10+)
            # _pymodbus_connect() guarantees self._client is not None here
            assert self._client is not None
            result = self._client.write_register(address=address, value=int(value), device_id=int(unit))

            if isinstance(result, ExceptionResponse):
                _LOGGER.error(f"Operation failed: {result}")
                result = None

        except ValueError as exception_error:
            _LOGGER.error("ValueError: Error writing registers: %s", exception_error)
            pass
        except (ModbusException, struct.error) as exception_error:
            _LOGGER.error("ModbusException: Error writing registers: %s", exception_error)
            pass
        except TimeoutError:
            _LOGGER.error("Timeout writing registers to device %s", unit)
            pass
        except asyncio.CancelledError as err:
            _LOGGER.error("Operation cancelled writing registers to device %s with error %s", unit, err)
            pass
        except Exception as e:
            _LOGGER.error(f"Unexpected error writing registers: {type(e).__name__} - {e}")
            pass
        finally:
            end_time = time.perf_counter()
            _LOGGER.debug(
                "Write completed in %.3f seconds.",
                end_time - start_time,
            )
            return result

    async def read_registers(
        self,
        unit: int | str,  # device address
        address: int,  # modbus register address
        count: int = 2,  # number of registers to read
        method: str = "input",  # type of register: input, holding
    ):
        """Call async pymodbus."""
        async with self._lock:
            return await self._loop.run_in_executor(self._executor, self.read_registers_blocking, unit, address, count, method)
            

    def decode_value(self, payload, value_type):
        """Decode modbus registers to value using struct.
        
        Similar to Home Assistant's approach but with type conversion.
        HA reads raw registers and leaves decoding to sensors.
        We decode here for convenience.
        """
        _payload_type = VALUE_TYPES[value_type]
        
        # Convert registers (16-bit values) to bytes
        byte_list = []
        for register in payload:
            byte_list.append((register >> 8) & 0xFF)  # High byte
            byte_list.append(register & 0xFF)  # Low byte
        
        byte_string = bytes(byte_list)
        
        # Unpack using struct with appropriate format and byte order
        format_string = _payload_type["byteorder"] + _payload_type["format"]
        value = struct.unpack(format_string, byte_string[:_payload_type["size"]])[0]
        
        return value

    async def write_register(self, unit: int | str, address: int, value: int | float):
        """Write register async."""
        async with self._lock:
            return await self._loop.run_in_executor(self._executor, self.write_register_blocking, unit, address, value)
