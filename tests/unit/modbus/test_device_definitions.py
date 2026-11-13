import pytest
from pydantic import ValidationError

from boneio.modbus.definition import DeviceDefinition, device_models, load_definition


def _minimal():
    return {
        "model": "x",
        "manufacturer": "m",
        "description": "d",
        "category": "other",
        "default_address": 1,
        "default_update_interval": "60s",
        "registers_base": [
            {
                "base": 0,
                "length": 2,
                "registers": [{"name": "A B", "address": 0, "value_type": "U_WORD"}],
            }
        ],
    }


@pytest.mark.parametrize("model", device_models())
def test_every_device_file_validates(model):
    load_definition(model)


def test_block_without_register_type_reads_input_registers():
    sdm = load_definition("sdm630")
    assert next(b for b in sdm.registers_base if b.base == 342).register_type == "input"


def test_additional_entity_without_entity_type_is_a_sensor():
    (e,) = load_definition("liquid-sensor").additional_entities
    assert e.entity_type == "sensor" and e.formula


def test_unknown_key_is_rejected():
    with pytest.raises(ValidationError):
        DeviceDefinition.model_validate({**_minimal(), "registers_bsae": []})


def test_register_defaults_and_decoded_name():
    (r,) = DeviceDefinition.model_validate(_minimal()).registers_base[0].registers
    assert r.entity_type == "sensor" and r.decoded_name == "ab"
    assert r.ha_filter == "round(2)" and not r.hidden and not r.confirm


def test_button_and_new_fields():
    d = _minimal()
    d["registers_base"][0]["optional"] = True
    d["registers_base"][0]["registers"].append(
        {"name": "Go", "address": 1, "value_type": "U_WORD", "entity_type": "button"}
    )
    d["heat_pump"] = {"scheme": "phnix", "roles": {"a": "b", "c": ["d"]}}
    m = DeviceDefinition.model_validate(d)
    assert m.registers_base[0].registers[1].write_value == 1
    assert m.registers_base[0].optional and m.heat_pump.scheme == "phnix"


def _key(name):
    return name.replace("_", "").lower()


# thessla: "Operation mode" is declared twice (coil + holding) and three additional
# entities point at registers that do not exist; needs hardware knowledge to fix.
_KNOWN_BAD = {"thessla"}


@pytest.mark.parametrize(
    "model",
    [
        pytest.param(m, marks=pytest.mark.xfail(strict=True, reason="known data gaps"))
        if m in _KNOWN_BAD
        else m
        for m in device_models()
    ],
)
def test_names_sources_and_addresses_are_consistent(model):
    d = load_definition(model)
    names = [r.decoded_name for b in d.registers_base for r in b.registers]
    assert len(names) == len(set(names))
    for b in d.registers_base:
        for r in b.registers:
            assert b.base <= r.address < b.base + b.length
    keys = {_key(n) for n in names}
    for a in d.additional_entities:
        for src in [a.source] if isinstance(a.source, str) else a.source:
            assert _key(src) in keys


_WORDS = {"FP32": 2, "U_DWORD": 2, "S_DWORD": 2, "U_WORD": 1, "S_WORD": 1}


@pytest.mark.parametrize("model", device_models())
def test_registers_fit_inside_their_block_with_their_width(model):
    for b in load_definition(model).registers_base:
        for r in b.registers:
            assert r.address + _WORDS[r.value_type] <= b.base + b.length, (b.base, r.name)
