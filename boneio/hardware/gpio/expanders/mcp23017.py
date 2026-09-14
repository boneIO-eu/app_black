"""MCP23017 I2C GPIO expander driver using smbus2.

MCP23017 is a 16-bit I/O expander with I2C interface.
This implementation is output-only for relay control.
"""

from __future__ import annotations

import logging
import threading
import time
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from boneio.core.state.manager import StateManager
    from boneio.hardware.i2c.bus import SMBus2I2C

_LOGGER = logging.getLogger(__name__)

# MCP23017 Registers
IODIRA = 0x00  # I/O direction register for port A (1=input, 0=output)
IODIRB = 0x01  # I/O direction register for port B
GPIOA = 0x12   # GPIO register for port A
GPIOB = 0x13   # GPIO register for port B
OLATA = 0x14   # Output latch register for port A
OLATB = 0x15   # Output latch register for port B

# IOCON is mirrored at 0x0A and 0x0B while BANK=0. With BANK=1 the whole
# register map shifts and 0x05 becomes IOCON instead — see _force_bank0().
IOCON_A = 0x0A
IOCON_B = 0x0B
IOCON_BANK1 = 0x05
# SEQOP=1 (address pointer does not auto-increment), BANK=0.
IOCON_VALUE = 0x20
# Every pin driven as an output.
IODIR_ALL_OUTPUTS = 0x00

# Minimum delay between I2C operations in seconds
# This prevents bus contention when switching multiple outputs rapidly
I2C_OPERATION_DELAY = 0.002  # 2ms


class MCP23017:
    """MCP23017 16-bit I2C GPIO expander driver.
    
    Output-only implementation for relay control.
    Pins 0-7 are on Port A, pins 8-15 are on Port B.
    
    Args:
        i2c: I2C bus instance
        address: I2C address of the MCP23017 (default 0x20)
    
    Example:
        from boneio.hardware.i2c import SMBus2I2C
        from boneio.hardware.gpio.expanders import MCP23017
        
        i2c = SMBus2I2C(bus_number=2)
        mcp = MCP23017(i2c=i2c, address=0x20)
        pin0 = mcp.get_pin(0)
        pin0.switch_to_output(value=True)
    """

    def __init__(
        self,
        i2c: SMBus2I2C,
        address: int = 0x20,
        reset: bool = False,
        inverted: bool | None = None,
        state_manager: StateManager | None = None,
    ):
        """Initialize MCP23017.
        
        Args:
            i2c: I2C bus instance (SMBus2I2C)
            address: I2C address of the device (default 0x20)
            reset: Reset flag (unused, for API compatibility with Adafruit library)
            inverted: Active-LOW relay board flag (True=active-LOW, False=active-HIGH, None=auto-detect)
            state_manager: Optional StateManager instance to persist/read auto-detected logic
        
        Raises:
            ValueError: If address is not in valid range (0x20-0x27)
            RuntimeError: If I2C bus cannot be locked
        """
        # Validate I2C address (MCP23017 supports 0x20-0x27 via A0-A2 pins)
        if not 0x20 <= address <= 0x27:
            raise ValueError(f"MCP23017 address must be 0x20-0x27, got 0x{address:02X}")
        
        self._i2c = i2c
        self._address = address
        self._state_manager = state_manager
        
        # Lock for thread-safe pin operations
        # This prevents race conditions when multiple outputs are switched simultaneously
        self._lock = threading.Lock()
        
        # Track output states (16 pins, 2 bytes)
        self._port_a_state = 0x00  # Pins 0-7
        self._port_b_state = 0x00  # Pins 8-15
        
        # Timestamp of last I2C operation for rate limiting
        self._last_operation_time = 0.0
        
        # Lock the I2C bus for initialization
        if not self._i2c.try_lock():
            raise RuntimeError("Failed to lock I2C bus for MCP23017 initialization")
        
        try:
            self._force_bank0_unlocked()

            # Read IODIR to check if this is cold boot (all inputs = 0xFF)
            iodir_a = self._read_register_unlocked(IODIRA)
            iodir_b = self._read_register_unlocked(IODIRB)
            is_cold_boot = (iodir_a == 0xFF and iodir_b == 0xFF)

            # Determine inverted state:
            # 1. Config override
            # 2. State manager persisted value
            # 3. Auto-detection on cold boot (GPIO read)
            # 4. Fallback (False)
            state_key = f"mcp_0x{address:02x}_inverted"
            if inverted is not None:
                self._inverted = bool(inverted)
                _LOGGER.info("MCP23017@0x%02X inverted set from config: %s", address, self._inverted)
            elif state_manager and state_manager.get("hardware", state_key) is not None:
                self._inverted = bool(state_manager.get("hardware", state_key))
                _LOGGER.info("MCP23017@0x%02X inverted loaded from state: %s", address, self._inverted)
            elif is_cold_boot:
                gpio_a = self._read_register_unlocked(GPIOA)
                gpio_b = self._read_register_unlocked(GPIOB)
                self._inverted = (gpio_a == 0xFF and gpio_b == 0xFF)
                _LOGGER.info(
                    "MCP23017@0x%02X auto-detected relay board logic: %s (GPIOA=0x%02X, GPIOB=0x%02X)",
                    address,
                    "active-LOW (inverted)" if self._inverted else "active-HIGH",
                    gpio_a,
                    gpio_b,
                )
                if state_manager:
                    state_manager.save_attribute("hardware", state_key, self._inverted)
            else:
                self._inverted = False
                _LOGGER.info("MCP23017@0x%02X inverted fallback: False", address)
            
            # Read current output latch states from hardware to preserve relay states
            if is_cold_boot:
                # The pins are still inputs, so nothing is being driven and there
                # is no relay state worth preserving. Latch the OFF level for this
                # board's polarity *before* IODIR turns the pins into outputs, so
                # enabling the drivers cannot pulse the relays. The level depends
                # on polarity: active-LOW boards are off at HIGH, active-HIGH
                # boards are off at LOW. Deriving it (instead of only writing
                # 0xFF when inverted) keeps a mis-detected polarity from turning
                # every relay on at startup.
                safe_level = 0xFF if self._inverted else 0x00
                self._port_a_state = safe_level
                self._port_b_state = safe_level
                self._write_register_unlocked(OLATA, safe_level)
                self._write_register_unlocked(OLATB, safe_level)
            else:
                self._port_a_state = self._read_register_unlocked(OLATA)
                self._port_b_state = self._read_register_unlocked(OLATB)

            _LOGGER.debug(
                f"MCP23017@0x{address:02X} preserved states (inverted={self._inverted}): "
                f"A=0b{self._port_a_state:08b}, B=0b{self._port_b_state:08b}"
            )
            
            # Initialize: Set all pins as outputs (IODIR=0x00)
            # This does NOT change the output latch values
            self._write_register_unlocked(IODIRA, IODIR_ALL_OUTPUTS)
            self._write_register_unlocked(IODIRB, IODIR_ALL_OUTPUTS)
            
            _LOGGER.info(f"Initialized MCP23017 at address 0x{address:02X} (inverted={self._inverted})")
        finally:
            self._i2c.unlock()

    def _force_bank0_unlocked(self) -> None:
        """Put IOCON into a known state, whichever bank the chip is currently in.

        The register map depends on IOCON.BANK, and the driver's constants assume
        BANK=0. A chip that came up dirty (or was glitched into BANK=1) addresses
        a completely different map, so writing IOCON at 0x0A blind would land on
        OLATA instead and never clear the bank bit.

        With BANK=1, 0x05 *is* IOCON, so zeroing it switches the map back to
        BANK=0. With BANK=0, 0x05 is GPINTENB, which this output-only driver
        keeps at 0x00 anyway — so the write is a no-op either way, and afterwards
        the map is guaranteed to be BANK=0.

        Caller must hold the I2C lock.
        """
        self._write_register_unlocked(IOCON_BANK1, 0x00)
        self._write_register_unlocked(IOCON_A, IOCON_VALUE)
        self._write_register_unlocked(IOCON_B, IOCON_VALUE)

    def _reconfigure_unlocked(self) -> None:
        """Re-apply IOCON, the cached output latches and IODIR.

        The latches go back *before* IODIR turns the pins into outputs again, so
        re-enabling the drivers takes the relays straight to the last commanded
        state instead of through the expander's power-on value.

        Caller must hold both ``self._lock`` and the I2C lock.
        """
        self._force_bank0_unlocked()
        self._write_register_unlocked(OLATA, self._port_a_state)
        self._write_register_unlocked(OLATB, self._port_b_state)
        self._write_register_unlocked(IODIRA, IODIR_ALL_OUTPUTS)
        self._write_register_unlocked(IODIRB, IODIR_ALL_OUTPUTS)

    def health_check(self) -> bool:
        """Verify the expander still holds its output configuration; repair it if not.

        A brown-out on VDD or a glitch on the RESET/I2C lines resets the
        MCP23017 to its power-on state: IODIR = 0xFF, every pin an input. The
        normal write path cannot notice this. OLAT is writable and readable
        regardless of IODIR, so ``_write_pin`` keeps succeeding, reads back the
        value it just wrote and raises nothing — while the pins are high-Z and
        the relays no longer follow the software state. Until something
        re-asserts IODIR the outputs stay dead, which is why restarting the
        service "fixes" it: ``__init__`` reconfigures the chip.

        Returns:
            True if a misconfiguration was found and repaired, False if the
            expander was already healthy or the check itself failed.
        """
        with self._lock:
            try:
                with self._i2c:
                    # Read 0x05 first: with BANK=1 it is IOCON (bit 7 = BANK, so
                    # it reads back set), with BANK=0 it is GPINTENB, which this
                    # driver never enables. It is the only single register that
                    # tells the two maps apart.
                    bank1 = bool(self._read_register_unlocked(IOCON_BANK1) & 0x80)
                    if bank1:
                        iocon = iodir_a = iodir_b = None
                    else:
                        iocon = self._read_register_unlocked(IOCON_A)
                        iodir_a = self._read_register_unlocked(IODIRA)
                        iodir_b = self._read_register_unlocked(IODIRB)
                        if (
                            iocon == IOCON_VALUE
                            and iodir_a == IODIR_ALL_OUTPUTS
                            and iodir_b == IODIR_ALL_OUTPUTS
                        ):
                            return False

                    _LOGGER.warning(
                        "MCP23017@0x%02X lost its configuration and stopped driving its "
                        "outputs (BANK=%d, IOCON=%s, IODIRA=%s, IODIRB=%s, expected "
                        "IOCON=0x%02X IODIR=0x%02X). Relays were not following commanded "
                        "state. Reconfiguring and restoring A=%s B=%s. This is "
                        "usually a supply brown-out or electrical noise on the expander.",
                        self._address,
                        1 if bank1 else 0,
                        "n/a (BANK=1)" if iocon is None else f"0x{iocon:02X}",
                        "n/a (BANK=1)" if iodir_a is None else f"0x{iodir_a:02X}",
                        "n/a (BANK=1)" if iodir_b is None else f"0x{iodir_b:02X}",
                        IOCON_VALUE,
                        IODIR_ALL_OUTPUTS,
                        f"0b{self._port_a_state:08b}",
                        f"0b{self._port_b_state:08b}",
                    )

                    self._reconfigure_unlocked()
                    return True
            except Exception as e:
                _LOGGER.error(
                    "MCP23017@0x%02X health check failed: %s", self._address, e
                )
                return False

    def _write_register_unlocked(self, register: int, value: int) -> None:
        """Write byte to register (caller must hold I2C lock).
        
        Args:
            register: Register address
            value: Byte value to write
        """
        try:
            self._i2c.write_byte_data(self._address, register, value)
        except Exception as e:
            _LOGGER.error(f"Failed to write MCP23017@0x{self._address:02X} register 0x{register:02X}: {e}")
            raise

    def _read_register_unlocked(self, register: int) -> int:
        """Read byte from register (caller must hold I2C lock).
        
        Args:
            register: Register address
            
        Returns:
            Byte value from register
        """
        try:
            return self._i2c.read_byte_data(self._address, register)
        except Exception as e:
            _LOGGER.error(f"Failed to read MCP23017@0x{self._address:02X} register 0x{register:02X}: {e}")
            raise

    def _write_register(self, register: int, value: int) -> None:
        """Write byte to register using direct SMBus call.
        
        Args:
            register: Register address
            value: Byte value to write
        """
        with self._i2c:
            self._write_register_unlocked(register, value)

    def _read_register(self, register: int) -> int:
        """Read byte from register using direct SMBus call with retry.
        
        Args:
            register: Register address
            
        Returns:
            Byte value from register
        """
        retries = 3
        last_error = None
        
        for i in range(retries):
            try:
                with self._i2c:
                    return self._i2c.read_byte_data(self._address, register)
            except Exception as e:
                last_error = e
                # Small delay before retry (outside of I2C lock!)
                time.sleep(0.001 * (i + 1))
        
        _LOGGER.error(f"Failed to read MCP23017@0x{self._address:02X} register 0x{register:02X} after {retries} attempts: {last_error}")
        raise last_error or RuntimeError(f"Failed to read register 0x{register:02X}")

    def _configure_pin_as_output(self, pin_number: int) -> None:
        """Configure a pin as output.
        
        Thread-safe and atomic I2C operation.
        
        Args:
            pin_number: Pin number (0-15)
        """
        with self._lock, self._i2c:
            if pin_number < 8:
                # Port A (pins 0-7)
                iodir = self._read_register_unlocked(IODIRA)
                iodir &= ~(1 << pin_number)  # Clear bit = output
                self._write_register_unlocked(IODIRA, iodir)
            else:
                # Port B (pins 8-15)
                pin_bit = pin_number - 8
                iodir = self._read_register_unlocked(IODIRB)
                iodir &= ~(1 << pin_bit)  # Clear bit = output
                self._write_register_unlocked(IODIRB, iodir)

    @property
    def inverted(self) -> bool:
        """Check whether expander operates in inverted (active-LOW) mode."""
        return self._inverted

    @property
    def address(self) -> int:
        """Get the I2C address of this expander."""
        return self._address

    def _write_pin(self, pin_number: int, value: bool) -> None:
        """Write value to a pin using ATOMIC hardware Read-Modify-Write.
        
        This implementation performs read and write in a SINGLE I2C transaction block,
        ensuring no other thread can interfere between read and write operations.
        
        Args:
            pin_number: Pin number (0-15)
            value: Output state (True=ON/HIGH logical, False=OFF/LOW logical)
        """
        with self._lock:
            # Rate limiting: ensure minimum delay between I2C operations
            # Do this BEFORE acquiring I2C lock to avoid blocking other devices
            now = time.monotonic()
            elapsed = now - self._last_operation_time
            if elapsed < I2C_OPERATION_DELAY:
                time.sleep(I2C_OPERATION_DELAY - elapsed)
            
            # Determine register and bit position
            if pin_number < 8:
                reg = OLATA
                bit = pin_number
            else:
                reg = OLATB
                bit = pin_number - 8
            
            try:
                # ATOMIC Read-Modify-Write: Single I2C lock for entire operation
                with self._i2c:
                    # The cache is the authoritative record of what was commanded:
                    # every mutation of it happens under self._lock, so it cannot
                    # drift on its own. The hardware latch can — an expander that
                    # was reset comes back with OLAT at its power-on value. Derive
                    # the new state from the cache and use the hardware read only
                    # to detect that divergence. Deriving it from the hardware read
                    # instead would silently drop every other pin on this port
                    # whenever the expander had been reset.
                    cached_state = self._port_a_state if pin_number < 8 else self._port_b_state

                    # Check IODIR, not OLAT, to decide whether the expander is
                    # still driving. IODIR has a state-independent expected value
                    # (every pin an output), so the check holds in every commanded
                    # state and on either polarity. Comparing the latch against the
                    # cache would go blind whenever the commanded value happens to
                    # equal the power-on value — which on an active-HIGH board is
                    # simply "this port is all off", a very ordinary state.
                    iodir_reg = IODIRA if pin_number < 8 else IODIRB
                    iodir = self._read_register_unlocked(iodir_reg)

                    if iodir != IODIR_ALL_OUTPUTS:
                        _LOGGER.warning(
                            "MCP23017@0x%02X %s reads %s, expected %s: the expander "
                            "lost its configuration and is not driving its outputs. "
                            "Reconfiguring now and applying this write on top of the "
                            "commanded state %s.",
                            self._address,
                            "IODIRA" if pin_number < 8 else "IODIRB",
                            f"0x{iodir:02X}",
                            f"0x{IODIR_ALL_OUTPUTS:02X}",
                            f"0b{cached_state:08b}",
                        )
                        # Cannot call health_check() here: self._lock is not
                        # reentrant and this thread already holds it.
                        self._reconfigure_unlocked()

                    # Account for active-LOW inverted logic
                    effective_value = not value if self._inverted else value

                    # Calculate new state
                    if effective_value:
                        new_state = cached_state | (1 << bit)
                    else:
                        new_state = cached_state & ~(1 << bit)
                    
                    # Only write if state changed
                    if new_state != cached_state:
                        _LOGGER.debug(
                            f"MCP23017@0x{self._address:02X} pin {pin_number} -> {value} (phys={effective_value}): "
                            f"{'OLATA' if pin_number < 8 else 'OLATB'} "
                            f"0b{cached_state:08b} -> 0b{new_state:08b}"
                        )
                        self._write_register_unlocked(reg, new_state)
                        
                        # Update cache after successful write
                        if pin_number < 8:
                            self._port_a_state = new_state
                        else:
                            self._port_b_state = new_state
                        
            except Exception as e:
                _LOGGER.error(f"Error writing MCP23017@0x{self._address:02X} pin {pin_number}: {e}")
                raise  # Re-raise to signal error to caller
            
            self._last_operation_time = time.monotonic()

    def configure_pin_as_output(self, pin_number: int, value: bool = False) -> None:
        """Configure a pin as output and set initial value.
        
        Args:
            pin_number: Pin number (0-15)
            value: Initial output state (True=HIGH, False=LOW)
        """
        if not 0 <= pin_number <= 15:
            raise ValueError(f"Pin number must be 0-15, got {pin_number}")
        
        self._configure_pin_as_output(pin_number)
        self._write_pin(pin_number, value)
        _LOGGER.debug(f"MCP23017 pin {pin_number} configured as output, initial value: {value}")

    def set_pin_value(self, pin_number: int, value: bool) -> None:
        """Set pin output value.
        
        Args:
            pin_number: Pin number (0-15)
            value: Output state (True=HIGH, False=LOW)
        """
        if not 0 <= pin_number <= 15:
            raise ValueError(f"Pin number must be 0-15, got {pin_number}")
        
        self._write_pin(pin_number, value)

    def get_pin_value(self, pin_number: int) -> bool:
        """Get current logical pin value.
        
        Args:
            pin_number: Pin number (0-15)
            
        Returns:
            Current logical pin state (accounting for active-LOW inverted logic)
        """
        if not 0 <= pin_number <= 15:
            raise ValueError(f"Pin number must be 0-15, got {pin_number}")
        
        with self._lock:
            if pin_number < 8:
                raw_state = bool(self._port_a_state & (1 << pin_number))
            else:
                pin_bit = pin_number - 8
                raw_state = bool(self._port_b_state & (1 << pin_bit))
            return not raw_state if self._inverted else raw_state

    def verify_port_state(self) -> tuple[int, int]:
        """Read actual port states from hardware and compare with cached state.
        
        Returns:
            Tuple of (actual_port_a, actual_port_b) read from hardware
        """
        with self._lock:
            actual_a = self._read_register(OLATA)
            actual_b = self._read_register(OLATB)
            
            if actual_a != self._port_a_state or actual_b != self._port_b_state:
                _LOGGER.warning(
                    f"MCP23017@0x{self._address:02X} state mismatch! "
                    f"Cached: A=0b{self._port_a_state:08b}, B=0b{self._port_b_state:08b} | "
                    f"Actual: A=0b{actual_a:08b}, B=0b{actual_b:08b}"
                )
            return (actual_a, actual_b)

    def __del__(self):
        """Cleanup on deletion."""
        # No cleanup needed - I2C bus is managed by the main bus manager
        pass
