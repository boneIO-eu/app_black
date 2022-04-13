"""DS2482 base class.
Module by https://github.com/fgervais/ds2482
"""
import time

import adafruit_bus_device.i2c_device as i2c_device

# Default i2c address (AD0 = GND, AD1 = GND)
DS2482_ADDRESS = 0x18

# DS2482 device commands
COMMAND_DEVICE_RESET = 0xF0
COMMAND_SET_POINTER = 0xE1
COMMAND_WRITE_CONFIG = 0xD2
COMMAND_1W_RESET = 0xB4
COMMAND_1W_SINGLE_BIT = 0x87
COMMAND_1W_WRITE_BYTE = 0xA5
COMMAND_1W_READ_BYTE = 0x96
COMMAND_1W_TRIPLET = 0x78

# DS2482 read pointer codes
POINTER_STATUS = 0xF0
POINTER_DATA = 0xE1
POINTER_CONFIG = 0xC3

# DS2482 configuration register
CONFIG_ACTIVE_PULLUP = 0x01
CONFIG_STRONG_PULLUP = 0x04
CONFIG_1W_OVERDRIVE = 0x08

CONFIG_MASK = 0x0F

# DS2482 status register
STATUS_1W_BUSY = 0x01
STATUS_PRESENCE_PULSE = 0x02
STATUT_SHORT_DETECTED = 0x04
STATUS_LOGIC_LEVEL = 0x08
STATUS_DEVICE_RESET = 0x10
STATUS_SINGLE_BIT = 0x20
STATUS_TRIPLET_BIT = 0x40
STATUS_BRANCH_TAKEN = 0x80


class DS2482:
    def __init__(self, i2c, address=DS2482_ADDRESS, active_pullup=False):
        self._i2c = i2c_device.I2CDevice(i2c, address)
        self.device_reset()
        if active_pullup:
            self.device_config = CONFIG_ACTIVE_PULLUP

        # 1-Wire bus busy with STRONG_PULLUP
        self._bus_busy = time.monotonic()

    def device_reset(self):
        """Terminate any 1-wire communication and reset the DS2482"""
        with self._i2c as i2c:
            i2c.write(bytes([COMMAND_DEVICE_RESET]))

    @property
    def device_status(self):
        with self._i2c as i2c:
            buf = bytearray([COMMAND_SET_POINTER, POINTER_STATUS])
            i2c.write_then_readinto(buf, buf, in_end=1)
            return buf[0]

    @property
    def device_config(self):
        with self._i2c as i2c:
            buf = bytearray([COMMAND_SET_POINTER, POINTER_CONFIG])
            i2c.write_then_readinto(buf, buf, in_end=1)
            return buf[0] & 0x0F

    @device_config.setter
    def device_config(self, config):
        with self._i2c as i2c:
            i2c.write(
                bytes([COMMAND_WRITE_CONFIG, (config & 0x0F) | ((~config << 4) & 0xF0)])
            )

    def reset(self):
        with self._i2c as i2c:
            buf = bytearray([COMMAND_1W_RESET])
            i2c.write(buf)
            while True:
                i2c.readinto(buf)
                if not buf[0] & STATUS_1W_BUSY:
                    break
                time.sleep(0.001)
            return not buf[0] & STATUS_PRESENCE_PULSE

    def single_bit(self, bit=1, strong_pullup=False, busy=None):
        with self._i2c as i2c:
            buf = bytearray(2)
            if strong_pullup:
                buf[0:2] = [COMMAND_SET_POINTER, POINTER_CONFIG]
                i2c.write_then_readinto(buf, buf, in_start=1)
                buf[0] = COMMAND_WRITE_CONFIG
                buf[1] = buf[1] & CONFIG_MASK | CONFIG_STRONG_PULLUP
                buf[1] |= (~buf[1] << 4) & 0xFF
                i2c.write(buf)
            buf[0:2] = [COMMAND_1W_SINGLE_BIT, 0x80 if bit else 0x00]
            i2c.write(buf)
            while True:
                i2c.readinto(buf, end=1)
                if not buf[0] & STATUS_1W_BUSY:
                    break
                time.sleep(0.001)
            if busy:
                self._bus_busy = time.monotonic() + busy
            return buf[0] & STATUS_SINGLE_BIT != 0

    def write_byte(self, data, strong_pullup=False, busy=None):
        with self._i2c as i2c:
            buf = bytearray(2)
            if strong_pullup:
                buf[0:2] = [COMMAND_SET_POINTER, POINTER_CONFIG]
                i2c.write_then_readinto(buf, buf, in_start=1)
                buf[0] = COMMAND_WRITE_CONFIG
                buf[1] = buf[1] & CONFIG_MASK | CONFIG_STRONG_PULLUP
                buf[1] |= (~buf[1] << 4) & 0xFF
                i2c.write(buf)
            buf[0:2] = [COMMAND_1W_WRITE_BYTE, data]
            i2c.write(buf)
            while True:
                i2c.readinto(buf, end=1)
                if buf[0] & STATUS_1W_BUSY == 0:
                    break
                time.sleep(0.001)
            if busy:
                self._bus_busy = time.monotonic() + busy

    def read_byte(self):
        with self._i2c as i2c:
            buf = bytearray([COMMAND_1W_READ_BYTE, 0x00])
            i2c.write(buf, end=1)
            while True:
                i2c.readinto(buf, end=1)
                if not buf[0] & STATUS_1W_BUSY:
                    break
                time.sleep(0.001)
            buf[0:2] = [COMMAND_SET_POINTER, POINTER_DATA]
            i2c.write_then_readinto(buf, buf, in_end=1)
            return buf[0]

    def wait_ready(self):
        while True:
            t = self._bus_busy - time.monotonic()
            if t > 0:
                time.sleep(t)
            else:
                break
        with self._i2c as i2c:
            buf = bytearray([COMMAND_SET_POINTER, POINTER_STATUS])
            i2c.write(buf)
            while True:
                i2c.readinto(buf, end=1)
                if not buf[0] & STATUS_1W_BUSY:
                    break
                time.sleep(0.001)
            return buf[0]

    def triplet(self, dir):
        pass
