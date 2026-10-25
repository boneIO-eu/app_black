"""1-Wire addresses: the kernel form and the ESPHome form name one sensor."""

import pytest

from boneio.core.config.models.sensors import OneWireSensor
from boneio.core.config.config_helper import ConfigHelper
from boneio.core.config.onewire_address import esphome_address, kernel_address, loaded_address

# Read from a working ESPHome config and the same sensors on the w1 bus.
PAIRS = [
    ("28-000000053f33", "0xc0000000053f3328"),
    ("28-02131dda9aaa", "0xc202131dda9aaa28"),
]


@pytest.mark.parametrize(("kernel", "esphome"), PAIRS)
def test_both_forms_meet(kernel, esphome):
    assert kernel_address(esphome) == kernel
    assert kernel_address(kernel) == kernel
    assert esphome_address(kernel) == esphome
    assert esphome_address(esphome) == esphome


def test_unquoted_yaml_hex_is_an_int():
    assert kernel_address(0xC202131DDA9AAA28) == "28-02131dda9aaa"


def test_crc_with_leading_zero_keeps_its_digits():
    # Family 28 with this serial sums to a CRC below 0x10.
    serial = next(
        f"{n:012x}" for n in range(1000) if esphome_address(f"28-{n:012x}")[2] == "0"
    )
    esp = esphome_address(f"28-{serial}")
    assert len(esp) == 18
    assert kernel_address(int(esp, 16)) == f"28-{serial}"


def test_upper_case_and_bare_serial():
    assert kernel_address("28-02131DDA9AAA") == "28-02131dda9aaa"
    assert kernel_address("0XC202131DDA9AAA28") == "28-02131dda9aaa"
    assert kernel_address("02131dda9aaa") == "28-02131dda9aaa"


@pytest.mark.parametrize(
    "bad", ["0xc302131dda9aaa28", "0x02131dda9aaa28", "28-02131dda9a", "dallas", True]
)
def test_rejects(bad):
    with pytest.raises(ValueError):
        kernel_address(bad)


def test_model_stores_the_kernel_form():
    assert OneWireSensor(address=0xC0000000053F3328).address == "28-000000053f33"
    with pytest.raises(ValueError):
        OneWireSensor(address="0xc1000000053f3328")


def test_loading_lets_an_unknown_address_through():
    # Start-up must not stop the controller over one sensor entry.
    assert loaded_address("28-0000") == "28-0000"
    assert loaded_address(0xC0000000053F3328) == "28-000000053f33"


def test_reload_and_save_hold_the_kernel_form(tmp_path):
    (tmp_path / "config.yaml").write_text(
        "boneio:\n"
        "  name: test\n"
        "  device_type: 32x10A\n"
        "  version: '0.8'\n"
        "sensor:\n"
        "  - address: 0xc0000000053f3328\n"
        "  - address: 28-02131dda9aaa\n",
        encoding="utf-8",
    )
    helper = ConfigHelper(
        name="black", serial_override="blk0001", config_file_path=str(tmp_path / "config.yaml")
    )
    reloaded = helper.reload_config()["sensor"]
    assert [s["address"] for s in reloaded] == ["28-000000053f33", "28-02131dda9aaa"]

    helper.update_config_section("sensor", [{"address": "0xc202131dda9aaa28"}])
    assert helper.get_config()["sensor"][0]["address"] == "28-02131dda9aaa"
