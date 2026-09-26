from __future__ import annotations

import asyncio
import logging
import struct
import threading
import time
from collections.abc import Hashable
from concurrent.futures import ThreadPoolExecutor
from contextlib import suppress
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
# Auto-resume timeout in seconds (safety net if frontend disconnects)
SUSPEND_AUTO_TIMEOUT = 300  # 5 minutes
#: Failure-tracker key for the serial port itself, as opposed to one register.
PORT_KEY = "port"


class FailureLog:
    """Report a repeating Modbus failure once loudly, then quietly.

    A device that stops answering fails the same read on every poll cycle.
    Logged at ERROR each time, that buried every other warning and error in
    the journal. The first failure after a period of success is a WARNING,
    repeats are INFO, and the first success after a failure is a WARNING
    again, so anyone reading at warning level sees the outage close as well
    as open.

    Keys are chosen by the caller. The client uses ``(unit, address)``: an
    exception response means the device did answer, so keying on the unit
    alone would flip between "failing" and "recovered" every cycle when one
    register is misconfigured and the rest are fine.
    """

    def __init__(self, logger: logging.Logger) -> None:
        """Initialize the tracker.

        Args:
            logger: Logger the messages are emitted on.
        """
        self._logger = logger
        self._failures: dict[Hashable, int] = {}
        # The blocking calls run on a thread pool; the asyncio lock serializes
        # them today, but this must not depend on it.
        self._lock = threading.Lock()

    def failed(self, key: Hashable, msg: str, *args: Any) -> None:
        """Record a failure and log it.

        Args:
            key: What failed, e.g. ``(unit, address)``.
            msg: Log message, %-style.
            *args: Arguments for ``msg``.
        """
        with self._lock:
            count = self._failures.get(key, 0) + 1
            self._failures[key] = count
        if count == 1:
            self._logger.warning(msg, *args)
        else:
            self._logger.info(msg + " (failed %d times in a row)", *args, count)

    def succeeded(self, key: Hashable, what: str) -> None:
        """Record a success; log the recovery if ``key`` was failing.

        Args:
            key: What succeeded, the same key passed to :meth:`failed`.
            what: Human-readable name of it for the recovery message.
        """
        with self._lock:
            count = self._failures.pop(key, 0)
        if count:
            self._logger.warning(
                "%s responding again after %d failed attempt(s)", what, count
            )


class Modbus:
    """Represent modbus connection over chosen UART."""

    def __init__(
        self,
        uart: dict[str, Any],
        baudrate: int = 9600,
        stopbits: int = 1,
        bytesize: int = 8,
        parity: str = "N",
        timeout: float = 1.5,
        inter_device_delay: int = 5,
    ) -> None:
        """Initialize the Modbus hub.

        Args:
            uart: UART configuration dict with RX/TX pins.
            baudrate: Serial baudrate (default 9600).
            stopbits: Number of stop bits (default 1).
            bytesize: Number of data bits (default 8).
            parity: Parity mode N/E/O (default N).
            timeout: Response timeout in seconds (default 1.5).
            inter_device_delay: Delay in ms between transactions (default 5).
                Helps with star topology wiring where signal reflections
                on branch stubs need time to settle.
        """
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
        # Suspend mechanism: when True, coordinator polling is skipped
        self._suspended = False
        self._suspend_timeout_handle: asyncio.TimerHandle | None = None
        # Clamp inter_device_delay to 0-200ms, timeout to 0.1-10s
        clamped_delay = max(0, min(200, inter_device_delay))
        if clamped_delay != inter_device_delay:
            _LOGGER.warning(
                "inter_device_delay %dms out of range (0-200), clamped to %dms",
                inter_device_delay,
                clamped_delay,
            )
        self._inter_device_delay = clamped_delay / 1000.0  # ms -> seconds
        clamped_timeout = max(0.1, min(10.0, timeout))
        if clamped_timeout != timeout:
            _LOGGER.warning(
                "timeout %.2fs out of range (0.1-10), clamped to %.2fs",
                timeout,
                clamped_timeout,
            )
        timeout = clamped_timeout
        self._executor = ThreadPoolExecutor(max_workers=MAX_WORKERS, thread_name_prefix="modbus_worker")
        self._failures = FailureLog(_LOGGER)

        _LOGGER.debug(f"Creating ModbusSerialClient for port: {self._uart[ID]}")
        # Calculate inter-character timeout based on baudrate (3.5 characters)
        # At 9600 baud: 1 char = 11 bits (start + 8 data + parity + stop) = ~1.15ms
        # 3.5 chars = ~4ms, we use slightly more for safety
        char_time_ms = (11 * 1000) / baudrate  # Time for 1 character in ms
        inter_char_timeout = (char_time_ms * 3.5) / 1000  # Convert to seconds

        self._client = ModbusSerialClient(
            port=self._uart[ID],
            framer=FramerType.RTU,
            baudrate=baudrate,
            stopbits=stopbits,
            bytesize=bytesize,
            parity=parity,
            timeout=timeout,
            retries=2,  # Reduced from 3 to speed up detection of offline devices
        )
        _LOGGER.debug(
            "ModbusSerialClient created successfully with timeout=%.2fs, retries=2, inter_device_delay=%dms",
            timeout,
            inter_device_delay,
        )

    @property
    def client(self) -> ModbusSerialClient | None:
        """Return client. May be None after async_close()."""
        return self._client

    @property
    def is_suspended(self) -> bool:
        """Return True if coordinator polling is suspended (Tools active)."""
        return self._suspended

    def suspend(self) -> None:
        """Suspend coordinator polling.

        Called when the Tools Modbus page is opened. Coordinators
        check ``is_suspended`` and skip their update cycle so they
        don't compete for the UART with manual read/write operations.

        An auto-resume timer is started as a safety net in case the
        frontend disconnects without calling ``resume()``.
        """
        if self._suspended:
            # Already suspended, just reset the timeout
            self._reset_suspend_timeout()
            return
        self._suspended = True
        self._reset_suspend_timeout()
        _LOGGER.info("Modbus coordinator polling suspended (Tools active)")

    def resume(self) -> None:
        """Resume coordinator polling.

        Called when the Tools Modbus page is closed or the user
        navigates away.
        """
        if not self._suspended:
            return
        self._suspended = False
        self._cancel_suspend_timeout()
        _LOGGER.info("Modbus coordinator polling resumed")

    def _reset_suspend_timeout(self) -> None:
        """Reset the auto-resume safety timer."""
        self._cancel_suspend_timeout()
        with suppress(RuntimeError):
            self._suspend_timeout_handle = self._loop.call_later(SUSPEND_AUTO_TIMEOUT, self._auto_resume)

    def _cancel_suspend_timeout(self) -> None:
        """Cancel the auto-resume safety timer."""
        if self._suspend_timeout_handle is not None:
            self._suspend_timeout_handle.cancel()
            self._suspend_timeout_handle = None

    def _auto_resume(self) -> None:
        """Auto-resume after timeout (safety net)."""
        if self._suspended:
            self._suspended = False
            self._suspend_timeout_handle = None
            _LOGGER.warning(
                "Modbus coordinator polling auto-resumed after %ds timeout",
                SUSPEND_AUTO_TIMEOUT,
            )

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

    def _pymodbus_connect(self, silent: bool = False) -> bool:
        """Connect to Modbus device.

        This method ensures the client is ready and connected.
        Returns False if client was closed.

        Args:
            silent: If True, suppress debug logging (useful for scanning)
        """
        try:
            if not self._client:
                if not silent:
                    self._failures.failed(PORT_KEY, "Modbus client was closed")
                return False

            # Check if already connected
            if self._client.connected:
                if not silent:
                    self._port_ok()
                return True

            # Try to connect (pymodbus 3.x handles this automatically on first request)
            result = self._client.connect()

            if result:
                if not silent:
                    _LOGGER.debug("Modbus client connected successfully")
                    self._port_ok()
                return True
            else:
                if not silent:
                    self._failures.failed(
                        PORT_KEY, "Failed to connect Modbus client to %s", self._uart[ID]
                    )
                return False

        except ModbusException as exception_error:
            if not silent:
                self._failures.failed(
                    PORT_KEY, "ModbusException during connect: %s", exception_error
                )
            return False
        except Exception as e:
            if not silent:
                self._failures.failed(
                    PORT_KEY,
                    "Unexpected error during Modbus connect: %s: %s",
                    type(e).__name__,
                    e,
                )
            return False

    def _port_ok(self) -> None:
        """Record that the serial port is usable again."""
        self._failures.succeeded(PORT_KEY, f"Modbus port {self._uart[ID]}")

    async def read_and_decode(
        self,
        unit: int | str,
        address: int,
        payload_type: str,
        count: int = 2,
        method: str = "input",
    ) -> float | None:
        """Call read_registers and decode."""
        result = await self.read_registers(unit=unit, address=address, count=count, method=method)
        if not result or isinstance(result, ExceptionResponse):
            return None
        if not hasattr(result, "registers"):
            return None
        decoded_value = self.decode_value(payload=result.registers, value_type=payload_type)
        return decoded_value

    def read_registers_blocking(self, unit: int | str, address: int, count: int = 2, method: str = "input"):
        """Read registers blocking (synchronous)."""
        start_time = time.perf_counter()
        result = None

        try:
            # In pymodbus 3.x, connection is automatic
            connected = self._pymodbus_connect()
            if not connected:
                # _pymodbus_connect() has already reported why, rate-limited.
                _LOGGER.debug("Can't connect to Modbus.")
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

            key = (str(unit), address)
            if not hasattr(result, REGISTERS):
                self._failures.failed(
                    key,
                    "No result from read for device %s at address %s: %s",
                    unit,
                    address,
                    str(result),
                )
                result = None
            elif isinstance(result, ExceptionResponse):
                # pymodbus 3.x gives ExceptionResponse an empty ``registers``,
                # so it passes the check above. It is still returned as before:
                # boneio.modbus.cli prints its exception code.
                self._failures.failed(
                    key,
                    "Device %s refused read at address %s: %s",
                    unit,
                    address,
                    result,
                )
            else:
                self._failures.succeeded(key, f"Modbus device {unit} at address {address}")

        except ValueError as exception_error:
            self._failures.failed(
                (str(unit), address),
                "Error reading registers from device %s at address %s: %s",
                unit,
                address,
                exception_error,
            )
        except (ModbusException, struct.error) as exception_error:
            self._failures.failed(
                (str(unit), address),
                "Error reading registers from device %s at address %s: %s",
                unit,
                address,
                exception_error,
            )
        except TimeoutError:
            self._failures.failed(
                (str(unit), address),
                "Timeout reading registers from device %s at address %s",
                unit,
                address,
            )
        except asyncio.CancelledError as err:
            _LOGGER.error("Operation cancelled reading registers from device %s at address %s: %s", unit, address, err)
        except Exception as e:
            self._failures.failed(
                (str(unit), address),
                "Unexpected error reading registers from device %s at address %s: %s - %s",
                unit,
                address,
                type(e).__name__,
                e,
            )
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
                # _pymodbus_connect() has already reported why, rate-limited.
                _LOGGER.debug("Can't connect to Modbus.")
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

            # Same key as reads: a holding register is usually both polled and
            # written, and a device that is down fails both.
            key = (str(unit), address)
            if isinstance(result, ExceptionResponse):
                self._failures.failed(
                    key,
                    "Write to device %s at address %s failed: %s",
                    unit,
                    address,
                    result,
                )
                result = None
            else:
                self._failures.succeeded(key, f"Modbus device {unit} at address {address}")

        except ValueError as exception_error:
            self._failures.failed(
                (str(unit), address),
                "ValueError: Error writing register %s on device %s: %s",
                address,
                unit,
                exception_error,
            )
        except (ModbusException, struct.error) as exception_error:
            self._failures.failed(
                (str(unit), address),
                "ModbusException: Error writing register %s on device %s: %s",
                address,
                unit,
                exception_error,
            )
        except TimeoutError:
            self._failures.failed(
                (str(unit), address),
                "Timeout writing register %s to device %s",
                address,
                unit,
            )
        except asyncio.CancelledError as err:
            _LOGGER.error("Operation cancelled writing registers to device %s with error %s", unit, err)
        except Exception as e:
            self._failures.failed(
                (str(unit), address),
                "Unexpected error writing register %s on device %s: %s - %s",
                address,
                unit,
                type(e).__name__,
                e,
            )
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
        """Call async pymodbus.

        Returns None immediately when suspended (Tools active) so that
        coordinators treat the cycle as a no-response and retry later.
        """
        if self._suspended:
            return None
        async with self._lock:
            result = await self._loop.run_in_executor(
                self._executor, self.read_registers_blocking, unit, address, count, method
            )
            if self._inter_device_delay > 0:
                await asyncio.sleep(self._inter_device_delay)
            return result

    async def read_registers_direct(
        self,
        unit: int | str,
        address: int,
        count: int = 2,
        method: str = "input",
    ):
        """Read registers bypassing the suspend check.

        Used by Tools API for manual reads while coordinators are
        suspended.  Still acquires the UART lock to serialize access.
        """
        async with self._lock:
            result = await self._loop.run_in_executor(
                self._executor,
                self.read_registers_blocking,
                unit,
                address,
                count,
                method,
            )
            if self._inter_device_delay > 0:
                await asyncio.sleep(self._inter_device_delay)
            return result

    def scan_device_blocking(self, unit: int, address: int = 1, method: str = "input", timeout: float = 0.3) -> bool:
        """Quick scan to check if device exists at address.

        Uses short timeout and no retries for fast scanning.

        Args:
            unit: Device address to scan
            address: Register address to read
            method: Register type (input/holding)
            timeout: Timeout in seconds (default 0.3s)

        Returns:
            True if device responds, False otherwise
        """
        if self._client is None:
            return False

        # Save original settings
        original_timeout = self._client.comm_params.timeout_connect
        original_retries = self._client.retries

        try:
            # Set fast scan settings
            self._client.comm_params.timeout_connect = timeout
            self._client.retries = 0

            # Ensure connected (silent mode - no logging during scan)
            if not self._pymodbus_connect(silent=True):
                return False

            # Try to read one register
            kwargs = {"address": address, "count": 1, "device_id": int(unit)}

            if method == "input":
                result = self._client.read_input_registers(**kwargs, no_response_expected=False)
            else:
                result = self._client.read_holding_registers(**kwargs, no_response_expected=False)

            # Check if we got a valid response
            return result is not None and hasattr(result, REGISTERS)

        except Exception:
            return False
        finally:
            # Restore original settings
            self._client.comm_params.timeout_connect = original_timeout
            self._client.retries = original_retries

    async def scan_device(self, unit: int, address: int = 1, method: str = "input", timeout: float = 0.3) -> bool:
        """Async wrapper for scan_device_blocking."""
        async with self._lock:
            return await self._loop.run_in_executor(
                self._executor, self.scan_device_blocking, unit, address, method, timeout
            )

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
        value = struct.unpack(format_string, byte_string[: _payload_type["size"]])[0]

        return value

    async def write_register(self, unit: int | str, address: int, value: int | float):
        """Write register async.

        Returns None immediately when suspended.
        """
        if self._suspended:
            return None
        async with self._lock:
            result = await self._loop.run_in_executor(
                self._executor, self.write_register_blocking, unit, address, value
            )
            if self._inter_device_delay > 0:
                await asyncio.sleep(self._inter_device_delay)
            return result

    async def write_register_direct(self, unit: int | str, address: int, value: int | float):
        """Write register bypassing the suspend check.

        Used by Tools API for manual writes while coordinators are
        suspended.  Still acquires the UART lock to serialize access.
        """
        async with self._lock:
            result = await self._loop.run_in_executor(
                self._executor,
                self.write_register_blocking,
                unit,
                address,
                value,
            )
            if self._inter_device_delay > 0:
                await asyncio.sleep(self._inter_device_delay)
            return result

    def write_registers_blocking(self, unit: int | str, address: int, values: list[int]):
        """Write multiple registers blocking (synchronous) - FC16.

        Sends a Modbus FC16 (Write Multiple Registers) request to write
        a list of 16-bit values starting at the given register address.

        Args:
            unit: Device address (1-247).
            address: Starting register address.
            values: List of 16-bit integer values to write.

        Returns:
            Pymodbus response object on success, None on failure.
        """
        start_time = time.perf_counter()
        result = None
        try:
            connected = self._pymodbus_connect()
            if not connected:
                # _pymodbus_connect() has already reported why, rate-limited.
                _LOGGER.debug("Can't connect to Modbus.")
                return None

            _LOGGER.debug(
                "Writing %d registers starting at %s with values %s to device %s (FC16).",
                len(values),
                address,
                values,
                unit,
            )

            assert self._client is not None
            result = self._client.write_registers(
                address=address, values=values, device_id=int(unit)
            )

            key = (str(unit), address)
            if isinstance(result, ExceptionResponse):
                self._failures.failed(
                    key,
                    "FC16 write to device %s at address %s failed: %s",
                    unit,
                    address,
                    result,
                )
                result = None
            else:
                self._failures.succeeded(key, f"Modbus device {unit} at address {address}")

        except ValueError as exception_error:
            self._failures.failed(
                (str(unit), address),
                "ValueError: Error writing multiple registers at %s on device %s: %s",
                address,
                unit,
                exception_error,
            )
        except (ModbusException, struct.error) as exception_error:
            self._failures.failed(
                (str(unit), address),
                "ModbusException: Error writing multiple registers at %s on device %s: %s",
                address,
                unit,
                exception_error,
            )
        except TimeoutError:
            self._failures.failed(
                (str(unit), address),
                "Timeout writing multiple registers at %s to device %s",
                address,
                unit,
            )
        except asyncio.CancelledError as err:
            _LOGGER.error("Operation cancelled writing multiple registers to device %s: %s", unit, err)
        except Exception as e:
            self._failures.failed(
                (str(unit), address),
                "Unexpected error writing multiple registers at %s on device %s: %s - %s",
                address,
                unit,
                type(e).__name__,
                e,
            )
        finally:
            end_time = time.perf_counter()
            _LOGGER.debug(
                "FC16 write completed in %.3f seconds.",
                end_time - start_time,
            )
        return result

    async def write_registers(self, unit: int | str, address: int, values: list[int]):
        """Write multiple registers async (FC16).

        Returns None immediately when suspended.

        Args:
            unit: Device address (1-247).
            address: Starting register address.
            values: List of 16-bit integer values to write.
        """
        if self._suspended:
            return None
        async with self._lock:
            result = await self._loop.run_in_executor(
                self._executor, self.write_registers_blocking, unit, address, values
            )
            if self._inter_device_delay > 0:
                await asyncio.sleep(self._inter_device_delay)
            return result

    async def write_registers_direct(self, unit: int | str, address: int, values: list[int]):
        """Write multiple registers bypassing the suspend check (FC16).

        Used by Tools API for manual writes while coordinators are
        suspended.  Still acquires the UART lock to serialize access.

        Args:
            unit: Device address (1-247).
            address: Starting register address.
            values: List of 16-bit integer values to write.
        """
        async with self._lock:
            result = await self._loop.run_in_executor(
                self._executor,
                self.write_registers_blocking,
                unit,
                address,
                values,
            )
            if self._inter_device_delay > 0:
                await asyncio.sleep(self._inter_device_delay)
            return result
