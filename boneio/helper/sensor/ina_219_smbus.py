# Based on https://github.com/AlexandreFrolov/ina219/blob/main/ina_219_smbus.py
from __future__ import annotations
import smbus2


class INA219_I2C:
    INA219_CONFIG = 0x00
    INA219_SV = 0x01
    INA219_BV = 0x02
    INA219_PW = 0x03
    INA219_CU = 0x04
    INA219_CAL = 0x05
    # config register configurations
    INA219_CONFIG_RESET = 0x8000  # Reset Bit

    INA219_CONFIG_BVOLTAGERANGE_MASK = 0x2000  # Bus Voltage Range Mask
    INA219_CONFIG_BVOLTAGERANGE_16V = 0x0000  # 0-16V Range
    INA219_CONFIG_BVOLTAGERANGE_32V = 0x2000  # 0-32V Range

    INA219_CONFIG_GAIN_MASK = 0x1800  # Gain Mask
    INA219_CONFIG_GAIN_1_40MV = 0x0000  # Gain 1, 40mV Range
    INA219_CONFIG_GAIN_2_80MV = 0x0800  # Gain 2, 80mV Range
    INA219_CONFIG_GAIN_4_160MV = 0x1000  # Gain 4, 160mV Range
    INA219_CONFIG_GAIN_8_320MV = 0x1800  # Gain 8, 320mV Range

    INA219_CONFIG_BADCRES_MASK = 0x0780  # Bus ADC Resolution Mask
    INA219_CONFIG_BADCRES_9BIT = 0x0080  # 9-bit bus res = 0..511
    INA219_CONFIG_BADCRES_10BIT = 0x0100  # 10-bit bus res = 0..1023
    INA219_CONFIG_BADCRES_11BIT = 0x0200  # 11-bit bus res = 0..2047
    INA219_CONFIG_BADCRES_12BIT = 0x0400  # 12-bit bus res = 0..4097

    INA219_CONFIG_SADCRES_MASK = 0x0078  # Shunt ADC Resolution and Averaging Mask
    INA219_CONFIG_SADCRES_9BIT_1S_84US = 0x0000  # 1 x 9-bit shunt sample
    INA219_CONFIG_SADCRES_10BIT_1S_148US = 0x0008  # 1 x 10-bit shunt sample
    INA219_CONFIG_SADCRES_11BIT_1S_276US = 0x0010  # 1 x 11-bit shunt sample
    INA219_CONFIG_SADCRES_12BIT_1S_532US = 0x0018  # 1 x 12-bit shunt sample
    INA219_CONFIG_SADCRES_12BIT_2S_1060US = (
        0x0048  # 2 x 12-bit shunt samples averaged together
    )
    INA219_CONFIG_SADCRES_12BIT_4S_2130US = (
        0x0050  # 4 x 12-bit shunt samples averaged together
    )
    INA219_CONFIG_SADCRES_12BIT_8S_4260US = (
        0x0058  # 8 x 12-bit shunt samples averaged together
    )
    INA219_CONFIG_SADCRES_12BIT_16S_8510US = (
        0x0060  # 16 x 12-bit shunt samples averaged together
    )
    INA219_CONFIG_SADCRES_12BIT_32S_17MS = (
        0x0068  # 32 x 12-bit shunt samples averaged together
    )
    INA219_CONFIG_SADCRES_12BIT_64S_34MS = (
        0x0070  # 64 x 12-bit shunt samples averaged together
    )
    INA219_CONFIG_SADCRES_12BIT_128S_69MS = (
        0x0078  # 128 x 12-bit shunt samples averaged together
    )

    INA219_CONFIG_MODE_MASK = 0x0007  # Operating Mode Mask
    INA219_CONFIG_MODE_POWERDOWN = 0x0000
    INA219_CONFIG_MODE_SVOLT_TRIGGERED = 0x0001
    INA219_CONFIG_MODE_BVOLT_TRIGGERED = 0x0002
    INA219_CONFIG_MODE_SANDBVOLT_TRIGGERED = 0x0003
    INA219_CONFIG_MODE_ADCOFF = 0x0004
    INA219_CONFIG_MODE_SVOLT_CONTINUOUS = 0x0005
    INA219_CONFIG_MODE_BVOLT_CONTINUOUS = 0x0006
    INA219_CONFIG_MODE_SANDBVOLT_CONTINUOUS = 0x0007

    def __init__(self, address: int = 0x40, _bus: int = 2, cal: int = 4096) -> None:
        self._address = address
        self._CAL = cal
        self.bus = smbus2.SMBus(_bus)
        self.s_cal = 0
        self.set_cal(self._CAL)

    def set_config(self, config_list):
        cfg = sum(config_list)
        self.write_word(self.INA219_CONFIG, cfg)

    def reset(
        self,
    ):
        self.write_word(self.INA219_CONFIG, self.INA219_CONFIG_RESET)

    def set_gain(self, gain):
        config = self.read_word(self.INA219_CONFIG)
        config = config & 0b1110011111111111
        config = config + gain
        self.write_word(self.INA219_CONFIG, config)

    def set_brang(self, brng):
        config = self.read_word(self.INA219_CONFIG)
        config = config & 0b1101111111111111
        config = config + brng
        self.write_word(self.INA219_CONFIG, config)

    def set_badc(self, badc):
        config = self.read_word(self.INA219_CONFIG)
        config = config & 0b1111100001111111
        config = config + badc
        self.write_word(self.INA219_CONFIG, config)

    def set_sadc(self, sadc):
        config = self.read_word(self.INA219_CONFIG)
        config = config & 0b1111111110000111
        config = config + sadc
        self.write_word(self.INA219_CONFIG, config)

    def set_mode(self, mode):
        config = self.read_word(self.INA219_CONFIG)
        config = config & 0b1111111111111000
        config = config + mode
        self.write_word(self.INA219_CONFIG, config)

    def set_cal(self, cal_value):
        self.write_word(self.INA219_CAL, cal_value)
        self.s_cal = cal_value

    def get_bus_voltage(self, mV: bool = False):
        raw_value = self.read_word(self.INA219_BV)
        return round((raw_value >> 3) * 4 * (0.001 if mV is False else 1), 2)

    def get_shunt_voltage(self, mV=False):
        raw_value = self.read_word(self.INA219_SV)
        return raw_value
    
    @property
    def power(self) -> float:
        return self.get_power(mW=False)
    
    @property
    def voltage(self) -> float:
        return self.get_bus_voltage()

    @property
    def current(self) -> float:
        return self.get_current(mA=False)

    def get_current(self, mA: bool = True) -> float:
        self.set_cal(self.s_cal)
        raw_value = self.read_word(self.INA219_CU)
        if raw_value > 32767:
            raw_value = raw_value - 65535
        current = raw_value / 10
        return round(current / (1000.0 if mA is False else 1.0), 3)

    def get_power(self, mW: bool = True) -> float:
        """
        raw_value=self.read_word(self.INA219_PW)
        current=(raw_value/2)
        return current/(1000 if mW==False else 1)
        """
        BV = self.get_bus_voltage()
        CV = self.get_current(mA=False)
        return round((BV * CV) * (1000 if mW is True else 1), 2)

    def read_word(self, address):
        read_data = self.bus.read_word_data(self._address, address)
        ac_high_byte = read_data & 0xFF
        ac_low_byte = (read_data & 0xFF00) >> 8
        return (ac_high_byte << 8) + ac_low_byte

    def write_word(self, address, data):
        cnv_high_byte = data & 0xFF
        cnv_low_byte = (data & 0xFF00) >> 8
        formed_data = (cnv_high_byte << 8) + cnv_low_byte
        self.bus.write_word_data(self._address, address, formed_data)
