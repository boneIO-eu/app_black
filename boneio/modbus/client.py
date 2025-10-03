from __future__ import annotations

import asyncio
import logging
import struct
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Any

from pymodbus.client import ModbusSerialClient
from pymodbus.exceptions import ModbusException
from pymodbus.framer import Endian
from pymodbus.payload import BinaryPayloadDecoder
from pymodbus.pdu import ModbusResponse

from boneio.const import ID, REGISTERS, RX, TX, UART
from boneio.helper import configure_pin
from boneio.helper.exceptions import ModbusUartException

_LOGGER = logging.getLogger(__name__)

VALUE_TYPES = {
    "U_WORD": {
        "f": "decode_16bit_uint",
        "byteorder": Endian.Big,
        "count": 1,
    },
    "S_WORD": {
        "f": "decode_16bit_int",
        "byteorder": Endian.Big,
        "count": 1,
    },
    "U_DWORD": {
        "f": "decode_32bit_uint",
        "byteorder": Endian.Big,
        "count": 2,
    },
    "S_DWORD": {
        "f": "decode_32bit_int",
        "byteorder": Endian.Big,
        "count": 2,
    },
    "U_DWORD_R": {
        "f": "decode_32bit_uint",
        "byteorder": Endian.Little,
        "count": 2,
    },
    "S_DWORD_R": {
        "f": "decode_32bit_int",
        "byteorder": Endian.Little,
        "count": 2,
    },
    "U_QWORD": {
        "f": "decode_64bit_uint",
        "byteorder": Endian.Big,
        "count": 4,
    },
    "S_QWORD": {
        "f": "decode_64bit_int",
        "byteorder": Endian.Big,
        "count": 4,
    },
    "U_QWORD_R": {
        "f": "decode_64bit_uint",
        "byteorder": Endian.Little,
        "count": 4,
    },
    "FP32": {
        "f": "decode_32bit_float",
        "byteorder": Endian.Big,
        "count": 2,
    },
    "FP32_R": {
        "f": "decode_32bit_float",
        "byteorder": Endian.Little,
        "count": 2,
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
        configure_pin(pin=rx, mode=UART)
        configure_pin(pin=tx, mode=UART)
        self._uart = uart

        # generic configuration
        self._client: ModbusSerialClient | None = None
        self._loop = asyncio.get_event_loop()
        self._lock = asyncio.Lock()
        self._executor = ThreadPoolExecutor(max_workers=MAX_WORKERS, thread_name_prefix="modbus_worker")

        try:
            self._client = ModbusSerialClient(
                port=self._uart[ID],
                method="rtu",
                baudrate=baudrate,
                stopbits=stopbits,
                bytesize=bytesize,
                parity=parity,
                timeout=timeout,
            )
            self._read_methods = {
                "input": self._client.read_input_registers,
                "holding": self._client.read_holding_registers,
                "coil": self._client.read_coils,
            }
        except ModbusException as exception_error:
            _LOGGER.error(exception_error)

    @property
    def client(self) -> ModbusSerialClient | None:
        """Return client."""
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
        """Connect client."""
        try:
            return self._client.connect()  # type: ignore[union-attr]
        except ModbusException as exception_error:
            _LOGGER.error(f"No connection to Modbus: {exception_error}")
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
        if not result or result.isError():
            return None
        decoded_value = self.decode_value(
            payload=result.registers, value_type=payload_type
        )
        return decoded_value

    def read_registers_blocking(self, unit: int | str, address: int, count: int = 2, method: str = "input") -> ModbusResponse:
        start_time = time.perf_counter()
        result = None
        kwargs = {"unit": unit, "count": count} if unit else {}
        read_method = self._read_methods[method]
        
        try:
            # Run connection in the executor
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

            # Run the read operation in the executor
            result = read_method(address, **kwargs)

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
                result.registers if hasattr(result, REGISTERS) else None,
            )
            return result

    def write_register_blocking(self, unit: int | str, address: int, value: int | float) -> ModbusResponse:
        """Call async pymodbus."""
        start_time = time.perf_counter()
        result = None
        try:
            # Run connection in the executor
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

            # Run the read operation in the executor
            result = self._client.write_register(address=address, value=value, unit=unit)

            if result.isError():
                _LOGGER.error("Operation failed.")
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
    ) -> ModbusResponse:
        """Call async pymodbus."""
        async with self._lock:
            return await self._loop.run_in_executor(self._executor, self.read_registers_blocking, unit, address, count, method)
            

    def decode_value(self, payload, value_type):
        _payload_type = VALUE_TYPES[value_type]
        decoder = BinaryPayloadDecoder.fromRegisters(
            registers=payload, byteorder=_payload_type["byteorder"]
        )
        value = getattr(decoder, _payload_type["f"])()
        return value

    async def write_register(self, unit: int | str, address: int, value: int | float) -> ModbusResponse:
        """Call async pymodbus."""
        async with self._lock:
            return await self._loop.run_in_executor(self._executor, self.write_register_blocking, unit, address, value)
