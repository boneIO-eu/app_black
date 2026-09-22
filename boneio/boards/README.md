# Board maps

One directory per hardware revision, named exactly as `boneio.version` in the
config. `get_board_config_path()` resolves `<version>/<file>.yaml` and raises if
the directory is missing, so a new revision needs a directory here before the
schema will accept it.

| File | What it maps |
| --- | --- |
| `input.yaml` | `boneio_input: in_NN` → physical pin |
| `output_<board>.yaml` | `boneio_output: out_NN` → MCP/GPIO pin, plus the expander addresses |

## Revisions

| Version | Notes |
| --- | --- |
| 0.2, 0.3 | MCP9808 temperature sensor, no power monitor, modbus on uart1 |
| 0.4 – 0.7 | LM75 + INA219, modbus on uart4, MCP23017 at 0x20/0x21 |
| 0.8 | As 0.7, but MCP23017 moved to 0x23/0x24 |
| 1.0 | INA226 instead of INA219, DS2484 1-Wire bridge, MCP outputs inverted |
| 1.1 | As 1.0, plus the buzzer |

The sensor and UART side of this table is also encoded in `HARDWARE_SENSORS`
(`webui/routes/update.py`); the I2C addresses live only in the board maps here.

Adding a revision means: a directory here, an entry in `HARDWARE_SENSORS`
(`webui/routes/update.py`), the overlay maps in `webui/routes/system.py` and the
frontend's `useOverlayCheck.ts`, the `allowed` list in `schema/schema.yaml` —
and then regenerating `webui/schema/*.json` with

```bash
python -m boneio.core.config.schema_converter
```

## The buzzer

Populated on 1.1 boards. It is an ordinary output: the board maps carry a
`buzzer` entry with `kind: buzzer`, so a config asks for it the same way it asks
for a relay.

```yaml
output:
  - id: buzzer
    boneio_output: buzzer
```

`OutputManager` turns that into a `BuzzerOutput`, which drives
`/sys/class/leds/boneio:buzzer/brightness` (override with `sysfs_path`).

The mapping exists only in the 1.1 maps. It used to be in the 1.0 ones too,
where the part is not fitted, so asking for it there produced an output that
logged sysfs write errors instead of beeping; a 1.0 config that still names
`boneio_output: buzzer` is now rejected at load with "Output mapping 'buzzer'
not found in board configuration", which is the honest answer for a board that
has no buzzer.
