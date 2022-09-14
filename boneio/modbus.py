from __future__ import annotations

import asyncio
import logging
from typing import Any

from pymodbus.client.sync import BaseModbusClient, ModbusSerialClient
from pymodbus.constants import Endian
from pymodbus.exceptions import ModbusException
from pymodbus.payload import BinaryPayloadDecoder
from pymodbus.pdu import ModbusResponse
from pymodbus.register_read_message import ReadInputRegistersResponse

from boneio.const import ID, REGISTERS, RX, TX, UART
from boneio.helper import configure_pin
from boneio.helper.exceptions import ModbusUartException

_LOGGER = logging.getLogger(__name__)


class Modbus:
    """Represent modbus connection over chosen UART."""

    def __init__(self, uart: dict[str, Any]) -> None:
        """Initialize the Modbus hub."""
        rx = uart.get(RX)
        tx = uart.get(TX)
        if not tx or not rx:
            raise ModbusUartException

        configure_pin(pin=rx, mode=UART)
        configure_pin(pin=tx, mode=UART)
        self._uart = uart

        # generic configuration
        self._client: BaseModbusClient | None = None
        self._lock = asyncio.Lock()
        try:
            self._client = ModbusSerialClient(
                port=self._uart[ID],
                method="rtu",
                baudrate=9600,
                stopbits=1,
                bytesize=8,
                parity="N",
            )
            self._read_methods = {
                "input": self._client.read_input_registers,
                "holding": self._client.read_holding_registers,
            }
        except ModbusException as exception_error:
            _LOGGER.error(exception_error)

    async def async_close(self) -> None:
        """Disconnect client."""
        async with self._lock:
            if self._client:
                try:
                    self._client.close()
                except ModbusException as exception_error:
                    _LOGGER.error(exception_error)
                del self._client
                self._client = None
                _LOGGER.warning("modbus communication closed")

    def _pymodbus_connect(self) -> bool:
        """Connect client."""
        try:
            return self._client.connect()  # type: ignore[union-attr]
        except ModbusException as exception_error:
            _LOGGER.error(exception_error)
            return False

    async def read_single_register(
        self, unit: int, address: int, count: int = 2, method: str = "input"
    ) -> float | None:
        """Call sync. pymodbus."""
        async with self._lock:
            if not self._pymodbus_connect():
                _LOGGER.error("Can't connect to Modbus address %s.", address)
                return None
            kwargs = {"unit": unit, "count": count} if unit else {}
            try:
                result: ReadInputRegistersResponse = self._read_methods[method](
                    address, **kwargs
                )
            except ModbusException as exception_error:
                _LOGGER.error(exception_error)
                return None
            if not hasattr(result, REGISTERS):
                _LOGGER.error(str(result))
                return None
            return BinaryPayloadDecoder.fromRegisters(
                result.registers, byteorder=Endian.Big, wordorder=Endian.Big
            ).decode_32bit_float()

    async def read_multiple_registers(
        self, unit: int, address: int, count: int = 2, method: str = "input"
    ) -> ModbusResponse:
        """Call sync. pymodbus."""
        async with self._lock:
            if not self._pymodbus_connect():
                _LOGGER.error("Can't connect to Modbus.")
                return None
            kwargs = {"unit": unit, "count": count} if unit else {}
            try:
                result: ReadInputRegistersResponse = self._read_methods[method](
                    address, **kwargs
                )
            except ModbusException as exception_error:
                _LOGGER.error(exception_error)
                return None
            if not hasattr(result, REGISTERS):
                _LOGGER.error(str(result))
                return None
            return result
