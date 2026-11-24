"""RX910-SE21 heat pump controller, read over RS232.

The map numbers holding registers 4001..4248 and those are the wire
addresses as they are: the customer's Node-RED flow reads seconds, minutes
and hours from 4000, 4001 and 4002. Below zero a temperature reads above
32765 and the flow takes ``-(raw - 32765) / 10``.
"""

from boneio.core.utils.filter import Filter
from boneio.modbus.definition import load_definition

RX910 = load_definition("rx910-se21")


def _registers():
    return {r.name: r for b in RX910.registers_base for r in b.registers}


def _decode(name: str, raw: int):
    return Filter()._apply_filters(raw, [dict(f) for f in _registers()[name].filters])


def test_reads_holding_registers_at_the_map_numbers():
    assert {b.register_type for b in RX910.registers_base} == {"holding"}
    regs = _registers()
    assert regs["Temperatura zewnętrzna"].address == 4065
    assert regs["Dolne źródło wejście"].address == 4070
    assert regs["Sprężarka"].address == 4114
    assert regs["Zadana temperatura CWU"].address == 4203
    assert regs["Stan pracy"].address == 4227


def test_temperature_below_zero_decodes_as_the_flow_does():
    assert _decode("Temperatura zewnętrzna", 215) == 21.5
    assert _decode("Temperatura zewnętrzna", 32766) == -0.1
    assert _decode("Dolne źródło wyjście", 32866) == -10.1


def test_signed_temperatures_are_read_unsigned():
    # As S_WORD a raw 32866 is already negative and the filter would skip it.
    for r in _registers().values():
        if any("negative_above" in f for f in r.filters):
            assert r.value_type == "U_WORD", r.name


def test_setpoints_keep_the_flows_scale():
    assert _decode("Nastawa CO komfort", 215) == 21.5
    assert _decode("Nastawa CWU komfort", 50) == 50
